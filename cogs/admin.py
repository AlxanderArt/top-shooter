"""Owner-only admin / debug commands."""

import discord
from discord import app_commands
from discord.ext import commands

import config
from utils import embeds


def _is_owner(interaction: discord.Interaction) -> bool:
    return interaction.user.id == config.OWNER_ID


class Admin(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="dbstats", description="Owner-only — DB row counts.")
    async def dbstats(self, interaction: discord.Interaction):
        if not _is_owner(interaction):
            await interaction.response.send_message(
                embed=embeds.error("STAND DOWN. OWNER-ONLY COMMAND."),
                ephemeral=True,
            )
            return

        tables = [
            "schema_version", "guild_settings", "warns", "levels", "level_roles",
            "reaction_roles", "automod_rules", "temp_voice_config", "temp_voice_active",
            "recent_joins",
        ]
        lines = []
        for t in tables:
            row = await self.bot.db.fetchone(f"SELECT COUNT(*)::bigint AS n FROM {t}")
            lines.append(f"`{t:<22}` {row['n']:>6}")
        await interaction.response.send_message(
            embed=embeds.info("DB SNAPSHOT.", "\n".join(lines)),
            ephemeral=True,
        )

    @app_commands.command(name="reload", description="Owner-only — reload a cog.")
    @app_commands.describe(cog="Cog name (e.g. cogs.general)")
    async def reload(self, interaction: discord.Interaction, cog: str):
        if not _is_owner(interaction):
            await interaction.response.send_message(
                embed=embeds.error("STAND DOWN. OWNER-ONLY COMMAND."),
                ephemeral=True,
            )
            return
        try:
            await self.bot.reload_extension(cog)
            await interaction.response.send_message(
                embed=embeds.success(f"COG RELOADED — {cog}"),
                ephemeral=True,
            )
        except Exception as e:
            await interaction.response.send_message(
                embed=embeds.error(f"RELOAD FAILED — {type(e).__name__}: {e}"),
                ephemeral=True,
            )

    @app_commands.command(name="sync", description="Owner-only — re-sync slash commands to the dev guild.")
    async def sync(self, interaction: discord.Interaction):
        if not _is_owner(interaction):
            await interaction.response.send_message(
                embed=embeds.error("STAND DOWN. OWNER-ONLY COMMAND."),
                ephemeral=True,
            )
            return
        await interaction.response.defer(ephemeral=True)
        guild = discord.Object(id=config.DEV_GUILD_ID)
        self.bot.tree.copy_global_to(guild=guild)
        synced = await self.bot.tree.sync(guild=guild)
        await interaction.followup.send(
            embed=embeds.success(f"RESYNCED — {len(synced)} commands."),
            ephemeral=True,
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(Admin(bot))
