"""Phase 9 — Channel management cog.

Slash commands wrapped around Discord's create/delete APIs with a confirmation
button gate on every destructive action.

Commands (all gated by `manage_channels`):
- /channel create <name> <type> [category]
- /channel delete <channel>             — confirmation required
- /category create <name>
- /category delete <category>           — confirmation required (and channels inside are deleted with it)
- /thread create <name> [auto_archive]  — creates a thread in the current channel
"""

import logging

import discord
from discord import app_commands
from discord.ext import commands

import config
from utils import embeds

log = logging.getLogger("topshooter.channels")


TYPE_MAP = {
    "text": discord.ChannelType.text,
    "voice": discord.ChannelType.voice,
    "stage": discord.ChannelType.stage_voice,
    "announcement": discord.ChannelType.news,
}


# ---------------------------------------------------------------------------
# Confirmation button view
# ---------------------------------------------------------------------------
class ConfirmDeleteView(discord.ui.View):
    """One-shot confirmation buttons. Locked to the invoking user. 60-sec timeout."""

    def __init__(self, invoker_id: int):
        super().__init__(timeout=60)
        self.invoker_id = invoker_id
        self.confirmed: bool | None = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.invoker_id:
            await interaction.response.send_message(
                embed=embeds.warn("STAND DOWN. THAT BUTTON ISN'T YOURS."),
                ephemeral=True,
            )
            return False
        return True

    @discord.ui.button(label="CONFIRM DELETE", style=discord.ButtonStyle.danger)
    async def confirm_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.confirmed = True
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(view=self)
        self.stop()

    @discord.ui.button(label="CANCEL", style=discord.ButtonStyle.secondary)
    async def cancel_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.confirmed = False
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(
            embed=embeds.info("CANCELLED. NO CHANGES."),
            view=self,
        )
        self.stop()

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True


# ---------------------------------------------------------------------------
class Channels(commands.Cog):
    channel_group = app_commands.Group(
        name="channel",
        description="Create or delete channels.",
        default_permissions=discord.Permissions(manage_channels=True),
    )
    category_group = app_commands.Group(
        name="category",
        description="Create or delete categories.",
        default_permissions=discord.Permissions(manage_channels=True),
    )
    thread_group = app_commands.Group(
        name="thread",
        description="Create threads.",
        default_permissions=discord.Permissions(manage_channels=True),
    )

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # =======================================================================
    # /channel create
    # =======================================================================
    @channel_group.command(name="create", description="Create a channel.")
    @app_commands.describe(
        name="Channel name (lowercase, dashes allowed).",
        type="Channel type.",
        category="Category to place it under (optional).",
        topic="Channel topic (text/announcement only).",
    )
    @app_commands.choices(type=[
        app_commands.Choice(name="text", value="text"),
        app_commands.Choice(name="voice", value="voice"),
        app_commands.Choice(name="stage", value="stage"),
        app_commands.Choice(name="announcement", value="announcement"),
    ])
    async def channel_create(
        self,
        interaction: discord.Interaction,
        name: str,
        type: app_commands.Choice[str],
        category: discord.CategoryChannel | None = None,
        topic: str | None = None,
    ):
        ch_type = TYPE_MAP[type.value]
        try:
            if ch_type == discord.ChannelType.text:
                ch = await interaction.guild.create_text_channel(
                    name=name, category=category, topic=topic or "", reason=f"By {interaction.user}"
                )
            elif ch_type == discord.ChannelType.voice:
                ch = await interaction.guild.create_voice_channel(
                    name=name, category=category, reason=f"By {interaction.user}"
                )
            elif ch_type == discord.ChannelType.stage_voice:
                ch = await interaction.guild.create_stage_channel(
                    name=name, category=category, reason=f"By {interaction.user}"
                )
            elif ch_type == discord.ChannelType.news:
                ch = await interaction.guild.create_text_channel(
                    name=name, category=category, topic=topic or "", reason=f"By {interaction.user}"
                )
                try:
                    await ch.edit(type=discord.ChannelType.news)
                except discord.HTTPException as e:
                    await interaction.response.send_message(
                        embed=embeds.warn(
                            f"CHANNEL CREATED, BUT ANNOUNCEMENT CONVERSION FAILED — {e}. "
                            "Community feature must be enabled for announcement channels."
                        ),
                        ephemeral=True,
                    )
                    return
        except discord.HTTPException as e:
            await interaction.response.send_message(
                embed=embeds.error(f"CREATE FAILED — {e}"),
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            embed=embeds.success(
                f"CHANNEL CREATED — {ch.mention} ({type.value})"
                + (f" under **{category.name}**" if category else "")
            ),
            ephemeral=True,
        )

    # =======================================================================
    # /channel delete
    # =======================================================================
    @channel_group.command(name="delete", description="Delete a channel. Requires confirmation.")
    @app_commands.describe(channel="Channel to delete.")
    async def channel_delete(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel | discord.VoiceChannel | discord.StageChannel | discord.ForumChannel,
    ):
        # Don't allow deleting the channel the command was invoked in (loses the response).
        if channel.id == interaction.channel_id:
            await interaction.response.send_message(
                embed=embeds.error("Can't delete the channel you're invoking from. Run this from a different channel."),
                ephemeral=True,
            )
            return

        view = ConfirmDeleteView(interaction.user.id)
        warning = embeds.warn(
            "CONFIRM DELETION.",
            f"You're about to permanently delete **#{channel.name}**. "
            "This wipes the channel and all its messages. **Cannot be undone.**",
        )
        await interaction.response.send_message(embed=warning, view=view, ephemeral=True)

        await view.wait()
        if view.confirmed is not True:
            return

        try:
            await channel.delete(reason=f"By {interaction.user}")
        except discord.HTTPException as e:
            await interaction.followup.send(
                embed=embeds.error(f"DELETE FAILED — {e}"),
                ephemeral=True,
            )
            return
        await interaction.followup.send(
            embed=embeds.success(f"CHANNEL DELETED — `#{channel.name}`"),
            ephemeral=True,
        )

    # =======================================================================
    # /category create
    # =======================================================================
    @category_group.command(name="create", description="Create a category.")
    @app_commands.describe(name="Category name.")
    async def category_create(self, interaction: discord.Interaction, name: str):
        try:
            cat = await interaction.guild.create_category(name=name, reason=f"By {interaction.user}")
        except discord.HTTPException as e:
            await interaction.response.send_message(
                embed=embeds.error(f"CREATE FAILED — {e}"),
                ephemeral=True,
            )
            return
        await interaction.response.send_message(
            embed=embeds.success(f"CATEGORY CREATED — **{cat.name}**"),
            ephemeral=True,
        )

    # =======================================================================
    # /category delete
    # =======================================================================
    @category_group.command(name="delete", description="Delete a category and all channels inside it. Requires confirmation.")
    @app_commands.describe(category="Category to delete.")
    async def category_delete(self, interaction: discord.Interaction, category: discord.CategoryChannel):
        if interaction.channel and interaction.channel.category_id == category.id:
            await interaction.response.send_message(
                embed=embeds.error("Can't delete the category that contains the channel you're invoking from."),
                ephemeral=True,
            )
            return

        child_count = len(category.channels)
        view = ConfirmDeleteView(interaction.user.id)
        warning = embeds.warn(
            "CONFIRM DELETION.",
            f"You're about to permanently delete category **{category.name}** "
            f"AND its **{child_count}** channel(s). **Cannot be undone.**",
        )
        await interaction.response.send_message(embed=warning, view=view, ephemeral=True)

        await view.wait()
        if view.confirmed is not True:
            return

        # Delete child channels first
        for ch in list(category.channels):
            try:
                await ch.delete(reason=f"By {interaction.user} (category delete)")
            except discord.HTTPException as e:
                log.warning("child delete failed: %s", e)

        try:
            await category.delete(reason=f"By {interaction.user}")
        except discord.HTTPException as e:
            await interaction.followup.send(
                embed=embeds.error(f"DELETE FAILED — {e}"),
                ephemeral=True,
            )
            return
        await interaction.followup.send(
            embed=embeds.success(f"CATEGORY DELETED — **{category.name}** ({child_count} channels)"),
            ephemeral=True,
        )

    # =======================================================================
    # /thread create
    # =======================================================================
    @thread_group.command(name="create", description="Create a thread in the current channel.")
    @app_commands.describe(
        name="Thread name.",
        auto_archive="Auto-archive duration.",
        private="Make this a private thread (only invited members can see).",
    )
    @app_commands.choices(auto_archive=[
        app_commands.Choice(name="1h", value=60),
        app_commands.Choice(name="24h", value=1440),
        app_commands.Choice(name="3d", value=4320),
        app_commands.Choice(name="7d", value=10080),
    ])
    async def thread_create(
        self,
        interaction: discord.Interaction,
        name: str,
        auto_archive: app_commands.Choice[int] | None = None,
        private: bool = False,
    ):
        if not isinstance(interaction.channel, discord.TextChannel):
            await interaction.response.send_message(
                embed=embeds.error("Threads can only be created from text channels."),
                ephemeral=True,
            )
            return

        archive_min = auto_archive.value if auto_archive else 1440
        try:
            thread = await interaction.channel.create_thread(
                name=name,
                auto_archive_duration=archive_min,
                type=discord.ChannelType.private_thread if private else discord.ChannelType.public_thread,
                reason=f"By {interaction.user}",
            )
        except discord.HTTPException as e:
            await interaction.response.send_message(
                embed=embeds.error(f"THREAD CREATE FAILED — {e}"),
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            embed=embeds.success(
                f"THREAD CREATED — {thread.mention}\n"
                f"**Archive:** {auto_archive.name if auto_archive else '24h'}"
                + (" · **Private**" if private else "")
            ),
            ephemeral=True,
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(Channels(bot))
