"""Phase 10 — Temp voice cog.

Join-to-create voice channels. One guild-wide configuration:

    /tempvoice setup <trigger_channel> [category] [name_template]
    /tempvoice teardown
    /tempvoice status

The trigger channel is a voice channel. When a member joins it, the bot:
1. Creates a new voice channel under the configured category, named via the
   template (default: `{user}'s VC`).
2. Grants the member channel-manage / mute / move perms on that channel so
   they can rename it, set a user limit, kick people, etc.
3. Moves the member into the new channel.
4. Records the channel in `temp_voice_active`.

When the last member leaves a tracked temp channel, the bot deletes it and
clears the row.

On cog load, orphan cleanup: any tracked channel that's empty or missing is
swept.
"""

import logging
import time

import discord
from discord import app_commands
from discord.ext import commands

import config
from utils import embeds

log = logging.getLogger("topshooter.tempvoice")


def _render_name(template: str, member: discord.Member) -> str:
    name = (
        template
        .replace("{user.mention}", member.mention)  # rare but supported
        .replace("{user.id}", str(member.id))
        .replace("{user}", member.display_name)
    )
    return name[:100]  # Discord channel-name max


# ---------------------------------------------------------------------------
class TempVoice(commands.Cog):
    tempvoice_group = app_commands.Group(
        name="tempvoice",
        description="Join-to-create voice channel system.",
        default_permissions=discord.Permissions(manage_guild=True),
    )

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_load(self):
        # Defer orphan cleanup until the bot is fully ready (guild caches populated).
        self.bot.loop.create_task(self._orphan_cleanup_on_ready())

    async def _orphan_cleanup_on_ready(self):
        await self.bot.wait_until_ready()
        try:
            rows = await self.bot.db.fetchall("SELECT channel_id, guild_id FROM temp_voice_active")
        except Exception as e:
            log.warning("orphan cleanup query failed: %s", e)
            return
        cleaned = 0
        for r in rows:
            guild = self.bot.get_guild(r["guild_id"])
            if not guild:
                await self.bot.db.execute(
                    "DELETE FROM temp_voice_active WHERE channel_id = $1",
                    (r["channel_id"],),
                )
                cleaned += 1
                continue
            ch = guild.get_channel(r["channel_id"])
            if not isinstance(ch, discord.VoiceChannel) or len(ch.members) == 0:
                if isinstance(ch, discord.VoiceChannel):
                    try:
                        await ch.delete(reason="temp voice orphan cleanup")
                    except discord.HTTPException as e:
                        log.warning("orphan delete failed: %s", e)
                await self.bot.db.execute(
                    "DELETE FROM temp_voice_active WHERE channel_id = $1",
                    (r["channel_id"],),
                )
                cleaned += 1
        if cleaned:
            log.info("temp voice orphan cleanup: %d row(s) removed", cleaned)

    # =======================================================================
    # /tempvoice setup
    # =======================================================================
    @tempvoice_group.command(name="setup", description="Configure the join-to-create trigger channel.")
    @app_commands.describe(
        trigger_channel="Voice channel that, when joined, spawns a temp voice channel.",
        category="Category to place temp channels under (default: trigger's category).",
        name_template="Name template. Supports {user}, {user.id}. Default: \"{user}'s VC\"",
    )
    async def setup_cmd(
        self,
        interaction: discord.Interaction,
        trigger_channel: discord.VoiceChannel,
        category: discord.CategoryChannel | None = None,
        name_template: str = "{user}'s VC",
    ):
        cat_id = (category or trigger_channel.category).id if (category or trigger_channel.category) else None
        if cat_id is None:
            await interaction.response.send_message(
                embed=embeds.error("Trigger channel is not in a category and no category was given."),
                ephemeral=True,
            )
            return
        await self.bot.db.execute(
            "INSERT INTO temp_voice_config (guild_id, category_id, trigger_channel_id, name_template) "
            "VALUES ($1, $2, $3, $4) "
            "ON CONFLICT (guild_id) DO UPDATE SET "
            "    category_id = EXCLUDED.category_id, "
            "    trigger_channel_id = EXCLUDED.trigger_channel_id, "
            "    name_template = EXCLUDED.name_template",
            (interaction.guild.id, cat_id, trigger_channel.id, name_template),
        )

        category_obj = interaction.guild.get_channel(cat_id)
        await interaction.response.send_message(
            embed=embeds.success(
                f"TEMP VOICE ARMED.\n\n"
                f"**Trigger:** {trigger_channel.mention}\n"
                f"**Category:** **{category_obj.name if category_obj else cat_id}**\n"
                f"**Name template:** `{name_template}`"
            ),
            ephemeral=True,
        )

    # =======================================================================
    # /tempvoice teardown
    # =======================================================================
    @tempvoice_group.command(name="teardown", description="Disable temp voice. Active temp channels stay alive until empty.")
    async def teardown_cmd(self, interaction: discord.Interaction):
        cur = await self.bot.db.execute(
            "DELETE FROM temp_voice_config WHERE guild_id = $1",
            (interaction.guild.id,),
        )
        if cur.rowcount == 0:
            await interaction.response.send_message(
                embed=embeds.info("Temp voice wasn't configured."),
                ephemeral=True,
            )
            return
        await interaction.response.send_message(
            embed=embeds.success("TEMP VOICE DISARMED. Existing temp channels persist until empty."),
            ephemeral=True,
        )

    # =======================================================================
    # /tempvoice status
    # =======================================================================
    @tempvoice_group.command(name="status", description="Show current temp voice configuration.")
    async def status_cmd(self, interaction: discord.Interaction):
        cfg = await self.bot.db.fetchone(
            "SELECT category_id, trigger_channel_id, name_template FROM temp_voice_config WHERE guild_id = $1",
            (interaction.guild.id,),
        )
        active = await self.bot.db.fetchall(
            "SELECT channel_id, owner_id, created_at FROM temp_voice_active WHERE guild_id = $1",
            (interaction.guild.id,),
        )
        if not cfg:
            await interaction.response.send_message(
                embed=embeds.info("TEMP VOICE: not configured. Use `/tempvoice setup`."),
                ephemeral=True,
            )
            return
        trigger = interaction.guild.get_channel(cfg["trigger_channel_id"])
        category = interaction.guild.get_channel(cfg["category_id"])
        lines = [
            f"**Trigger:** {trigger.mention if trigger else '*deleted*'}",
            f"**Category:** **{category.name if category else '*deleted*'}**",
            f"**Name template:** `{cfg['name_template']}`",
            f"**Active temp channels:** {len(active)}",
        ]
        if active:
            for a in active[:10]:
                ch = interaction.guild.get_channel(a["channel_id"])
                owner = interaction.guild.get_member(a["owner_id"])
                ch_str = ch.mention if ch else f"`{a['channel_id']}`"
                owner_str = owner.mention if owner else f"`{a['owner_id']}`"
                lines.append(f"  · {ch_str} — owner {owner_str} · <t:{a['created_at']}:R>")
        await interaction.response.send_message(
            embed=embeds.info("TEMP VOICE STATUS.", "\n".join(lines)),
            ephemeral=True,
        )

    # =======================================================================
    # Voice state listener
    # =======================================================================
    @commands.Cog.listener()
    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ):
        if member.bot:
            return

        # --- Spawn on join of trigger -------------------------------------
        if after.channel is not None and (before.channel is None or before.channel.id != after.channel.id):
            cfg = await self.bot.db.fetchone(
                "SELECT category_id, trigger_channel_id, name_template "
                "FROM temp_voice_config WHERE guild_id = $1",
                (member.guild.id,),
            )
            if cfg and after.channel.id == cfg["trigger_channel_id"]:
                await self._spawn_temp(member, cfg)

        # --- Despawn when tracked channel empties ------------------------
        if before.channel is not None and (after.channel is None or after.channel.id != before.channel.id):
            row = await self.bot.db.fetchone(
                "SELECT channel_id FROM temp_voice_active WHERE channel_id = $1",
                (before.channel.id,),
            )
            if row and len(before.channel.members) == 0:
                try:
                    await before.channel.delete(reason="temp voice empty")
                except (discord.NotFound, discord.HTTPException) as e:
                    log.warning("temp voice delete failed: %s", e)
                await self.bot.db.execute(
                    "DELETE FROM temp_voice_active WHERE channel_id = $1",
                    (before.channel.id,),
                )

    async def _spawn_temp(self, member: discord.Member, cfg):
        guild = member.guild
        category = guild.get_channel(cfg["category_id"])
        if not isinstance(category, discord.CategoryChannel):
            log.warning("temp voice category missing for guild %s", guild.id)
            return

        # Owner gets channel-management perms on their own channel
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(connect=True, speak=True, view_channel=True),
            member: discord.PermissionOverwrite(
                connect=True,
                speak=True,
                view_channel=True,
                manage_channels=True,
                manage_permissions=True,
                move_members=True,
                mute_members=True,
                deafen_members=True,
                priority_speaker=True,
            ),
            guild.me: discord.PermissionOverwrite(
                connect=True,
                speak=True,
                view_channel=True,
                manage_channels=True,
                move_members=True,
            ),
        }

        name = _render_name(cfg["name_template"], member)
        try:
            new_ch = await guild.create_voice_channel(
                name=name,
                category=category,
                overwrites=overwrites,
                reason=f"temp voice for {member}",
            )
        except discord.HTTPException as e:
            log.warning("temp voice create failed: %s", e)
            return

        try:
            await member.move_to(new_ch, reason="temp voice spawn")
        except (discord.Forbidden, discord.HTTPException) as e:
            log.warning("temp voice move failed: %s", e)
            # Best-effort cleanup if move failed
            try:
                await new_ch.delete(reason="temp voice abort — move failed")
            except discord.HTTPException:
                pass
            return

        await self.bot.db.execute(
            "INSERT INTO temp_voice_active (channel_id, guild_id, owner_id, created_at) "
            "VALUES ($1, $2, $3, $4) "
            "ON CONFLICT (channel_id) DO UPDATE SET "
            "    guild_id = EXCLUDED.guild_id, "
            "    owner_id = EXCLUDED.owner_id, "
            "    created_at = EXCLUDED.created_at",
            (new_ch.id, guild.id, member.id, int(time.time())),
        )
        log.info("temp voice spawned: #%s (id=%s) for %s", new_ch.name, new_ch.id, member)


async def setup(bot: commands.Bot):
    await bot.add_cog(TempVoice(bot))
