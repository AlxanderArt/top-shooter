"""Phase 7 — Levels / XP cog.

Mechanics
---------
- On every non-bot message in a guild, the author gains 5–10 random XP
  (uniform). 60-second per-user-per-guild cooldown prevents spam-grinding.
- Level formula: `level = floor(sqrt(xp / 100))`.
  → Level 1 at 100 XP, Level 10 at 10000 XP, Level 20 at 40000 XP, etc.
  At ~7.5 XP/message average and 60s cooldown, hitting Level 20 takes roughly
  5,300 messages — months of normal-pace chatting. This is the "hard" gate
  for @New Shooter that the brand chose.
- On level up:
    1. Post a "RANK UP — LEVEL {n}." embed in the configured announce channel,
       falling back to the message's own channel.
    2. Grant any `level_roles` rows where `level <= new_level`. The bot's
       top-role must be above the role; otherwise we skip with a warning.

Commands
--------
/rank [user]                   open
/leaderboard                   open
/levels enable                 manage_guild
/levels disable                manage_guild
/levels announce_channel [ch]  manage_guild — clears to fallback if no channel
"""

import logging
import math
import random
import time

import discord
from discord import app_commands
from discord.ext import commands

import config
from utils import embeds, event_push, strings

log = logging.getLogger("topshooter.levels")

XP_COOLDOWN_SECONDS = 60
XP_MIN = 5
XP_MAX = 10

LEVEL_UP_COLOR = 0x39FF14
RANK_COLOR = 0xFF5F1F
LEADERBOARD_COLOR = 0x39FF14


# ---------------------------------------------------------------------------
# Math helpers
# ---------------------------------------------------------------------------
def xp_for_level(level: int) -> int:
    """Total XP needed to be AT that level (inclusive lower bound)."""
    if level <= 0:
        return 0
    return level * level * 100


def level_for_xp(xp: int) -> int:
    return int(math.isqrt(max(0, xp) // 100))


def progress_bar(current: int, total: int, width: int = 12) -> str:
    if total <= 0:
        return "░" * width
    pct = max(0.0, min(1.0, current / total))
    filled = int(pct * width)
    return "█" * filled + "░" * (width - filled)


# ---------------------------------------------------------------------------
class Levels(commands.Cog):
    levels_group = app_commands.Group(
        name="levels",
        description="Configure the XP / leveling system.",
        default_permissions=discord.Permissions(manage_guild=True),
    )

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # =======================================================================
    # XP accrual on every message
    # =======================================================================
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or message.guild is None:
            return
        if not message.content and not message.attachments:
            return  # ignore system messages
        # Slash commands fire on_message too; the content starts with /, but we still
        # award XP — chatting is chatting. Filtering by prefix would punish helpers.

        settings = await self.bot.db.get_guild_settings(message.guild.id)
        if settings and not settings["levels_enabled"]:
            return

        now = int(time.time())
        row = await self.bot.db.fetchone(
            "SELECT xp, level, last_message_at FROM levels WHERE guild_id = $1 AND user_id = $2",
            (message.guild.id, message.author.id),
        )
        if row and (now - row["last_message_at"]) < XP_COOLDOWN_SECONDS:
            return

        gained = random.randint(XP_MIN, XP_MAX)
        new_xp = (row["xp"] if row else 0) + gained
        new_level = level_for_xp(new_xp)
        old_level = row["level"] if row else 0

        await self.bot.db.execute(
            "INSERT INTO levels (guild_id, user_id, xp, level, last_message_at) "
            "VALUES ($1, $2, $3, $4, $5) "
            "ON CONFLICT (guild_id, user_id) DO UPDATE SET "
            "    xp = EXCLUDED.xp, level = EXCLUDED.level, last_message_at = EXCLUDED.last_message_at",
            (message.guild.id, message.author.id, new_xp, new_level, now),
        )

        if new_level > old_level:
            await self._handle_levelup(message, new_level, settings)

    async def _handle_levelup(self, message: discord.Message, new_level: int, settings):
        event_push.push(
            "level_up",
            guild_id=message.guild.id,
            target_id=message.author.id,
            details={"level": new_level, "channel_id": message.channel.id},
        )
        # Announce
        announce_ch = message.channel
        if settings and settings["levels_announce_channel"]:
            ch = message.guild.get_channel(settings["levels_announce_channel"])
            if isinstance(ch, discord.TextChannel):
                announce_ch = ch

        embed = discord.Embed(
            title=strings.LEVEL_UP.format(n=new_level),
            description=f"{message.author.mention} just hit level **{new_level}**.",
            color=LEVEL_UP_COLOR,
            timestamp=discord.utils.utcnow(),
        )
        embed.set_thumbnail(url=message.author.display_avatar.url)
        embed.set_footer(text=config.BRAND_FOOTER)
        try:
            await announce_ch.send(embed=embed)
        except (discord.Forbidden, discord.HTTPException) as e:
            log.warning("level-up announce failed: %s", e)

        # Grant any level-role bindings up to (and including) the new level
        rows = await self.bot.db.fetchall(
            "SELECT level, role_id FROM level_roles WHERE guild_id = $1 AND level <= $2 ORDER BY level",
            (message.guild.id, new_level),
        )
        bot_top = message.guild.me.top_role
        for r in rows:
            role = message.guild.get_role(r["role_id"])
            if not role or role in message.author.roles:
                continue
            if role >= bot_top:
                log.warning("level-role %s is above bot top role; skipping grant", role)
                continue
            try:
                await message.author.add_roles(role, reason=f"level {new_level} reward")
            except (discord.Forbidden, discord.HTTPException) as e:
                log.warning("level-role grant failed: %s", e)

    # =======================================================================
    # /rank
    # =======================================================================
    @app_commands.command(name="rank", description="Show your XP rank, or another member's.")
    @app_commands.describe(user="Member to check (default: yourself).")
    async def rank(self, interaction: discord.Interaction, user: discord.Member | None = None):
        target = user or interaction.user
        if target.bot:
            await interaction.response.send_message(
                embed=embeds.info("Bots don't accrue XP."),
                ephemeral=True,
            )
            return

        row = await self.bot.db.fetchone(
            "SELECT xp, level FROM levels WHERE guild_id = $1 AND user_id = $2",
            (interaction.guild.id, target.id),
        )
        xp = row["xp"] if row else 0
        level = row["level"] if row else 0
        xp_floor = xp_for_level(level)
        xp_ceiling = xp_for_level(level + 1)
        xp_this_level = xp - xp_floor
        xp_to_next = xp_ceiling - xp_floor
        bar = progress_bar(xp_this_level, xp_to_next)

        rank_row = await self.bot.db.fetchone(
            "SELECT COUNT(*) + 1 AS rank FROM levels WHERE guild_id = $1 AND xp > $2",
            (interaction.guild.id, xp),
        )
        server_rank = rank_row["rank"] if rank_row else 1

        embed = discord.Embed(title=f"RANK — {target.display_name}", color=RANK_COLOR)
        embed.add_field(name="Level", value=f"**{level}**", inline=True)
        embed.add_field(name="Total XP", value=f"`{xp:,}`", inline=True)
        embed.add_field(name="Server Rank", value=f"`#{server_rank}`", inline=True)
        embed.add_field(
            name="To Next Level",
            value=f"`{bar}` `{xp_this_level:,}/{xp_to_next:,}`",
            inline=False,
        )
        embed.set_thumbnail(url=target.display_avatar.url)
        embed.set_footer(text=config.BRAND_FOOTER)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # =======================================================================
    # /leaderboard
    # =======================================================================
    @app_commands.command(name="leaderboard", description="Top 10 XP earners in this server.")
    async def leaderboard(self, interaction: discord.Interaction):
        rows = await self.bot.db.fetchall(
            "SELECT user_id, xp, level FROM levels WHERE guild_id = $1 ORDER BY xp DESC LIMIT 10",
            (interaction.guild.id,),
        )
        if not rows:
            await interaction.response.send_message(
                embed=embeds.info("LEADERBOARD EMPTY.", "No XP accrued yet."),
                ephemeral=True,
            )
            return
        medals = ["🥇", "🥈", "🥉"]
        lines = []
        for i, r in enumerate(rows):
            member = interaction.guild.get_member(r["user_id"])
            name = member.display_name if member else f"`{r['user_id']}`"
            marker = medals[i] if i < 3 else f"`#{i + 1:>2}`"
            lines.append(f"{marker} **{name}** · L{r['level']} · `{r['xp']:,}` XP")
        embed = discord.Embed(
            title="LEADERBOARD — TOP 10.",
            description="\n".join(lines),
            color=LEADERBOARD_COLOR,
        )
        embed.set_footer(text=config.BRAND_FOOTER)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # =======================================================================
    # /levels enable / disable / announce_channel
    # =======================================================================
    @levels_group.command(name="enable", description="Enable XP accrual on this server.")
    async def levels_enable(self, interaction: discord.Interaction):
        await self.bot.db.execute(
            "INSERT INTO guild_settings (guild_id, levels_enabled) VALUES ($1, TRUE) "
            "ON CONFLICT (guild_id) DO UPDATE SET levels_enabled = TRUE",
            (interaction.guild.id,),
        )
        await interaction.response.send_message(embed=embeds.success("LEVELS ENABLED."), ephemeral=True)

    @levels_group.command(name="disable", description="Disable XP accrual on this server.")
    async def levels_disable(self, interaction: discord.Interaction):
        await self.bot.db.execute(
            "INSERT INTO guild_settings (guild_id, levels_enabled) VALUES ($1, FALSE) "
            "ON CONFLICT (guild_id) DO UPDATE SET levels_enabled = FALSE",
            (interaction.guild.id,),
        )
        await interaction.response.send_message(embed=embeds.success("LEVELS DISABLED. Existing XP retained."), ephemeral=True)

    @levels_group.command(name="announce_channel", description="Set the channel for level-up messages. Leave blank to use the user's current channel.")
    @app_commands.describe(channel="Where level-up announcements should post. Leave blank to clear.")
    async def levels_announce_channel(self, interaction: discord.Interaction, channel: discord.TextChannel | None = None):
        await self.bot.db.execute(
            "INSERT INTO guild_settings (guild_id, levels_announce_channel) VALUES ($1, $2) "
            "ON CONFLICT (guild_id) DO UPDATE SET levels_announce_channel = EXCLUDED.levels_announce_channel",
            (interaction.guild.id, channel.id if channel else None),
        )
        msg = (
            f"LEVEL-UP ANNOUNCE → {channel.mention}"
            if channel
            else "LEVEL-UP ANNOUNCE → message's own channel (default)."
        )
        await interaction.response.send_message(embed=embeds.success(msg), ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Levels(bot))
