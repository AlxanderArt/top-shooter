"""Phase 5 — Welcome / Leave cog.

Per-guild configurable welcome and leave messages with placeholder substitution.
Stored in guild_settings.{welcome_channel_id, welcome_message, leave_channel_id, leave_message}.

Placeholders supported in templates:
- {user}          → member display name
- {user.mention}  → member mention
- {user.id}       → numeric ID
- {server}        → guild name
- {member_count}  → guild member count
"""

import logging

import discord
from discord import app_commands
from discord.ext import commands

import config
from utils import embeds

log = logging.getLogger("topshooter.welcome")

PLACEHOLDER_HELP = "Placeholders: `{user}` `{user.mention}` `{user.id}` `{server}` `{member_count}`"

WELCOME_COLOR = 0xFF5F1F  # hi-vis orange — in-progress / onboarding state
LEAVE_COLOR = 0x3F4448    # anodized slate — neutral exit


def render(template: str, member: discord.Member) -> str:
    return (
        template
        .replace("{user.mention}", member.mention)
        .replace("{user.id}", str(member.id))
        .replace("{user}", member.display_name)
        .replace("{server}", member.guild.name)
        .replace("{member_count}", str(member.guild.member_count or 0))
    )


def welcome_embed(template: str, member: discord.Member) -> discord.Embed:
    embed = discord.Embed(
        title="NEW RECRUIT ON THE RANGE.",
        description=render(template, member),
        color=WELCOME_COLOR,
        timestamp=discord.utils.utcnow(),
    )
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.set_footer(text=f"{config.BRAND_FOOTER} · member #{member.guild.member_count}")
    return embed


def leave_embed(template: str, member: discord.Member) -> discord.Embed:
    embed = discord.Embed(
        title="OPERATOR STOOD DOWN.",
        description=render(template, member),
        color=LEAVE_COLOR,
        timestamp=discord.utils.utcnow(),
    )
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.set_footer(text=f"{config.BRAND_FOOTER}")
    return embed


# ---------------------------------------------------------------------------
class Welcome(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ---- /setwelcome ------------------------------------------------------
    @app_commands.command(name="setwelcome", description="Configure the welcome message for new joins.")
    @app_commands.describe(
        channel="Channel where the welcome message lands.",
        message="Message template (max 1900 chars). Supports placeholders.",
    )
    @app_commands.default_permissions(manage_guild=True)
    async def setwelcome(self, interaction: discord.Interaction, channel: discord.TextChannel, message: str):
        if len(message) > 1900:
            await interaction.response.send_message(
                embed=embeds.error("Message too long (max 1900 chars)."),
                ephemeral=True,
            )
            return
        await self.bot.db.execute(
            "INSERT INTO guild_settings (guild_id, welcome_channel_id, welcome_message) VALUES ($1, $2, $3) "
            "ON CONFLICT (guild_id) DO UPDATE SET welcome_channel_id = EXCLUDED.welcome_channel_id, welcome_message = EXCLUDED.welcome_message",
            (interaction.guild.id, channel.id, message),
        )
        await interaction.response.send_message(
            embed=embeds.success(f"WELCOME SET — {channel.mention}\n\n*{PLACEHOLDER_HELP}*\n\nPreview with `/welcomepreview`."),
            ephemeral=True,
        )

    @app_commands.command(name="clearwelcome", description="Disable the welcome message.")
    @app_commands.default_permissions(manage_guild=True)
    async def clearwelcome(self, interaction: discord.Interaction):
        await self.bot.db.execute(
            "UPDATE guild_settings SET welcome_channel_id = NULL, welcome_message = NULL WHERE guild_id = $1",
            (interaction.guild.id,),
        )
        await interaction.response.send_message(embed=embeds.success("WELCOME CLEARED."), ephemeral=True)

    # ---- /setleave --------------------------------------------------------
    @app_commands.command(name="setleave", description="Configure the leave message.")
    @app_commands.describe(
        channel="Channel where the leave message lands.",
        message="Message template (max 1900 chars). Supports placeholders.",
    )
    @app_commands.default_permissions(manage_guild=True)
    async def setleave(self, interaction: discord.Interaction, channel: discord.TextChannel, message: str):
        if len(message) > 1900:
            await interaction.response.send_message(
                embed=embeds.error("Message too long (max 1900 chars)."),
                ephemeral=True,
            )
            return
        await self.bot.db.execute(
            "INSERT INTO guild_settings (guild_id, leave_channel_id, leave_message) VALUES ($1, $2, $3) "
            "ON CONFLICT (guild_id) DO UPDATE SET leave_channel_id = EXCLUDED.leave_channel_id, leave_message = EXCLUDED.leave_message",
            (interaction.guild.id, channel.id, message),
        )
        await interaction.response.send_message(
            embed=embeds.success(f"LEAVE SET — {channel.mention}\n\n*{PLACEHOLDER_HELP}*\n\nPreview with `/leavepreview`."),
            ephemeral=True,
        )

    @app_commands.command(name="clearleave", description="Disable the leave message.")
    @app_commands.default_permissions(manage_guild=True)
    async def clearleave(self, interaction: discord.Interaction):
        await self.bot.db.execute(
            "UPDATE guild_settings SET leave_channel_id = NULL, leave_message = NULL WHERE guild_id = $1",
            (interaction.guild.id,),
        )
        await interaction.response.send_message(embed=embeds.success("LEAVE CLEARED."), ephemeral=True)

    # ---- /welcomepreview & /leavepreview ----------------------------------
    @app_commands.command(name="welcomepreview", description="Preview the welcome embed using your own profile.")
    async def welcomepreview(self, interaction: discord.Interaction):
        settings = await self.bot.db.get_guild_settings(interaction.guild.id)
        if not settings or not settings["welcome_message"]:
            await interaction.response.send_message(
                embed=embeds.info("NO WELCOME CONFIGURED.", "Use `/setwelcome` first."),
                ephemeral=True,
            )
            return
        await interaction.response.send_message(
            embed=welcome_embed(settings["welcome_message"], interaction.user),
            ephemeral=True,
        )

    @app_commands.command(name="leavepreview", description="Preview the leave embed using your own profile.")
    async def leavepreview(self, interaction: discord.Interaction):
        settings = await self.bot.db.get_guild_settings(interaction.guild.id)
        if not settings or not settings["leave_message"]:
            await interaction.response.send_message(
                embed=embeds.info("NO LEAVE CONFIGURED.", "Use `/setleave` first."),
                ephemeral=True,
            )
            return
        await interaction.response.send_message(
            embed=leave_embed(settings["leave_message"], interaction.user),
            ephemeral=True,
        )

    # ---- Listeners --------------------------------------------------------
    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        if member.bot:
            return
        settings = await self.bot.db.get_guild_settings(member.guild.id)
        if not settings:
            return
        ch_id, template = settings["welcome_channel_id"], settings["welcome_message"]
        if not (ch_id and template):
            return
        ch = member.guild.get_channel(ch_id)
        if not isinstance(ch, discord.TextChannel):
            return
        try:
            await ch.send(content=member.mention, embed=welcome_embed(template, member))
        except (discord.Forbidden, discord.HTTPException) as e:
            log.warning("welcome send failed: %s", e)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        if member.bot:
            return
        settings = await self.bot.db.get_guild_settings(member.guild.id)
        if not settings:
            return
        ch_id, template = settings["leave_channel_id"], settings["leave_message"]
        if not (ch_id and template):
            return
        ch = member.guild.get_channel(ch_id)
        if not isinstance(ch, discord.TextChannel):
            return
        try:
            await ch.send(embed=leave_embed(template, member))
        except (discord.Forbidden, discord.HTTPException) as e:
            log.warning("leave send failed: %s", e)


async def setup(bot: commands.Bot):
    await bot.add_cog(Welcome(bot))
