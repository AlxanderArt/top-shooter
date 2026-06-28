"""Phase 3 — Moderation cog.

Slash commands: /kick, /ban, /unban, /timeout, /untimeout, /role add|remove,
                /warn, /warns, /clearwarns

Every mod action:
- Pre-checks role hierarchy (utils.checks.can_act_on).
- Best-effort DMs the target user with the reason.
- Logs to the guild's configured audit-log channel (falls back to a channel
  named #audit-log if no setting is stored).
- Replies ephemerally to the moderator.

Warn auto-escalation:
- 3 active warns → 10-minute timeout
- 5 active warns → 60-minute timeout
- 7 active warns → kick
"""

import logging
import time
from datetime import timedelta

import discord
from discord import app_commands
from discord.ext import commands

import config
from utils import checks, embeds, event_push, strings
from utils.time_parse import format_duration, parse_duration

log = logging.getLogger("topshooter.mod")

WARN_ESCALATIONS = [
    (3, "timeout", timedelta(minutes=10)),
    (5, "timeout", timedelta(hours=1)),
    (7, "kick", None),
]


def _audit_color(action: str) -> int:
    """Pick an embed color based on action severity."""
    if action in ("ban", "kick"):
        return 0xFF1F1F  # alarm red
    if action in ("timeout", "warn"):
        return 0xFF5F1F  # hi-vis orange
    if action in ("unban", "untimeout", "clearwarns"):
        return 0x39FF14  # neon green
    return 0x3F4448  # slate


async def _send_audit(bot: commands.Bot, guild: discord.Guild, embed: discord.Embed) -> None:
    settings = await bot.db.get_guild_settings(guild.id)
    log_channel = None
    if settings and settings["log_channel_id"]:
        log_channel = guild.get_channel(settings["log_channel_id"])
    if not log_channel:
        log_channel = discord.utils.get(guild.text_channels, name="audit-log")
    if not log_channel:
        return
    try:
        await log_channel.send(embed=embed)
    except (discord.Forbidden, discord.HTTPException) as e:
        log.warning("audit log send failed: %s", e)


def _audit_embed(action: str, target: discord.abc.User, moderator: discord.Member, reason: str, extra: dict | None = None) -> discord.Embed:
    embed = discord.Embed(
        title=f"[{action.upper()}] · {target}",
        color=_audit_color(action),
        timestamp=discord.utils.utcnow(),
    )
    embed.add_field(name="Target", value=f"{target.mention} (`{target.id}`)", inline=True)
    embed.add_field(name="Moderator", value=f"{moderator.mention} (`{moderator.id}`)", inline=True)
    embed.add_field(name="Reason", value=reason or "*none provided*", inline=False)
    if extra:
        for k, v in extra.items():
            embed.add_field(name=k, value=v, inline=True)
    embed.set_footer(text=f"{config.BRAND_FOOTER}")
    return embed


def _dm_embed(action: str, guild_name: str, reason: str, extra: str = "") -> discord.Embed:
    headers = {
        "kick": "YOU HAVE BEEN KICKED.",
        "ban": "YOU HAVE BEEN BANNED.",
        "timeout": "YOU HAVE BEEN TIMED OUT.",
        "warn": "YOU HAVE BEEN WARNED.",
        "untimeout": "TIMEOUT LIFTED.",
        "unban": "BAN LIFTED.",
    }
    color_map = {
        "kick": 0xFF1F1F, "ban": 0xFF1F1F,
        "timeout": 0xFF5F1F, "warn": 0xFF5F1F,
        "untimeout": 0x39FF14, "unban": 0x39FF14,
    }
    embed = discord.Embed(
        title=headers.get(action, action.upper()),
        description=(f"**Server:** {guild_name}\n**Reason:** {reason or '*none provided*'}\n{extra}").strip(),
        color=color_map.get(action, 0x3F4448),
    )
    embed.set_footer(text=config.BRAND_FOOTER)
    return embed


# ---------------------------------------------------------------------------
# Cog
# ---------------------------------------------------------------------------
class Moderation(commands.Cog):
    """Moderation actions: kick, ban, timeout, role, warn."""

    role = app_commands.Group(name="role", description="Manage member roles.", default_permissions=discord.Permissions(manage_roles=True))

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ---- KICK -------------------------------------------------------------
    @app_commands.command(name="kick", description="Kick a member from the server.")
    @app_commands.describe(user="Member to kick.", reason="Reason shown to the user + in the audit log.")
    @app_commands.default_permissions(kick_members=True)
    async def kick(self, interaction: discord.Interaction, user: discord.Member, reason: str = ""):
        ok, why = checks.can_act_on(interaction.user, user, interaction.guild.me)
        if not ok:
            await interaction.response.send_message(embed=embeds.error(why), ephemeral=True)
            return
        # DM first (kicked users can't be DM'd after the kick removes shared servers)
        await checks.try_dm(user, _dm_embed("kick", interaction.guild.name, reason))
        try:
            await user.kick(reason=f"By {interaction.user}: {reason}")
        except discord.HTTPException as e:
            await interaction.response.send_message(embed=embeds.error(f"KICK FAILED — {e}"), ephemeral=True)
            return
        await _send_audit(self.bot, interaction.guild, _audit_embed("kick", user, interaction.user, reason))
        event_push.push("mod_kick", guild_id=interaction.guild.id, target_id=user.id, actor_id=interaction.user.id, details={"reason": reason})
        await interaction.response.send_message(embed=embeds.success(strings.KICK_DONE), ephemeral=True)

    # ---- BAN --------------------------------------------------------------
    @app_commands.command(name="ban", description="Ban a member from the server.")
    @app_commands.describe(
        user="Member to ban.",
        reason="Reason shown to the user + in the audit log.",
        delete_message_days="Delete the user's recent messages (0–7).",
    )
    @app_commands.default_permissions(ban_members=True)
    async def ban(self, interaction: discord.Interaction, user: discord.Member, reason: str = "", delete_message_days: app_commands.Range[int, 0, 7] = 0):
        ok, why = checks.can_act_on(interaction.user, user, interaction.guild.me)
        if not ok:
            await interaction.response.send_message(embed=embeds.error(why), ephemeral=True)
            return
        await checks.try_dm(user, _dm_embed("ban", interaction.guild.name, reason))
        try:
            await user.ban(reason=f"By {interaction.user}: {reason}", delete_message_seconds=delete_message_days * 86400)
        except discord.HTTPException as e:
            await interaction.response.send_message(embed=embeds.error(f"BAN FAILED — {e}"), ephemeral=True)
            return
        await _send_audit(self.bot, interaction.guild, _audit_embed("ban", user, interaction.user, reason, {"Messages deleted": f"{delete_message_days}d"}))
        event_push.push("mod_ban", guild_id=interaction.guild.id, target_id=user.id, actor_id=interaction.user.id, details={"reason": reason, "delete_message_days": delete_message_days})
        await interaction.response.send_message(embed=embeds.success(strings.BAN_DONE), ephemeral=True)

    # ---- UNBAN ------------------------------------------------------------
    @app_commands.command(name="unban", description="Lift a ban by user ID.")
    @app_commands.describe(user_id="Discord user ID to unban.", reason="Reason for the audit log.")
    @app_commands.default_permissions(ban_members=True)
    async def unban(self, interaction: discord.Interaction, user_id: str, reason: str = ""):
        try:
            uid = int(user_id)
        except ValueError:
            await interaction.response.send_message(embed=embeds.error("Invalid user ID."), ephemeral=True)
            return
        try:
            user = await self.bot.fetch_user(uid)
            await interaction.guild.unban(user, reason=f"By {interaction.user}: {reason}")
        except discord.NotFound:
            await interaction.response.send_message(embed=embeds.error("Not banned, or user not found."), ephemeral=True)
            return
        except discord.HTTPException as e:
            await interaction.response.send_message(embed=embeds.error(f"UNBAN FAILED — {e}"), ephemeral=True)
            return
        await _send_audit(self.bot, interaction.guild, _audit_embed("unban", user, interaction.user, reason))
        event_push.push("mod_unban", guild_id=interaction.guild.id, target_id=user.id, actor_id=interaction.user.id, details={"reason": reason})
        await interaction.response.send_message(embed=embeds.success(f"UNBANNED — {user}"), ephemeral=True)

    # ---- TIMEOUT ----------------------------------------------------------
    @app_commands.command(name="timeout", description="Timeout a member for a duration (e.g. 10m, 2h, 3d).")
    @app_commands.describe(
        user="Member to timeout.",
        duration="Duration like '10m', '2h', '1d'. Max 28d.",
        reason="Reason shown to the user + in the audit log.",
    )
    @app_commands.default_permissions(moderate_members=True)
    async def timeout_cmd(self, interaction: discord.Interaction, user: discord.Member, duration: str, reason: str = ""):
        ok, why = checks.can_act_on(interaction.user, user, interaction.guild.me)
        if not ok:
            await interaction.response.send_message(embed=embeds.error(why), ephemeral=True)
            return
        try:
            td = parse_duration(duration)
        except ValueError as e:
            await interaction.response.send_message(embed=embeds.error(f"BAD DURATION — {e}"), ephemeral=True)
            return
        try:
            await user.timeout(td, reason=f"By {interaction.user}: {reason}")
        except discord.HTTPException as e:
            await interaction.response.send_message(embed=embeds.error(f"TIMEOUT FAILED — {e}"), ephemeral=True)
            return
        await checks.try_dm(user, _dm_embed("timeout", interaction.guild.name, reason, f"**Duration:** {format_duration(td)}"))
        await _send_audit(self.bot, interaction.guild, _audit_embed("timeout", user, interaction.user, reason, {"Duration": format_duration(td)}))
        event_push.push("mod_timeout", guild_id=interaction.guild.id, target_id=user.id, actor_id=interaction.user.id, details={"reason": reason, "duration_s": int(td.total_seconds())})
        await interaction.response.send_message(
            embed=embeds.success(strings.TIMEOUT_DONE.format(duration=format_duration(td))),
            ephemeral=True,
        )

    # ---- UNTIMEOUT --------------------------------------------------------
    @app_commands.command(name="untimeout", description="Remove an active timeout on a member.")
    @app_commands.describe(user="Member to untimeout.", reason="Reason for the audit log.")
    @app_commands.default_permissions(moderate_members=True)
    async def untimeout_cmd(self, interaction: discord.Interaction, user: discord.Member, reason: str = ""):
        ok, why = checks.can_act_on(interaction.user, user, interaction.guild.me)
        if not ok:
            await interaction.response.send_message(embed=embeds.error(why), ephemeral=True)
            return
        try:
            await user.timeout(None, reason=f"By {interaction.user}: {reason}")
        except discord.HTTPException as e:
            await interaction.response.send_message(embed=embeds.error(f"UNTIMEOUT FAILED — {e}"), ephemeral=True)
            return
        await checks.try_dm(user, _dm_embed("untimeout", interaction.guild.name, reason))
        await _send_audit(self.bot, interaction.guild, _audit_embed("untimeout", user, interaction.user, reason))
        event_push.push("mod_untimeout", guild_id=interaction.guild.id, target_id=user.id, actor_id=interaction.user.id, details={"reason": reason})
        await interaction.response.send_message(embed=embeds.success(f"TIMEOUT LIFTED — {user}"), ephemeral=True)

    # ---- ROLE add/remove --------------------------------------------------
    @role.command(name="add", description="Add a role to a member.")
    @app_commands.describe(user="Member to grant the role to.", role="Role to add.")
    async def role_add(self, interaction: discord.Interaction, user: discord.Member, role: discord.Role):
        # Hierarchy: actor must be above the role they're assigning; bot must too.
        if role >= interaction.user.top_role and interaction.user.id != interaction.guild.owner_id:
            await interaction.response.send_message(embed=embeds.error("Role is at or above your top role."), ephemeral=True)
            return
        if role >= interaction.guild.me.top_role:
            await interaction.response.send_message(embed=embeds.error("Role is at or above my top role. Move me up first."), ephemeral=True)
            return
        if role in user.roles:
            await interaction.response.send_message(embed=embeds.info(f"{user} already has {role.name}."), ephemeral=True)
            return
        try:
            await user.add_roles(role, reason=f"By {interaction.user}")
        except discord.HTTPException as e:
            await interaction.response.send_message(embed=embeds.error(f"ROLE ADD FAILED — {e}"), ephemeral=True)
            return
        await _send_audit(self.bot, interaction.guild, _audit_embed("role-add", user, interaction.user, "", {"Role": role.mention}))
        await interaction.response.send_message(embed=embeds.success(f"ROLE GRANTED — {role.name} → {user}"), ephemeral=True)

    @role.command(name="remove", description="Remove a role from a member.")
    @app_commands.describe(user="Member to remove the role from.", role="Role to remove.")
    async def role_remove(self, interaction: discord.Interaction, user: discord.Member, role: discord.Role):
        if role >= interaction.user.top_role and interaction.user.id != interaction.guild.owner_id:
            await interaction.response.send_message(embed=embeds.error("Role is at or above your top role."), ephemeral=True)
            return
        if role >= interaction.guild.me.top_role:
            await interaction.response.send_message(embed=embeds.error("Role is at or above my top role."), ephemeral=True)
            return
        if role not in user.roles:
            await interaction.response.send_message(embed=embeds.info(f"{user} doesn't have {role.name}."), ephemeral=True)
            return
        try:
            await user.remove_roles(role, reason=f"By {interaction.user}")
        except discord.HTTPException as e:
            await interaction.response.send_message(embed=embeds.error(f"ROLE REMOVE FAILED — {e}"), ephemeral=True)
            return
        await _send_audit(self.bot, interaction.guild, _audit_embed("role-remove", user, interaction.user, "", {"Role": role.mention}))
        await interaction.response.send_message(embed=embeds.success(f"ROLE REMOVED — {role.name} from {user}"), ephemeral=True)

    # ---- WARN -------------------------------------------------------------
    @app_commands.command(name="warn", description="Warn a member. Auto-escalates at 3/5/7 active warns.")
    @app_commands.describe(user="Member to warn.", reason="What they did wrong.")
    @app_commands.default_permissions(moderate_members=True)
    async def warn(self, interaction: discord.Interaction, user: discord.Member, reason: str):
        ok, why = checks.can_act_on(interaction.user, user, interaction.guild.me)
        if not ok:
            await interaction.response.send_message(embed=embeds.error(why), ephemeral=True)
            return
        if not reason or not reason.strip():
            await interaction.response.send_message(embed=embeds.error("Reason required."), ephemeral=True)
            return

        await self.bot.db.execute(
            "INSERT INTO warns (guild_id, user_id, moderator_id, reason, created_at) VALUES ($1, $2, $3, $4, $5)",
            (interaction.guild.id, user.id, interaction.user.id, reason.strip(), int(time.time())),
        )

        row = await self.bot.db.fetchone(
            "SELECT COUNT(*) AS n FROM warns WHERE guild_id = $1 AND user_id = $2 AND cleared_at IS NULL",
            (interaction.guild.id, user.id),
        )
        active_count = row["n"]

        # DM user
        await checks.try_dm(user, _dm_embed("warn", interaction.guild.name, reason, f"**Active warns:** {active_count}"))

        # Audit
        await _send_audit(
            self.bot, interaction.guild,
            _audit_embed("warn", user, interaction.user, reason, {"Strike": f"{active_count}/7"}),
        )
        event_push.push(
            "mod_warn",
            guild_id=interaction.guild.id, target_id=user.id, actor_id=interaction.user.id,
            details={"reason": reason, "active_warns": active_count},
        )

        # Auto-escalation
        escalation_msg = ""
        for threshold, action, td in WARN_ESCALATIONS:
            if active_count == threshold:
                try:
                    if action == "timeout":
                        await user.timeout(td, reason=f"Auto-escalation at {threshold} warns")
                        escalation_msg = f"AUTO-ESCALATION: TIMEOUT — {format_duration(td)}"
                        await checks.try_dm(user, _dm_embed("timeout", interaction.guild.name, f"Auto-escalation at {threshold} warns", f"**Duration:** {format_duration(td)}"))
                        await _send_audit(self.bot, interaction.guild, _audit_embed("timeout", user, interaction.guild.me, f"Auto: {threshold} warns", {"Duration": format_duration(td)}))
                    elif action == "kick":
                        await checks.try_dm(user, _dm_embed("kick", interaction.guild.name, f"Auto-kick at {threshold} warns"))
                        await user.kick(reason=f"Auto-kick at {threshold} warns")
                        escalation_msg = "AUTO-ESCALATION: KICK"
                        await _send_audit(self.bot, interaction.guild, _audit_embed("kick", user, interaction.guild.me, f"Auto: {threshold} warns"))
                except discord.HTTPException as e:
                    log.warning("auto-escalation failed: %s", e)
                break

        body = f"{strings.WARN_DONE.format(n=active_count)}"
        if escalation_msg:
            body += f"\n\n**{escalation_msg}**"
        await interaction.response.send_message(embed=embeds.warn(body), ephemeral=True)

    # ---- WARNS ------------------------------------------------------------
    @app_commands.command(name="warns", description="List a member's active warns.")
    @app_commands.describe(user="Member (default: yourself).", include_cleared="Include cleared warns.")
    async def warns(self, interaction: discord.Interaction, user: discord.Member | None = None, include_cleared: bool = False):
        target = user or interaction.user
        # Non-mods can only see their own.
        actor_can_mod = interaction.user.guild_permissions.moderate_members or interaction.user.id == interaction.guild.owner_id
        if target.id != interaction.user.id and not actor_can_mod:
            await interaction.response.send_message(embed=embeds.error("You can only view your own warns."), ephemeral=True)
            return

        if include_cleared:
            rows = await self.bot.db.fetchall(
                "SELECT id, reason, moderator_id, created_at, cleared_at FROM warns WHERE guild_id = $1 AND user_id = $2 ORDER BY created_at DESC",
                (interaction.guild.id, target.id),
            )
        else:
            rows = await self.bot.db.fetchall(
                "SELECT id, reason, moderator_id, created_at, cleared_at FROM warns WHERE guild_id = $1 AND user_id = $2 AND cleared_at IS NULL ORDER BY created_at DESC",
                (interaction.guild.id, target.id),
            )

        if not rows:
            await interaction.response.send_message(embed=embeds.info(f"NO {'WARNS' if include_cleared else 'ACTIVE WARNS'} — {target}"), ephemeral=True)
            return

        lines = []
        for r in rows[:25]:  # cap to fit one embed
            ts = f"<t:{r['created_at']}:R>"
            cleared = " · *cleared*" if r["cleared_at"] else ""
            lines.append(f"`#{r['id']}` · {ts} · {r['reason']}{cleared}")
        embed = embeds.warn(f"WARNS — {target}", "\n".join(lines))
        embed.set_footer(text=f"{config.BRAND_FOOTER} · {len(rows)} record(s)")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ---- CLEARWARNS -------------------------------------------------------
    @app_commands.command(name="clearwarns", description="Clear all active warns for a member (owner / admin only).")
    @app_commands.describe(user="Member whose warns to clear.", reason="Reason for the audit log.")
    @app_commands.default_permissions(administrator=True)
    async def clearwarns(self, interaction: discord.Interaction, user: discord.Member, reason: str = ""):
        result = await self.bot.db.execute(
            "UPDATE warns SET cleared_at = $1, cleared_by = $2 WHERE guild_id = $3 AND user_id = $4 AND cleared_at IS NULL",
            (int(time.time()), interaction.user.id, interaction.guild.id, user.id),
        )
        n = result.rowcount
        await _send_audit(self.bot, interaction.guild, _audit_embed("clearwarns", user, interaction.user, reason, {"Cleared": str(n)}))
        event_push.push("mod_clearwarns", guild_id=interaction.guild.id, target_id=user.id, actor_id=interaction.user.id, details={"cleared": n, "reason": reason})
        await interaction.response.send_message(embed=embeds.success(f"CLEARED {n} WARN(S) — {user}"), ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Moderation(bot))
