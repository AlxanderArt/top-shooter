"""Permission + hierarchy helpers for moderation commands."""

import discord

import config


def is_owner(user_id: int) -> bool:
    return user_id == config.OWNER_ID


def can_act_on(actor: discord.Member, target: discord.Member, bot_member: discord.Member) -> tuple[bool, str]:
    """Return (allowed, reason_if_not). Checks role hierarchy + special cases.

    - Server owner can always act.
    - Cannot act on self.
    - Cannot act on the server owner.
    - Cannot act on the bot.
    - Actor's top role must be strictly above target's top role.
    - Bot's top role must be strictly above target's top role (so it can carry out the action).
    """
    if actor.id == target.id:
        return False, "You can't act on yourself."
    if target.id == actor.guild.owner_id:
        return False, "Can't act on the server owner."
    if target.bot and target.id == bot_member.id:
        return False, "I can't act on myself. Try the integration settings if you need to."
    if actor.id == actor.guild.owner_id:
        return True, ""
    if actor.top_role <= target.top_role:
        return False, "Target has an equal or higher role than you."
    if bot_member.top_role <= target.top_role:
        return False, "Target has an equal or higher role than me. Move my role up first."
    return True, ""


async def try_dm(user: discord.User | discord.Member, embed: discord.Embed) -> bool:
    """DM a user with an embed. Returns True on success, False on failure (DMs closed, etc.)."""
    try:
        await user.send(embed=embed)
        return True
    except (discord.Forbidden, discord.HTTPException):
        return False
