"""Phase 4 — Audit logging cog.

Routes server events to a configurable audit-log channel.

Logged events:
- Member join / leave
- Message edit / delete (non-bot messages)
- Member update (role added/removed, nickname, timeout state)
- External moderation actions (kick/ban/unban not done by this bot)

The moderation cog (Phase 3) already audit-logs its own actions, so this cog
skips bot-initiated audit-log entries to avoid duplicates.

/setlog <channel> writes the audit channel into guild_settings.log_channel_id.
"""

import logging

import discord
from discord import app_commands
from discord.ext import commands

import config
from utils import embeds, event_push

log = logging.getLogger("topshooter.audit")

COLOR_JOIN = 0x39FF14       # neon green
COLOR_LEAVE = 0xFF1F1F      # alarm red
COLOR_EDIT = 0xFF5F1F       # hi-vis orange
COLOR_DELETE = 0xFF1F1F     # alarm red
COLOR_UPDATE = 0x3F4448     # slate
COLOR_BAN = 0xFF1F1F
COLOR_UNBAN = 0x39FF14
COLOR_KICK = 0xFF1F1F


async def _get_log_channel(bot: commands.Bot, guild: discord.Guild) -> discord.TextChannel | None:
    settings = await bot.db.get_guild_settings(guild.id)
    if settings and settings["log_channel_id"]:
        ch = guild.get_channel(settings["log_channel_id"])
        if isinstance(ch, discord.TextChannel):
            return ch
    return discord.utils.get(guild.text_channels, name="audit-log")


async def _send(bot: commands.Bot, guild: discord.Guild, embed: discord.Embed) -> None:
    ch = await _get_log_channel(bot, guild)
    if not ch:
        return
    try:
        await ch.send(embed=embed)
    except (discord.Forbidden, discord.HTTPException) as e:
        log.warning("audit send failed: %s", e)


def _base_embed(title: str, color: int) -> discord.Embed:
    embed = discord.Embed(title=title, color=color, timestamp=discord.utils.utcnow())
    embed.set_footer(text=config.BRAND_FOOTER)
    return embed


# ---------------------------------------------------------------------------
# Cog
# ---------------------------------------------------------------------------
class AuditLog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ---- /setlog ----------------------------------------------------------
    @app_commands.command(name="setlog", description="Set the audit-log channel for this server.")
    @app_commands.describe(channel="Text channel where audit events should be posted.")
    @app_commands.default_permissions(manage_guild=True)
    async def setlog(self, interaction: discord.Interaction, channel: discord.TextChannel):
        await self.bot.db.execute(
            "INSERT INTO guild_settings (guild_id, log_channel_id) VALUES ($1, $2) "
            "ON CONFLICT (guild_id) DO UPDATE SET log_channel_id = EXCLUDED.log_channel_id",
            (interaction.guild.id, channel.id),
        )
        await interaction.response.send_message(
            embed=embeds.success(f"AUDIT LOG SET — {channel.mention}"),
            ephemeral=True,
        )

    # ---- Member join ------------------------------------------------------
    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        embed = _base_embed(f"[JOIN] · {member}", COLOR_JOIN)
        embed.description = f"{member.mention} entered the range."
        embed.add_field(name="Account created", value=f"<t:{int(member.created_at.timestamp())}:R>", inline=True)
        embed.add_field(name="User ID", value=f"`{member.id}`", inline=True)
        embed.set_thumbnail(url=member.display_avatar.url)
        await _send(self.bot, member.guild, embed)
        event_push.push(
            "member_join",
            guild_id=member.guild.id,
            target_id=member.id,
            details={"name": member.name, "is_bot": member.bot},
        )

    # ---- Member remove ----------------------------------------------------
    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        # If a kick/ban audit entry exists in the last few seconds for this user,
        # skip the LEAVE log — the action's audit entry already covers it.
        try:
            now = discord.utils.utcnow().timestamp()
            async for entry in member.guild.audit_logs(limit=5, action=discord.AuditLogAction.kick):
                if entry.target and entry.target.id == member.id and (now - entry.created_at.timestamp()) < 10:
                    return
            async for entry in member.guild.audit_logs(limit=5, action=discord.AuditLogAction.ban):
                if entry.target and entry.target.id == member.id and (now - entry.created_at.timestamp()) < 10:
                    return
        except discord.Forbidden:
            pass

        embed = _base_embed(f"[LEAVE] · {member}", COLOR_LEAVE)
        embed.description = f"{member.mention} stood down."
        roles_text = ", ".join(r.name for r in member.roles[1:]) or "@everyone only"
        embed.add_field(name="Roles at exit", value=roles_text[:1024], inline=False)
        embed.add_field(name="User ID", value=f"`{member.id}`", inline=True)
        embed.add_field(name="Joined", value=f"<t:{int(member.joined_at.timestamp())}:R>" if member.joined_at else "*unknown*", inline=True)
        embed.set_thumbnail(url=member.display_avatar.url)
        await _send(self.bot, member.guild, embed)
        event_push.push(
            "member_leave",
            guild_id=member.guild.id,
            target_id=member.id,
            details={"name": member.name, "roles": [r.name for r in member.roles[1:]]},
        )

    # ---- Message edit -----------------------------------------------------
    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        if before.guild is None or before.author.bot or before.content == after.content:
            return
        embed = _base_embed(f"[EDIT] · {before.author}", COLOR_EDIT)
        embed.description = f"In {before.channel.mention} · [jump]({after.jump_url})"
        before_txt = before.content[:1024] if before.content else "*empty*"
        after_txt = after.content[:1024] if after.content else "*empty*"
        embed.add_field(name="Before", value=before_txt, inline=False)
        embed.add_field(name="After", value=after_txt, inline=False)
        embed.set_footer(text=f"{config.BRAND_FOOTER} · author id `{before.author.id}`")
        await _send(self.bot, before.guild, embed)
        event_push.push(
            "message_edit",
            guild_id=before.guild.id,
            target_id=before.author.id,
            details={
                "channel_id": before.channel.id,
                "message_id": before.id,
                "before": before.content[:500],
                "after": after.content[:500],
            },
        )

    # ---- Message delete ---------------------------------------------------
    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        if message.guild is None or message.author.bot:
            return
        embed = _base_embed(f"[DELETE] · {message.author}", COLOR_DELETE)
        embed.description = f"In {message.channel.mention}"
        if message.content:
            embed.add_field(name="Content", value=message.content[:1024], inline=False)
        if message.attachments:
            embed.add_field(
                name="Attachments",
                value=", ".join(f"`{a.filename}`" for a in message.attachments)[:1024],
                inline=False,
            )
        embed.set_footer(text=f"{config.BRAND_FOOTER} · author id `{message.author.id}`")
        await _send(self.bot, message.guild, embed)
        event_push.push(
            "message_delete",
            guild_id=message.guild.id,
            target_id=message.author.id,
            details={
                "channel_id": message.channel.id,
                "message_id": message.id,
                "content": (message.content or "")[:500],
            },
        )

    # ---- Member update (roles / nick / timeout) ---------------------------
    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        changes = []
        added = [r for r in after.roles if r not in before.roles]
        removed = [r for r in before.roles if r not in after.roles]
        if added:
            changes.append(f"**Role added:** {', '.join(r.mention for r in added)}")
        if removed:
            changes.append(f"**Role removed:** {', '.join(r.mention for r in removed)}")
        if before.nick != after.nick:
            changes.append(
                f"**Nickname:** `{before.nick or before.name}` → `{after.nick or after.name}`"
            )
        if before.timed_out_until != after.timed_out_until:
            if after.timed_out_until:
                changes.append(f"**Timeout:** until <t:{int(after.timed_out_until.timestamp())}:R>")
            else:
                changes.append("**Timeout:** lifted")
        if not changes:
            return
        embed = _base_embed(f"[MEMBER UPDATE] · {after}", COLOR_UPDATE)
        embed.description = "\n".join(changes)
        embed.set_footer(text=f"{config.BRAND_FOOTER} · user id `{after.id}`")
        await _send(self.bot, after.guild, embed)

    # ---- External moderation actions via Discord audit-log gateway ---------
    @commands.Cog.listener()
    async def on_audit_log_entry_create(self, entry: discord.AuditLogEntry):
        # Skip our own bot actions — moderation cog handles those.
        if entry.user_id == self.bot.user.id:
            return

        action_map = {
            discord.AuditLogAction.ban: ("BAN", COLOR_BAN),
            discord.AuditLogAction.unban: ("UNBAN", COLOR_UNBAN),
            discord.AuditLogAction.kick: ("KICK", COLOR_KICK),
        }
        pair = action_map.get(entry.action)
        if not pair:
            return  # not an action we route through here

        name, color = pair
        target_str = f"`{entry.target_id}`"
        try:
            if entry.target:
                target_str = f"{entry.target} (`{entry.target.id}`)"
        except Exception:
            pass

        actor = entry.user
        actor_str = f"{actor.mention} (`{actor.id}`)" if actor else f"`{entry.user_id}`"

        embed = _base_embed(f"[{name}] · external", color)
        embed.description = (
            f"**Target:** {target_str}\n"
            f"**By:** {actor_str}\n"
            f"**Reason:** {entry.reason or '*none*'}"
        )
        embed.set_footer(text=f"{config.BRAND_FOOTER} · source: Discord audit log")
        await _send(self.bot, entry.guild, embed)
        event_push.push(
            f"external_{name.lower()}",
            guild_id=entry.guild.id,
            target_id=entry.target_id,
            actor_id=entry.user_id,
            details={"reason": entry.reason},
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(AuditLog(bot))
