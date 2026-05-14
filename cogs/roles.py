"""Phase 6 — Roles cog.

Three role-management features:

1. **Auto-role**  — single role auto-granted on member join.
2. **Reaction roles** — reacting to a configured message grants a role; un-reacting revokes.
3. **Level roles** — bindings between Top Shooter XP levels and roles (Phase 7 consumes).

Storage:
- `guild_settings.autorole_id`        — single role id (or NULL).
- `reaction_roles(guild_id, message_id, emoji, role_id)` — composite-key bindings.
- `level_roles(guild_id, level, role_id)` — level threshold → role.
"""

import logging
import re

import discord
from discord import app_commands
from discord.ext import commands

from utils import embeds

log = logging.getLogger("topshooter.roles")

# Match Discord message links: https://discord.com/channels/<guild>/<channel>/<message>
MSG_LINK_RE = re.compile(
    r"https?://(?:canary\.|ptb\.)?discord\.com/channels/(\d+)/(\d+)/(\d+)"
)


def emoji_key(emoji: discord.PartialEmoji | discord.Emoji | str) -> str:
    """Canonical storage form for an emoji.

    Unicode emoji → the unicode literal.
    Custom emoji → `<:name:id>` or `<a:name:id>` for animated.
    Strings → returned verbatim.
    """
    if isinstance(emoji, str):
        return emoji
    if isinstance(emoji, (discord.PartialEmoji, discord.Emoji)):
        if emoji.id is None:
            return emoji.name
        prefix = "a" if getattr(emoji, "animated", False) else ""
        return f"<{prefix}:{emoji.name}:{emoji.id}>"
    return str(emoji)


def parse_emoji_input(s: str, guild: discord.Guild) -> discord.PartialEmoji | None:
    """Accept a unicode emoji, a `<:name:id>` literal, or a custom emoji name on this guild."""
    s = s.strip()
    if not s:
        return None
    m = re.match(r"<(a?):([A-Za-z0-9_]+):(\d+)>", s)
    if m:
        return discord.PartialEmoji(name=m.group(2), id=int(m.group(3)), animated=bool(m.group(1)))
    # Lookup by name in guild custom emojis
    for e in guild.emojis:
        if e.name == s:
            return discord.PartialEmoji(name=e.name, id=e.id, animated=e.animated)
    # Treat as unicode
    return discord.PartialEmoji(name=s, id=None)


# ---------------------------------------------------------------------------
class Roles(commands.Cog):
    autorole = app_commands.Group(name="autorole", description="Manage the role given to new joins.", default_permissions=discord.Permissions(manage_guild=True))
    reactionrole = app_commands.Group(name="reactionrole", description="Bind a role to a reaction on a message.", default_permissions=discord.Permissions(manage_roles=True))
    levelrole = app_commands.Group(name="levelrole", description="Bind roles to XP levels (Phase 7 grants them).", default_permissions=discord.Permissions(manage_roles=True))

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # =======================================================================
    # /autorole
    # =======================================================================
    @autorole.command(name="set", description="Set the role auto-applied to every new member.")
    @app_commands.describe(role="Role to grant on join.")
    async def autorole_set(self, interaction: discord.Interaction, role: discord.Role):
        bot_top = interaction.guild.me.top_role
        if role >= bot_top:
            await interaction.response.send_message(
                embed=embeds.error("That role sits at or above my top role — I can't grant it. Move my role up first."),
                ephemeral=True,
            )
            return
        if role.is_default():
            await interaction.response.send_message(
                embed=embeds.error("@everyone can't be assigned."),
                ephemeral=True,
            )
            return
        await self.bot.db.execute(
            "INSERT INTO guild_settings (guild_id, autorole_id) VALUES ($1, $2) "
            "ON CONFLICT (guild_id) DO UPDATE SET autorole_id = EXCLUDED.autorole_id",
            (interaction.guild.id, role.id),
        )
        await interaction.response.send_message(
            embed=embeds.success(f"AUTOROLE SET — every new member gets {role.mention}."),
            ephemeral=True,
        )

    @autorole.command(name="clear", description="Disable auto-role on join.")
    async def autorole_clear(self, interaction: discord.Interaction):
        await self.bot.db.execute(
            "UPDATE guild_settings SET autorole_id = NULL WHERE guild_id = $1",
            (interaction.guild.id,),
        )
        await interaction.response.send_message(embed=embeds.success("AUTOROLE CLEARED."), ephemeral=True)

    @autorole.command(name="show", description="Show the current auto-role.")
    async def autorole_show(self, interaction: discord.Interaction):
        settings = await self.bot.db.get_guild_settings(interaction.guild.id)
        if not settings or not settings["autorole_id"]:
            await interaction.response.send_message(embed=embeds.info("AUTOROLE: not set."), ephemeral=True)
            return
        role = interaction.guild.get_role(settings["autorole_id"])
        await interaction.response.send_message(
            embed=embeds.info(f"AUTOROLE: {role.mention if role else '*deleted role*'}"),
            ephemeral=True,
        )

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        if member.bot:
            return
        settings = await self.bot.db.get_guild_settings(member.guild.id)
        if not settings or not settings["autorole_id"]:
            return
        role = member.guild.get_role(settings["autorole_id"])
        if not role:
            return
        try:
            await member.add_roles(role, reason="autorole")
        except (discord.Forbidden, discord.HTTPException) as e:
            log.warning("autorole failed for %s: %s", member, e)

    # =======================================================================
    # /reactionrole
    # =======================================================================
    @reactionrole.command(name="create", description="Bind a role to a reaction on a message.")
    @app_commands.describe(
        message_link="Full Discord message URL (right-click message → Copy Message Link).",
        emoji="Unicode emoji, or `:name:` of a custom emoji on this server.",
        role="Role to grant when the emoji is reacted with.",
    )
    async def rr_create(self, interaction: discord.Interaction, message_link: str, emoji: str, role: discord.Role):
        m = MSG_LINK_RE.match(message_link.strip())
        if not m:
            await interaction.response.send_message(
                embed=embeds.error("Invalid message link. Right-click a message → Copy Message Link."),
                ephemeral=True,
            )
            return
        guild_id, channel_id, message_id = (int(x) for x in m.groups())
        if guild_id != interaction.guild.id:
            await interaction.response.send_message(
                embed=embeds.error("That message is in a different guild."),
                ephemeral=True,
            )
            return
        channel = interaction.guild.get_channel(channel_id)
        if not isinstance(channel, (discord.TextChannel, discord.Thread)):
            await interaction.response.send_message(
                embed=embeds.error("Channel not found or not a text channel."),
                ephemeral=True,
            )
            return
        try:
            target_message = await channel.fetch_message(message_id)
        except discord.NotFound:
            await interaction.response.send_message(embed=embeds.error("Message not found."), ephemeral=True)
            return
        except discord.Forbidden:
            await interaction.response.send_message(embed=embeds.error("I can't read that channel."), ephemeral=True)
            return

        if role >= interaction.guild.me.top_role:
            await interaction.response.send_message(
                embed=embeds.error("That role sits at or above my top role — I can't grant it."),
                ephemeral=True,
            )
            return
        if role.is_default():
            await interaction.response.send_message(embed=embeds.error("@everyone can't be assigned."), ephemeral=True)
            return

        pe = parse_emoji_input(emoji, interaction.guild)
        if pe is None:
            await interaction.response.send_message(embed=embeds.error("Invalid emoji."), ephemeral=True)
            return
        key = emoji_key(pe)

        # React on the message so users can see/copy the emoji.
        try:
            await target_message.add_reaction(pe)
        except discord.HTTPException as e:
            await interaction.response.send_message(
                embed=embeds.error(f"Couldn't react with that emoji — {e}"),
                ephemeral=True,
            )
            return

        await self.bot.db.execute(
            "INSERT INTO reaction_roles (guild_id, message_id, emoji, role_id) VALUES ($1, $2, $3, $4) "
            "ON CONFLICT (guild_id, message_id, emoji) DO UPDATE SET role_id = EXCLUDED.role_id",
            (interaction.guild.id, message_id, key, role.id),
        )

        await interaction.response.send_message(
            embed=embeds.success(
                f"REACTION ROLE BOUND.\n\n"
                f"**Message:** [jump]({target_message.jump_url}) in {channel.mention}\n"
                f"**Emoji:** {pe}\n"
                f"**Role:** {role.mention}"
            ),
            ephemeral=True,
        )

    @reactionrole.command(name="remove", description="Remove a reaction-role binding.")
    @app_commands.describe(message_link="The message URL.", emoji="The emoji whose binding to remove.")
    async def rr_remove(self, interaction: discord.Interaction, message_link: str, emoji: str):
        m = MSG_LINK_RE.match(message_link.strip())
        if not m:
            await interaction.response.send_message(embed=embeds.error("Invalid message link."), ephemeral=True)
            return
        _, _, message_id = (int(x) for x in m.groups())
        pe = parse_emoji_input(emoji, interaction.guild)
        if pe is None:
            await interaction.response.send_message(embed=embeds.error("Invalid emoji."), ephemeral=True)
            return
        key = emoji_key(pe)
        cur = await self.bot.db.execute(
            "DELETE FROM reaction_roles WHERE guild_id = $1 AND message_id = $2 AND emoji = $3",
            (interaction.guild.id, message_id, key),
        )
        if cur.rowcount == 0:
            await interaction.response.send_message(embed=embeds.info("No binding existed."), ephemeral=True)
            return
        await interaction.response.send_message(embed=embeds.success("REACTION ROLE REMOVED."), ephemeral=True)

    @reactionrole.command(name="list", description="List all reaction-role bindings on this server.")
    async def rr_list(self, interaction: discord.Interaction):
        rows = await self.bot.db.fetchall(
            "SELECT message_id, emoji, role_id FROM reaction_roles WHERE guild_id = $1 ORDER BY message_id, emoji",
            (interaction.guild.id,),
        )
        if not rows:
            await interaction.response.send_message(embed=embeds.info("No reaction-role bindings yet."), ephemeral=True)
            return
        lines = []
        for r in rows[:40]:
            role = interaction.guild.get_role(r["role_id"])
            role_str = role.mention if role else f"*deleted role id `{r['role_id']}`*"
            lines.append(f"`msg:{r['message_id']}` · {r['emoji']} → {role_str}")
        await interaction.response.send_message(
            embed=embeds.info("REACTION ROLE BINDINGS.", "\n".join(lines)),
            ephemeral=True,
        )

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        if payload.guild_id is None or payload.user_id == self.bot.user.id:
            return
        key = emoji_key(payload.emoji)
        row = await self.bot.db.fetchone(
            "SELECT role_id FROM reaction_roles WHERE guild_id = $1 AND message_id = $2 AND emoji = $3",
            (payload.guild_id, payload.message_id, key),
        )
        if not row:
            return
        guild = self.bot.get_guild(payload.guild_id)
        if not guild:
            return
        member = guild.get_member(payload.user_id) or await guild.fetch_member(payload.user_id)
        if not member or member.bot:
            return
        role = guild.get_role(row["role_id"])
        if not role:
            return
        if role >= guild.me.top_role:
            log.warning("reaction-role %s above bot top role, skipping grant", role)
            return
        try:
            await member.add_roles(role, reason="reaction-role")
        except (discord.Forbidden, discord.HTTPException) as e:
            log.warning("reaction-role add failed: %s", e)

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent):
        if payload.guild_id is None:
            return
        key = emoji_key(payload.emoji)
        row = await self.bot.db.fetchone(
            "SELECT role_id FROM reaction_roles WHERE guild_id = $1 AND message_id = $2 AND emoji = $3",
            (payload.guild_id, payload.message_id, key),
        )
        if not row:
            return
        guild = self.bot.get_guild(payload.guild_id)
        if not guild:
            return
        member = guild.get_member(payload.user_id)
        if not member or member.bot:
            return
        role = guild.get_role(row["role_id"])
        if not role:
            return
        try:
            await member.remove_roles(role, reason="reaction-role removed")
        except (discord.Forbidden, discord.HTTPException) as e:
            log.warning("reaction-role remove failed: %s", e)

    # =======================================================================
    # /levelrole (storage only; Phase 7 grants when a member levels up)
    # =======================================================================
    @levelrole.command(name="set", description="Bind a role to a Top Shooter XP level.")
    @app_commands.describe(level="XP level (≥ 1) that grants the role.", role="Role to grant at that level.")
    async def lr_set(self, interaction: discord.Interaction, level: app_commands.Range[int, 1, 1000], role: discord.Role):
        if role >= interaction.guild.me.top_role:
            await interaction.response.send_message(
                embed=embeds.error("Role sits at or above my top role. Move me up first."),
                ephemeral=True,
            )
            return
        if role.is_default():
            await interaction.response.send_message(embed=embeds.error("@everyone can't be a level role."), ephemeral=True)
            return
        await self.bot.db.execute(
            "INSERT INTO level_roles (guild_id, level, role_id) VALUES ($1, $2, $3) "
            "ON CONFLICT (guild_id, level) DO UPDATE SET role_id = EXCLUDED.role_id",
            (interaction.guild.id, level, role.id),
        )
        await interaction.response.send_message(
            embed=embeds.success(f"LEVEL ROLE SET — Level {level} → {role.mention}\n\nPhase 7 (levels) will grant it automatically once that cog ships."),
            ephemeral=True,
        )

    @levelrole.command(name="remove", description="Remove the role binding for a level.")
    @app_commands.describe(level="XP level whose binding to remove.")
    async def lr_remove(self, interaction: discord.Interaction, level: app_commands.Range[int, 1, 1000]):
        cur = await self.bot.db.execute(
            "DELETE FROM level_roles WHERE guild_id = $1 AND level = $2",
            (interaction.guild.id, level),
        )
        if cur.rowcount == 0:
            await interaction.response.send_message(embed=embeds.info("No binding at that level."), ephemeral=True)
            return
        await interaction.response.send_message(embed=embeds.success(f"LEVEL {level} BINDING REMOVED."), ephemeral=True)

    @levelrole.command(name="list", description="List all level-role bindings.")
    async def lr_list(self, interaction: discord.Interaction):
        rows = await self.bot.db.fetchall(
            "SELECT level, role_id FROM level_roles WHERE guild_id = $1 ORDER BY level",
            (interaction.guild.id,),
        )
        if not rows:
            await interaction.response.send_message(embed=embeds.info("No level-role bindings yet."), ephemeral=True)
            return
        lines = []
        for r in rows:
            role = interaction.guild.get_role(r["role_id"])
            role_str = role.mention if role else f"*deleted role id `{r['role_id']}`*"
            lines.append(f"Level **{r['level']}** → {role_str}")
        await interaction.response.send_message(
            embed=embeds.info("LEVEL ROLE BINDINGS.", "\n".join(lines)),
            ephemeral=True,
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(Roles(bot))
