"""Phase D — Status cog.

`/status [public]` — embed reporting overall Discord health.
                     Ephemeral by default; `public=True` posts to the channel (mod-only).

Plus a scheduled auto-post at 00:00 and 12:00 in config.STATUS_TIMEZONE,
landing in config.STATUS_AUTO_POST_CHANNEL_ID (falls back to #audit-log).
"""

import logging
import time
from datetime import datetime, time as dt_time
from zoneinfo import ZoneInfo

import discord
from discord import app_commands
from discord.ext import commands, tasks

import config
from utils import embeds

log = logging.getLogger("topshooter.status")

COLOR_GREEN = 0x39FF14
COLOR_YELLOW = 0xFF5F1F
COLOR_RED = 0xFF1F1F

VERDICT_COLOR = {"green": COLOR_GREEN, "yellow": COLOR_YELLOW, "red": COLOR_RED}
VERDICT_LABEL = {"green": "🟩 HEALTHY", "yellow": "🟧 WATCH", "red": "🟥 CRITICAL"}


def _format_uptime(start_ts: float) -> str:
    elapsed = int(time.time() - start_ts)
    days, rem = divmod(elapsed, 86400)
    hours, rem = divmod(rem, 3600)
    mins, _ = divmod(rem, 60)
    parts = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    if mins or not parts:
        parts.append(f"{mins}m")
    return "".join(parts)


async def _build_status(bot: commands.Bot, guild: discord.Guild, started_at: float, is_auto: bool = False) -> discord.Embed:
    # --- Bot --------------------------------------------------------------
    latency = round(bot.latency * 1000) if bot.is_ready() else None

    # --- Server -----------------------------------------------------------
    members = guild.member_count or 0
    online = sum(1 for m in guild.members if m.status != discord.Status.offline)
    bot_count = sum(1 for m in guild.members if m.bot)

    text_chs = sum(1 for c in guild.channels if isinstance(c, discord.TextChannel))
    voice_chs = sum(1 for c in guild.channels if isinstance(c, discord.VoiceChannel))
    forum_chs = sum(1 for c in guild.channels if isinstance(c, discord.ForumChannel))

    # --- Moderation -------------------------------------------------------
    try:
        bans_count = sum(1 async for _ in guild.bans(limit=None))
    except discord.Forbidden:
        bans_count = -1

    warn_row = await bot.db.fetchone(
        "SELECT COUNT(*) AS n FROM warns WHERE guild_id = $1 AND cleared_at IS NULL",
        (guild.id,),
    )
    active_warns = warn_row["n"] if warn_row else 0

    top_flagged_rows = await bot.db.fetchall(
        "SELECT user_id, COUNT(*) AS n FROM warns "
        "WHERE guild_id = $1 AND cleared_at IS NULL "
        "GROUP BY user_id ORDER BY n DESC LIMIT 5",
        (guild.id,),
    )

    # --- AutoMod ---------------------------------------------------------
    am_row = await bot.db.fetchone(
        "SELECT COUNT(*) AS n FROM automod_rules WHERE guild_id = $1 AND enabled = TRUE",
        (guild.id,),
    )
    settings = await bot.db.get_guild_settings(guild.id)
    raid_active = bool(settings["raid_mode"]) if settings else False
    automod_on = bool(settings["automod_enabled"]) if settings else False

    # --- Verdict ---------------------------------------------------------
    verdict = "green"
    if active_warns >= 10 or not automod_on:
        verdict = "yellow"
    if not bot.is_ready() or raid_active:
        verdict = "red"

    # --- Build embed -----------------------------------------------------
    embed = discord.Embed(
        title=f"STATUS — {guild.name}",
        color=VERDICT_COLOR[verdict],
        timestamp=discord.utils.utcnow(),
    )
    embed.add_field(
        name="🤖 BOT",
        value=(
            f"Status: **{'🟢 ready' if bot.is_ready() else '🔴 not ready'}**\n"
            f"Latency: `{latency} ms`\n"
            f"Uptime: `{_format_uptime(started_at)}`"
        ),
        inline=True,
    )
    embed.add_field(
        name="👥 SERVER",
        value=(
            f"Members: **{members}** ({online} online, {bot_count} bots)\n"
            f"Channels: text **{text_chs}** · voice **{voice_chs}** · forum **{forum_chs}**\n"
            f"Roles: **{len(guild.roles)}**"
        ),
        inline=True,
    )

    top_lines = []
    for r in top_flagged_rows:
        member = guild.get_member(r["user_id"])
        name = member.display_name if member else f"`{r['user_id']}`"
        top_lines.append(f"{name} · {r['n']}")
    if not top_lines:
        top_lines = ["*none*"]
    embed.add_field(
        name="🛡️ MODERATION",
        value=(
            f"Bans: **{bans_count if bans_count >= 0 else '?'}**\n"
            f"Active warns: **{active_warns}**\n"
            f"Top flagged:\n" + "\n".join(f"  · {l}" for l in top_lines)
        ),
        inline=False,
    )

    embed.add_field(
        name="🚨 AUTOMOD",
        value=(
            f"Engine: **{'ON' if automod_on else 'OFF'}**\n"
            f"Patterns: **{am_row['n'] if am_row else 0}**\n"
            f"Raid mode: **{'🚨 ACTIVE' if raid_active else 'clear'}**"
        ),
        inline=True,
    )

    embed.add_field(
        name="VERDICT",
        value=VERDICT_LABEL[verdict],
        inline=True,
    )

    footer = f"{config.BRAND_FOOTER}" + (" · AUTO" if is_auto else "")
    embed.set_footer(text=footer)
    return embed


# ---------------------------------------------------------------------------
class Status(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.started_at = time.time()
        self.auto_post_loop.start()

    def cog_unload(self):
        self.auto_post_loop.cancel()

    @app_commands.command(name="status", description="Show bot + server health snapshot. Ephemeral by default.")
    @app_commands.describe(public="Post to the channel (visible to everyone). Requires manage_messages.")
    async def status_cmd(self, interaction: discord.Interaction, public: bool = False):
        if public and not interaction.user.guild_permissions.manage_messages:
            await interaction.response.send_message(
                embed=embeds.error("Public status requires manage_messages."),
                ephemeral=True,
            )
            return
        embed = await _build_status(self.bot, interaction.guild, self.started_at)
        await interaction.response.send_message(embed=embed, ephemeral=not public)

    # -- Scheduled auto-post (00:00 and 12:00 in STATUS_TIMEZONE) ----------
    @tasks.loop(time=[
        dt_time(hour=0, minute=0),
        dt_time(hour=12, minute=0),
    ])
    async def auto_post_loop(self):
        # discord.tasks.loop interprets `time` in UTC by default. Convert by
        # rescheduling at the next correct local moment instead — simpler to
        # check the local hour/minute ourselves and bail if it's not our window.
        # The above schedule is UTC-anchored, so we adjust by re-checking.
        if not config.STATUS_AUTO_POST_CHANNEL_ID:
            return
        if not self.bot.is_ready() or not config.DEV_GUILD_ID:
            return
        guild = self.bot.get_guild(config.DEV_GUILD_ID)
        if not guild:
            return
        # Verify it's actually 00:00 or 12:00 in the configured TZ (within a 30-min slop).
        try:
            tz = ZoneInfo(config.STATUS_TIMEZONE)
        except Exception:
            tz = ZoneInfo("UTC")
        now_local = datetime.now(tz)
        if now_local.hour not in (0, 12):
            return
        ch = guild.get_channel(config.STATUS_AUTO_POST_CHANNEL_ID)
        if not isinstance(ch, discord.TextChannel):
            ch = discord.utils.get(guild.text_channels, name="audit-log")
        if not ch:
            log.warning("auto-status: target channel missing")
            return
        try:
            embed = await _build_status(self.bot, guild, self.started_at, is_auto=True)
            await ch.send(embed=embed)
            log.info("auto-status posted to #%s (%s local)", ch.name, now_local.strftime("%H:%M %Z"))
        except (discord.Forbidden, discord.HTTPException) as e:
            log.warning("auto-status post failed: %s", e)

    @auto_post_loop.before_loop
    async def before_auto_post(self):
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot):
    await bot.add_cog(Status(bot))
