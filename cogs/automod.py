"""Phase 8 — AutoMod cog.

Three independent layers, all gated by `guild_settings.automod_enabled`:

1. **Regex pattern filter.** Patterns stored in `automod_rules`. Each rule has
   an action: `delete`, `delete+warn`, or `delete+timeout:Xm`. On any message
   matching a pattern, the action runs and an audit entry is posted.

2. **Anti-spam.** In-memory deque of message timestamps per (guild, user).
   ≥ 5 messages within 5 seconds → 10-minute timeout + audit alert.

3. **Anti-raid.** In-memory deque of join timestamps per guild. ≥ 10 joins
   within 30 seconds → flip the guild into "raid mode" for 5 minutes; new
   joins during that window get auto-kicked and the audit channel is alerted.

Plus `/slowmode <seconds>` as a convenience.

Moderators and admins (anyone with `manage_messages`) are exempt from
all filters.
"""

import logging
import re
import time
from collections import defaultdict, deque
from datetime import timedelta

import discord
from discord import app_commands
from discord.ext import commands

import config
from utils import embeds, event_push
from utils.time_parse import format_duration, parse_duration

log = logging.getLogger("topshooter.automod")

# Anti-spam: ≥ THRESHOLD messages in WINDOW seconds → TIMEOUT
SPAM_WINDOW = 5
SPAM_THRESHOLD = 5
SPAM_TIMEOUT = timedelta(minutes=10)

# Anti-raid: ≥ THRESHOLD joins in WINDOW seconds → raid mode for DURATION
RAID_WINDOW = 30
RAID_THRESHOLD = 10
RAID_DURATION = timedelta(minutes=5)

VALID_ACTIONS_HELP = (
    "Valid actions: `delete`, `delete+warn`, "
    "`delete+timeout:<duration>` (e.g. `delete+timeout:10m`)."
)


def _parse_action(action_str: str) -> tuple[str, timedelta | None]:
    """Return (kind, optional_duration). Raises ValueError on bad input."""
    s = action_str.strip().lower()
    if s == "delete":
        return "delete", None
    if s == "delete+warn":
        return "delete+warn", None
    if s.startswith("delete+timeout:"):
        td = parse_duration(s.split(":", 1)[1])
        return "delete+timeout", td
    raise ValueError("Unknown action.")


async def _get_log_channel(bot: commands.Bot, guild: discord.Guild) -> discord.TextChannel | None:
    settings = await bot.db.get_guild_settings(guild.id)
    if settings and settings["log_channel_id"]:
        ch = guild.get_channel(settings["log_channel_id"])
        if isinstance(ch, discord.TextChannel):
            return ch
    return discord.utils.get(guild.text_channels, name="audit-log")


async def _audit(bot: commands.Bot, guild: discord.Guild, embed: discord.Embed) -> None:
    ch = await _get_log_channel(bot, guild)
    if not ch:
        return
    try:
        await ch.send(embed=embed)
    except (discord.Forbidden, discord.HTTPException) as e:
        log.warning("automod audit send failed: %s", e)


# ---------------------------------------------------------------------------
class AutoMod(commands.Cog):
    automod_group = app_commands.Group(
        name="automod",
        description="Top Shooter's automoderation engine.",
        default_permissions=discord.Permissions(manage_guild=True),
    )

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # In-memory state
        self.recent_messages: dict[tuple[int, int], deque[float]] = defaultdict(
            lambda: deque(maxlen=SPAM_THRESHOLD + 5)
        )
        self.recent_joins: dict[int, deque[float]] = defaultdict(
            lambda: deque(maxlen=RAID_THRESHOLD + 5)
        )
        self.raid_mode_until: dict[int, float] = {}
        # Pattern cache (guild_id → list of (id, compiled_regex, action_kind, action_td))
        self._patterns: dict[int, list[tuple[int, re.Pattern, str, timedelta | None]]] = {}

    def _bust_pattern_cache(self, guild_id: int) -> None:
        self._patterns.pop(guild_id, None)

    async def _get_patterns(self, guild_id: int):
        if guild_id in self._patterns:
            return self._patterns[guild_id]
        rows = await self.bot.db.fetchall(
            "SELECT id, pattern, action FROM automod_rules WHERE guild_id = $1 AND enabled = TRUE",
            (guild_id,),
        )
        compiled = []
        for r in rows:
            try:
                rx = re.compile(r["pattern"], re.IGNORECASE | re.MULTILINE)
                kind, td = _parse_action(r["action"])
                compiled.append((r["id"], rx, kind, td))
            except (re.error, ValueError) as e:
                log.warning("bad automod rule #%s: %s", r["id"], e)
        self._patterns[guild_id] = compiled
        return compiled

    # =======================================================================
    # /automod enable / disable / raid_off / patterns
    # =======================================================================
    @automod_group.command(name="enable", description="Turn Top Shooter's automod on.")
    async def am_enable(self, interaction: discord.Interaction):
        await self.bot.db.execute(
            "INSERT INTO guild_settings (guild_id, automod_enabled) VALUES ($1, TRUE) "
            "ON CONFLICT (guild_id) DO UPDATE SET automod_enabled = TRUE",
            (interaction.guild.id,),
        )
        await interaction.response.send_message(embed=embeds.success("AUTOMOD ENABLED."), ephemeral=True)

    @automod_group.command(name="disable", description="Turn Top Shooter's automod off.")
    async def am_disable(self, interaction: discord.Interaction):
        await self.bot.db.execute(
            "INSERT INTO guild_settings (guild_id, automod_enabled) VALUES ($1, FALSE) "
            "ON CONFLICT (guild_id) DO UPDATE SET automod_enabled = FALSE",
            (interaction.guild.id,),
        )
        await interaction.response.send_message(embed=embeds.success("AUTOMOD DISABLED."), ephemeral=True)

    @automod_group.command(name="raid_off", description="Force raid-mode off (cancel auto-kicks).")
    async def am_raid_off(self, interaction: discord.Interaction):
        self.raid_mode_until.pop(interaction.guild.id, None)
        await self.bot.db.execute(
            "UPDATE guild_settings SET raid_mode = FALSE WHERE guild_id = $1",
            (interaction.guild.id,),
        )
        await interaction.response.send_message(embed=embeds.success("RAID MODE LIFTED."), ephemeral=True)

    @automod_group.command(name="add_pattern", description="Add a regex pattern + action.")
    @app_commands.describe(
        pattern="Python-style regex (case-insensitive, multiline).",
        action="Action: `delete`, `delete+warn`, or `delete+timeout:10m`.",
    )
    async def am_add(self, interaction: discord.Interaction, pattern: str, action: str):
        try:
            re.compile(pattern)
        except re.error as e:
            await interaction.response.send_message(embed=embeds.error(f"Bad regex — {e}"), ephemeral=True)
            return
        try:
            _parse_action(action)
        except ValueError:
            await interaction.response.send_message(
                embed=embeds.error(f"Bad action.\n{VALID_ACTIONS_HELP}"),
                ephemeral=True,
            )
            return
        cur = await self.bot.db.execute(
            "INSERT INTO automod_rules (guild_id, pattern, action, created_at) VALUES ($1, $2, $3, $4) RETURNING id",
            (interaction.guild.id, pattern, action, int(time.time())),
        )
        self._bust_pattern_cache(interaction.guild.id)
        await interaction.response.send_message(
            embed=embeds.success(f"PATTERN #{cur.lastrowid} ADDED.\n\n`{pattern}` → `{action}`"),
            ephemeral=True,
        )

    @automod_group.command(name="remove_pattern", description="Delete a pattern by ID.")
    @app_commands.describe(pattern_id="Rule ID (from /automod list_patterns).")
    async def am_remove(self, interaction: discord.Interaction, pattern_id: int):
        cur = await self.bot.db.execute(
            "DELETE FROM automod_rules WHERE id = $1 AND guild_id = $2",
            (pattern_id, interaction.guild.id),
        )
        self._bust_pattern_cache(interaction.guild.id)
        if cur.rowcount == 0:
            await interaction.response.send_message(embed=embeds.info("No such rule on this guild."), ephemeral=True)
            return
        await interaction.response.send_message(embed=embeds.success(f"PATTERN #{pattern_id} REMOVED."), ephemeral=True)

    @automod_group.command(name="list_patterns", description="List all automod patterns on this server.")
    async def am_list(self, interaction: discord.Interaction):
        rows = await self.bot.db.fetchall(
            "SELECT id, pattern, action, enabled FROM automod_rules WHERE guild_id = $1 ORDER BY id",
            (interaction.guild.id,),
        )
        if not rows:
            await interaction.response.send_message(embed=embeds.info("No automod patterns yet."), ephemeral=True)
            return
        lines = []
        for r in rows[:25]:
            flag = "" if r["enabled"] else " *(disabled)*"
            lines.append(f"`#{r['id']}` · `{r['pattern']}` → `{r['action']}`{flag}")
        await interaction.response.send_message(
            embed=embeds.info("AUTOMOD PATTERNS.", "\n".join(lines)),
            ephemeral=True,
        )

    # =======================================================================
    # /slowmode
    # =======================================================================
    @app_commands.command(name="slowmode", description="Set slowmode delay on this channel (0–21600s).")
    @app_commands.describe(seconds="0 to disable, otherwise 1–21600 seconds (6h max).")
    @app_commands.default_permissions(manage_channels=True)
    async def slowmode_cmd(self, interaction: discord.Interaction, seconds: app_commands.Range[int, 0, 21600]):
        if not isinstance(interaction.channel, (discord.TextChannel, discord.Thread)):
            await interaction.response.send_message(embed=embeds.error("Slowmode applies to text channels only."), ephemeral=True)
            return
        try:
            await interaction.channel.edit(slowmode_delay=seconds)
        except discord.HTTPException as e:
            await interaction.response.send_message(embed=embeds.error(f"SLOWMODE FAILED — {e}"), ephemeral=True)
            return
        msg = "SLOWMODE OFF." if seconds == 0 else f"SLOWMODE — {seconds}s."
        await interaction.response.send_message(embed=embeds.success(msg), ephemeral=True)

    # =======================================================================
    # Message listener — anti-spam + patterns
    # =======================================================================
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or message.guild is None:
            return
        # Members with manage_messages are exempt (mods + staff).
        if isinstance(message.author, discord.Member) and message.author.guild_permissions.manage_messages:
            return

        settings = await self.bot.db.get_guild_settings(message.guild.id)
        if not settings or not settings["automod_enabled"]:
            return

        # --- Anti-spam ----------------------------------------------------
        if await self._check_spam(message):
            return  # already acted

        # --- Pattern filter ----------------------------------------------
        if not message.content:
            return
        patterns = await self._get_patterns(message.guild.id)
        for rule_id, regex, kind, td in patterns:
            if regex.search(message.content):
                await self._apply_pattern_action(message, rule_id, kind, td, regex.pattern)
                return

    async def _check_spam(self, message: discord.Message) -> bool:
        key = (message.guild.id, message.author.id)
        dq = self.recent_messages[key]
        now = time.time()
        dq.append(now)
        cutoff = now - SPAM_WINDOW
        recent_count = sum(1 for t in dq if t >= cutoff)
        if recent_count < SPAM_THRESHOLD:
            return False

        try:
            await message.author.timeout(SPAM_TIMEOUT, reason=f"anti-spam ({SPAM_THRESHOLD} msgs/{SPAM_WINDOW}s)")
        except (discord.Forbidden, discord.HTTPException) as e:
            log.warning("anti-spam timeout failed: %s", e)
            return False

        dq.clear()

        # Try to wipe their recent messages in this channel
        try:
            await message.channel.purge(limit=SPAM_THRESHOLD * 2, check=lambda m: m.author.id == message.author.id, reason="anti-spam cleanup")
        except (discord.Forbidden, discord.HTTPException) as e:
            log.warning("anti-spam purge failed: %s", e)

        # Audit
        embed = discord.Embed(
            title=f"[AUTOMOD · SPAM] · {message.author}",
            description=(
                f"**Target:** {message.author.mention} (`{message.author.id}`)\n"
                f"**Action:** {format_duration(SPAM_TIMEOUT)} timeout\n"
                f"**Trigger:** {SPAM_THRESHOLD} messages in {SPAM_WINDOW}s\n"
                f"**Channel:** {message.channel.mention}"
            ),
            color=0xFF1F1F,
            timestamp=discord.utils.utcnow(),
        )
        embed.set_footer(text=config.BRAND_FOOTER)
        await _audit(self.bot, message.guild, embed)
        event_push.push(
            "automod_spam",
            guild_id=message.guild.id,
            target_id=message.author.id,
            details={"channel_id": message.channel.id, "timeout_s": int(SPAM_TIMEOUT.total_seconds())},
        )
        return True

    async def _apply_pattern_action(self, message: discord.Message, rule_id: int, kind: str, td: timedelta | None, pattern_str: str):
        try:
            await message.delete()
        except (discord.Forbidden, discord.NotFound, discord.HTTPException) as e:
            log.warning("automod delete failed: %s", e)
            return

        action_detail = "delete"
        if kind == "delete+warn":
            await self.bot.db.execute(
                "INSERT INTO warns (guild_id, user_id, moderator_id, reason, created_at) VALUES ($1, $2, $3, $4, $5)",
                (message.guild.id, message.author.id, self.bot.user.id, f"automod rule #{rule_id}", int(time.time())),
            )
            action_detail = "delete + warn"
        elif kind == "delete+timeout" and td is not None:
            try:
                await message.author.timeout(td, reason=f"automod rule #{rule_id}")
                action_detail = f"delete + timeout ({format_duration(td)})"
            except (discord.Forbidden, discord.HTTPException) as e:
                log.warning("automod timeout failed: %s", e)

        embed = discord.Embed(
            title=f"[AUTOMOD · PATTERN] · {message.author}",
            description=(
                f"**Target:** {message.author.mention} (`{message.author.id}`)\n"
                f"**Action:** {action_detail}\n"
                f"**Rule:** #{rule_id} · `{pattern_str}`\n"
                f"**Channel:** {message.channel.mention}"
            ),
            color=0xFF1F1F,
            timestamp=discord.utils.utcnow(),
        )
        embed.set_footer(text=config.BRAND_FOOTER)
        await _audit(self.bot, message.guild, embed)
        event_push.push(
            "automod_pattern",
            guild_id=message.guild.id,
            target_id=message.author.id,
            details={"rule_id": rule_id, "pattern": pattern_str, "action": kind, "channel_id": message.channel.id},
        )

    # =======================================================================
    # Member-join listener — anti-raid + raid-mode auto-kick
    # =======================================================================
    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        if member.bot:
            return

        guild = member.guild
        settings = await self.bot.db.get_guild_settings(guild.id)
        if not settings or not settings["automod_enabled"]:
            return

        now = time.time()

        # Already in raid mode → auto-kick this join
        if now < self.raid_mode_until.get(guild.id, 0):
            try:
                await member.kick(reason="anti-raid auto-kick")
            except (discord.Forbidden, discord.HTTPException) as e:
                log.warning("raid auto-kick failed: %s", e)
                return
            embed = discord.Embed(
                title=f"[AUTOMOD · RAID-KICK] · {member}",
                description=f"{member.mention} (`{member.id}`) auto-kicked under active raid mode.",
                color=0xFF1F1F,
                timestamp=discord.utils.utcnow(),
            )
            embed.set_footer(text=config.BRAND_FOOTER)
            await _audit(self.bot, guild, embed)
            return

        # Record + evaluate join burst
        dq = self.recent_joins[guild.id]
        dq.append(now)
        cutoff = now - RAID_WINDOW
        recent_count = sum(1 for t in dq if t >= cutoff)
        if recent_count < RAID_THRESHOLD:
            return

        # Enter raid mode
        self.raid_mode_until[guild.id] = now + RAID_DURATION.total_seconds()
        await self.bot.db.execute(
            "UPDATE guild_settings SET raid_mode = TRUE WHERE guild_id = $1",
            (guild.id,),
        )

        embed = discord.Embed(
            title="[AUTOMOD · RAID DETECTED]",
            description=(
                f"**{recent_count} joins** in the last {RAID_WINDOW}s.\n"
                f"Raid mode is now **ACTIVE** for {format_duration(RAID_DURATION)} — "
                f"new joins are auto-kicked until it lifts.\n"
                f"Use `/automod raid_off` to cancel early."
            ),
            color=0xFF1F1F,
            timestamp=discord.utils.utcnow(),
        )
        embed.set_footer(text=config.BRAND_FOOTER)
        await _audit(self.bot, guild, embed)
        event_push.push("automod_raid", guild_id=guild.id, details={"joins_in_window": recent_count})


async def setup(bot: commands.Bot):
    await bot.add_cog(AutoMod(bot))
