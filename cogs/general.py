import discord
from discord import app_commands
from discord.ext import commands

import config
from utils import embeds, strings


# ---------------------------------------------------------------------------
# /demo — button + select + modal showcase
# ---------------------------------------------------------------------------
class DemoModal(discord.ui.Modal):
    loadout = discord.ui.TextInput(
        label=strings.DEMO_MODAL_LABEL,
        placeholder=strings.DEMO_MODAL_PLACEHOLDER,
        style=discord.TextStyle.short,
        max_length=200,
        required=True,
    )

    def __init__(self):
        super().__init__(title=strings.DEMO_MODAL_TITLE)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.send_message(
            embed=embeds.success(strings.DEMO_MODAL_SUBMIT.format(value=self.loadout.value)),
            ephemeral=True,
        )


class DemoView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=120)

    @discord.ui.button(label=strings.DEMO_BUTTON_PRIMARY, style=discord.ButtonStyle.primary, row=0)
    async def press_me(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            embed=embeds.success(strings.DEMO_BUTTON_PRESSED),
            ephemeral=True,
        )

    @discord.ui.button(label=strings.DEMO_BUTTON_MODAL, style=discord.ButtonStyle.success, row=0)
    async def open_modal(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(DemoModal())

    @discord.ui.select(
        placeholder=strings.DEMO_SELECT_PLACEHOLDER,
        min_values=1,
        max_values=1,
        row=1,
        options=[
            discord.SelectOption(label="Tactical Black", description="#0A0A0A — the brand base.", emoji="⬛"),
            discord.SelectOption(label="Hi-Vis Orange", description="#FF5F1F — in-progress / accent.", emoji="🟧"),
            discord.SelectOption(label="Neon Green", description="#39FF14 — verified / earned-state.", emoji="🟩"),
        ],
    )
    async def pick_livery(self, interaction: discord.Interaction, select: discord.ui.Select):
        choice = select.values[0]
        await interaction.response.send_message(
            embed=embeds.success(strings.DEMO_SELECT_CHOSEN.format(choice=choice.upper())),
            ephemeral=True,
        )

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True


# ---------------------------------------------------------------------------
# /help — paginated command listing
# ---------------------------------------------------------------------------
class HelpView(discord.ui.View):
    def __init__(self, pages: list[discord.Embed], invoker_id: int):
        super().__init__(timeout=120)
        self.pages = pages
        self.index = 0
        self.invoker_id = invoker_id
        self._sync_buttons()

    def _sync_buttons(self):
        self.prev_btn.disabled = self.index == 0
        self.next_btn.disabled = self.index >= len(self.pages) - 1

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.invoker_id:
            await interaction.response.send_message(
                embed=embeds.warn("THIS HELP PAGE BELONGS TO ANOTHER OPERATOR."),
                ephemeral=True,
            )
            return False
        return True

    @discord.ui.button(label="◀", style=discord.ButtonStyle.secondary)
    async def prev_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.index = max(0, self.index - 1)
        self._sync_buttons()
        await interaction.response.edit_message(embed=self.pages[self.index], view=self)

    @discord.ui.button(label="▶", style=discord.ButtonStyle.secondary)
    async def next_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.index = min(len(self.pages) - 1, self.index + 1)
        self._sync_buttons()
        await interaction.response.edit_message(embed=self.pages[self.index], view=self)

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True


def _build_help_pages(bot: commands.Bot, per_page: int = 8) -> list[discord.Embed]:
    """Walk the slash-command tree and build paginated help embeds."""
    cmds: list[app_commands.Command] = []
    for c in bot.tree.walk_commands():
        if isinstance(c, app_commands.Command):
            cmds.append(c)
    cmds.sort(key=lambda c: c.qualified_name)

    if not cmds:
        return [embeds.info(strings.HELP_TITLE, "No commands registered yet.")]

    pages = []
    total_pages = (len(cmds) + per_page - 1) // per_page
    for page_idx in range(total_pages):
        chunk = cmds[page_idx * per_page : (page_idx + 1) * per_page]
        body_lines = []
        for c in chunk:
            body_lines.append(f"**/{c.qualified_name}** — {c.description or 'No description.'}")
        embed = embeds.brand(strings.HELP_TITLE, "\n".join(body_lines))
        embed.set_footer(text=f"{config.BRAND_FOOTER} · {strings.HELP_FOOTER_PAGE.format(current=page_idx + 1, total=total_pages)}")
        pages.append(embed)
    return pages


# ---------------------------------------------------------------------------
# Cog
# ---------------------------------------------------------------------------
class General(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="ping", description="Check bot latency.")
    async def ping(self, interaction: discord.Interaction):
        latency_ms = round(self.bot.latency * 1000)
        await interaction.response.send_message(
            embed=embeds.brand(strings.PING_REPLY.format(latency=latency_ms)),
            ephemeral=True,
        )

    @app_commands.command(name="demo", description="Showcase a button, dropdown, and modal in PKC voice.")
    async def demo(self, interaction: discord.Interaction):
        embed = embeds.brand(strings.DEMO_TITLE, strings.DEMO_BODY)
        await interaction.response.send_message(embed=embed, view=DemoView(), ephemeral=True)

    @app_commands.command(name="help", description="List every command Top Shooter responds to.")
    async def help_cmd(self, interaction: discord.Interaction):
        pages = _build_help_pages(self.bot)
        view = HelpView(pages, interaction.user.id) if len(pages) > 1 else None
        await interaction.response.send_message(embed=pages[0], view=view, ephemeral=True)

    @commands.command(name="ping")
    async def ping_prefix(self, ctx: commands.Context):
        latency_ms = round(self.bot.latency * 1000)
        await ctx.reply(
            embed=embeds.brand(strings.PING_REPLY.format(latency=latency_ms)),
            mention_author=False,
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(General(bot))
