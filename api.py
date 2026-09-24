"""HTTP REST API surface for Top Shooter.

Runs in-process inside the bot via uvicorn on the same asyncio loop as discord.py.
All endpoints require `Authorization: Bearer <BOT_API_TOKEN>` except `/health`.

The mega-dispatcher at `POST /action` accepts `{action, params}` and routes
to the right handler. See ACTION_HANDLERS below for the full action vocabulary.

Every handler returns `{"ok": bool, "result": ..., "error": str|null}`.

Actor model: there is no per-user actor — possession of the BOT_API_TOKEN is
the only authorization. Every moderation handler therefore acts *as the bot*,
and hierarchy checks pass `guild.me` as the actor (e.g. h_timeout / h_untimeout
gate on `checks.can_act_on(guild.me, member, guild.me)`; h_grant_role /
h_revoke_role refuse any role at or above the bot's top role). Callers are
trusted to have already authorized the human on their side (n8n / Discord perms).

Designed to be called by n8n's "PKCW Discord Bot — Tool: bot" sub-workflow.
"""

import logging
import secrets
import time
from typing import Any, Awaitable, Callable

import discord
from discord.ext import commands
from fastapi import Body, FastAPI, Header, HTTPException
from pydantic import BaseModel

import config
from utils import checks
from utils.time_parse import parse_duration

log = logging.getLogger("topshooter.api")


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------
def _require_token(authorization: str | None) -> None:
    if not config.BOT_API_TOKEN:
        raise HTTPException(503, "Bot API token not configured.")
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Missing or malformed Authorization header.")
    expected = f"Bearer {config.BOT_API_TOKEN}"
    if not secrets.compare_digest(authorization, expected):
        raise HTTPException(401, "Invalid token.")


# ---------------------------------------------------------------------------
# Response helpers
# ---------------------------------------------------------------------------
def ok(result: Any = None) -> dict:
    return {"ok": True, "result": result, "error": None}


def fail(msg: str, status: int | None = None) -> dict:
    out = {"ok": False, "result": None, "error": msg}
    if status:
        out["status"] = status
    return out


def _get_guild(bot: commands.Bot, params: dict) -> discord.Guild:
    gid = params.get("guild_id") or config.DEV_GUILD_ID
    if not gid:
        raise ValueError("guild_id required")
    g = bot.get_guild(int(gid))
    if not g:
        raise ValueError(f"guild {gid} not found")
    return g


def _embed_from_dict(d: dict | None) -> discord.Embed | None:
    if not d:
        return None
    return discord.Embed.from_dict(d)


# ===========================================================================
# Action handlers
# ===========================================================================
async def h_send_message(bot, params):
    ch = bot.get_channel(int(params["channel_id"]))
    if not isinstance(ch, (discord.TextChannel, discord.Thread, discord.VoiceChannel)):
        return fail("Channel not found or not messageable.")
    msg = await ch.send(content=params.get("content") or None, embed=_embed_from_dict(params.get("embed")))
    return ok({"message_id": msg.id, "jump_url": msg.jump_url, "channel_id": ch.id})


async def h_send_dm(bot, params):
    user = await bot.fetch_user(int(params["user_id"]))
    try:
        msg = await user.send(content=params.get("content") or None, embed=_embed_from_dict(params.get("embed")))
        return ok({"message_id": msg.id, "delivered": True})
    except discord.Forbidden:
        return ok({"delivered": False, "reason": "DMs closed"})


async def h_edit_message(bot, params):
    ch = bot.get_channel(int(params["channel_id"]))
    if not ch:
        return fail("Channel not found.")
    msg = await ch.fetch_message(int(params["message_id"]))
    if msg.author.id != bot.user.id:
        return fail("Can only edit my own messages.")
    await msg.edit(content=params.get("content"), embed=_embed_from_dict(params.get("embed")))
    return ok({"message_id": msg.id})


async def h_delete_message(bot, params):
    ch = bot.get_channel(int(params["channel_id"]))
    if not ch:
        return fail("Channel not found.")
    msg = await ch.fetch_message(int(params["message_id"]))
    await msg.delete()
    return ok({"deleted": True})


async def h_react(bot, params):
    ch = bot.get_channel(int(params["channel_id"]))
    if not ch:
        return fail("Channel not found.")
    msg = await ch.fetch_message(int(params["message_id"]))
    await msg.add_reaction(params["emoji"])
    return ok({"reacted": True})


async def h_unreact(bot, params):
    ch = bot.get_channel(int(params["channel_id"]))
    if not ch:
        return fail("Channel not found.")
    msg = await ch.fetch_message(int(params["message_id"]))
    await msg.remove_reaction(params["emoji"], bot.user)
    return ok({"unreacted": True})


# --- Reads -----------------------------------------------------------------

async def h_get_member(bot, params):
    guild = _get_guild(bot, params)
    uid = int(params["user_id"])
    member = guild.get_member(uid)
    if member is None:
        try:
            member = await guild.fetch_member(uid)
        except discord.NotFound:
            return fail("Member not in guild.")
    # Pull level/xp + warn count
    lvl_row = await bot.db.fetchone(
        "SELECT xp, level FROM levels WHERE guild_id = $1 AND user_id = $2",
        (guild.id, uid),
    )
    warn_row = await bot.db.fetchone(
        "SELECT COUNT(*) AS n FROM warns WHERE guild_id = $1 AND user_id = $2 AND cleared_at IS NULL",
        (guild.id, uid),
    )
    return ok({
        "id": member.id,
        "name": member.name,
        "display_name": member.display_name,
        "avatar_url": member.display_avatar.url,
        "joined_at": int(member.joined_at.timestamp()) if member.joined_at else None,
        "created_at": int(member.created_at.timestamp()),
        "roles": [{"id": r.id, "name": r.name} for r in member.roles if not r.is_default()],
        "status": str(member.status),
        "is_bot": member.bot,
        "is_pending": member.pending,
        "timed_out_until": int(member.timed_out_until.timestamp()) if member.timed_out_until else None,
        "level": lvl_row["level"] if lvl_row else 0,
        "xp": lvl_row["xp"] if lvl_row else 0,
        "active_warns": warn_row["n"] if warn_row else 0,
    })


async def h_list_members(bot, params):
    guild = _get_guild(bot, params)
    role_id = params.get("role_id")
    min_level = params.get("min_level", 0)
    limit = min(int(params.get("limit", 50)), 200)

    members = list(guild.members)
    if role_id:
        rid = int(role_id)
        members = [m for m in members if any(r.id == rid for r in m.roles)]
    if min_level:
        # Need XP lookup for each — fetch levels in one query
        rows = await bot.db.fetchall(
            "SELECT user_id, level FROM levels WHERE guild_id = $1 AND level >= $2",
            (guild.id, int(min_level)),
        )
        level_uids = {r["user_id"] for r in rows}
        members = [m for m in members if m.id in level_uids]

    members = members[:limit]
    return ok([
        {"id": m.id, "name": m.name, "display_name": m.display_name, "is_bot": m.bot}
        for m in members
    ])


async def h_list_channels(bot, params):
    guild = _get_guild(bot, params)
    type_filter = params.get("type")
    cat_id = params.get("category_id")
    result = []
    for ch in guild.channels:
        if cat_id and ch.category_id != int(cat_id):
            continue
        type_name = str(ch.type).removeprefix("ChannelType.")
        if type_filter and type_filter != type_name:
            continue
        result.append({
            "id": ch.id,
            "name": ch.name,
            "type": type_name,
            "category_id": ch.category_id,
            "position": ch.position,
        })
    return ok(result)


async def h_recent_messages(bot, params):
    ch = bot.get_channel(int(params["channel_id"]))
    if not isinstance(ch, (discord.TextChannel, discord.Thread)):
        return fail("Channel not found or not a text channel.")
    limit = min(int(params.get("limit", 25)), 100)
    skip_bots = bool(params.get("skip_bots", True))
    msgs = []
    async for m in ch.history(limit=limit):
        if skip_bots and m.author.bot:
            continue
        msgs.append({
            "id": m.id,
            "author_id": m.author.id,
            "author_name": m.author.name,
            "content": m.content,
            "created_at": int(m.created_at.timestamp()),
            "jump_url": m.jump_url,
            "attachments": [a.url for a in m.attachments],
        })
    return ok(msgs)


async def h_audit_log_recent(bot, params):
    guild = _get_guild(bot, params)
    limit = min(int(params.get("limit", 25)), 100)
    action_filter = params.get("action_type")
    entries = []
    action_enum = None
    if action_filter:
        action_enum = getattr(discord.AuditLogAction, action_filter, None)
    try:
        async for e in guild.audit_logs(limit=limit, action=action_enum):
            entries.append({
                "id": e.id,
                "action": str(e.action),
                "actor_id": e.user_id,
                "target_id": e.target_id,
                "reason": e.reason,
                "created_at": int(e.created_at.timestamp()),
            })
    except discord.Forbidden:
        return fail("Bot lacks view_audit_log permission.")
    return ok(entries)


# --- Mod -------------------------------------------------------------------

async def h_grant_role(bot, params):
    guild = _get_guild(bot, params)
    member = guild.get_member(int(params["user_id"])) or await guild.fetch_member(int(params["user_id"]))
    role = guild.get_role(int(params["role_id"]))
    if not role:
        return fail("Role not found.")
    if role >= guild.me.top_role:
        return fail("Role is at or above my top role.")
    if role in member.roles:
        return ok({"already_had": True})
    await member.add_roles(role, reason=params.get("reason") or "via API")
    return ok({"granted": True, "role": role.name})


async def h_revoke_role(bot, params):
    guild = _get_guild(bot, params)
    member = guild.get_member(int(params["user_id"])) or await guild.fetch_member(int(params["user_id"]))
    role = guild.get_role(int(params["role_id"]))
    if not role:
        return fail("Role not found.")
    if role >= guild.me.top_role:
        return fail("Role is at or above my top role.")
    if role not in member.roles:
        return ok({"didnt_have": True})
    await member.remove_roles(role, reason=params.get("reason") or "via API")
    return ok({"revoked": True, "role": role.name})


async def h_timeout(bot, params):
    guild = _get_guild(bot, params)
    member = guild.get_member(int(params["user_id"])) or await guild.fetch_member(int(params["user_id"]))
    td = parse_duration(params["duration"])
    ok_act, why = checks.can_act_on(guild.me, member, guild.me)
    if not ok_act and member.id != guild.owner_id:
        return fail(why)
    await member.timeout(td, reason=params.get("reason") or "via API")
    return ok({"timed_out_for_seconds": int(td.total_seconds())})


async def h_untimeout(bot, params):
    guild = _get_guild(bot, params)
    member = guild.get_member(int(params["user_id"])) or await guild.fetch_member(int(params["user_id"]))
    ok_act, why = checks.can_act_on(guild.me, member, guild.me)
    if not ok_act and member.id != guild.owner_id:
        return fail(why)
    await member.timeout(None, reason=params.get("reason") or "via API")
    return ok({"untimed_out": True})


async def h_warn(bot, params):
    """Route through the same logic as /warn including auto-escalation."""
    guild = _get_guild(bot, params)
    member = guild.get_member(int(params["user_id"])) or await guild.fetch_member(int(params["user_id"]))
    reason = (params.get("reason") or "").strip()
    if not reason:
        return fail("reason required")
    await bot.db.execute(
        "INSERT INTO warns (guild_id, user_id, moderator_id, reason, created_at) VALUES ($1, $2, $3, $4, $5)",
        (guild.id, member.id, bot.user.id, reason, int(time.time())),
    )
    row = await bot.db.fetchone(
        "SELECT COUNT(*) AS n FROM warns WHERE guild_id = $1 AND user_id = $2 AND cleared_at IS NULL",
        (guild.id, member.id),
    )
    active = row["n"]
    # Auto-escalation (reuse the constants from moderation cog)
    from cogs.moderation import WARN_ESCALATIONS
    escalation = None
    for threshold, action, td in WARN_ESCALATIONS:
        if active == threshold:
            try:
                if action == "timeout":
                    await member.timeout(td, reason=f"Auto-escalation at {threshold} warns")
                    escalation = f"timeout {int(td.total_seconds())}s"
                elif action == "kick":
                    await member.kick(reason=f"Auto-kick at {threshold} warns")
                    escalation = "kick"
            except discord.HTTPException as e:
                log.warning("auto-escalation failed: %s", e)
            break
    return ok({"active_warns": active, "escalation": escalation})


async def h_kick(bot, params):
    guild = _get_guild(bot, params)
    member = guild.get_member(int(params["user_id"])) or await guild.fetch_member(int(params["user_id"]))
    ok_act, why = checks.can_act_on(guild.me, member, guild.me)
    if not ok_act and member.id != guild.owner_id:
        return fail(why)
    await member.kick(reason=params.get("reason") or "via API")
    return ok({"kicked": True})


async def h_ban(bot, params):
    guild = _get_guild(bot, params)
    user_id = int(params["user_id"])
    member = guild.get_member(user_id)
    delete_days = int(params.get("delete_message_days", 0))
    if member:
        ok_act, why = checks.can_act_on(guild.me, member, guild.me)
        if not ok_act and member.id != guild.owner_id:
            return fail(why)
        await member.ban(reason=params.get("reason") or "via API", delete_message_seconds=delete_days * 86400)
    else:
        user_obj = await bot.fetch_user(user_id)
        await guild.ban(user_obj, reason=params.get("reason") or "via API", delete_message_seconds=delete_days * 86400)
    return ok({"banned": True})


async def h_unban(bot, params):
    guild = _get_guild(bot, params)
    user = await bot.fetch_user(int(params["user_id"]))
    await guild.unban(user, reason=params.get("reason") or "via API")
    return ok({"unbanned": True})


# ---------------------------------------------------------------------------
# Action registry
# ---------------------------------------------------------------------------
Handler = Callable[[commands.Bot, dict], Awaitable[dict]]

ACTION_HANDLERS: dict[str, Handler] = {
    # messaging
    "send_message": h_send_message,
    "send_dm": h_send_dm,
    "edit_message": h_edit_message,
    "delete_message": h_delete_message,
    "react": h_react,
    "unreact": h_unreact,
    # reads
    "get_member": h_get_member,
    "list_members": h_list_members,
    "list_channels": h_list_channels,
    "recent_messages": h_recent_messages,
    "audit_log_recent": h_audit_log_recent,
    # mod
    "grant_role": h_grant_role,
    "revoke_role": h_revoke_role,
    "timeout": h_timeout,
    "untimeout": h_untimeout,
    "warn": h_warn,
    "kick": h_kick,
    "ban": h_ban,
    "unban": h_unban,
}


# ---------------------------------------------------------------------------
# Pydantic request models
# ---------------------------------------------------------------------------
class ActionRequest(BaseModel):
    action: str
    params: dict = {}


# ---------------------------------------------------------------------------
# FastAPI app factory
# ---------------------------------------------------------------------------
def create_app(bot: commands.Bot) -> FastAPI:
    app = FastAPI(
        title="Top Shooter API",
        version="1.0",
        docs_url=None,  # disable interactive docs — internal-only service
        redoc_url=None,
        openapi_url=None,
    )

    @app.get("/health")
    async def health():
        """Liveness probe. Unauthenticated."""
        return {
            "ok": True,
            "bot_ready": bot.is_ready(),
            "latency_ms": round(bot.latency * 1000) if bot.is_ready() else None,
            "user": str(bot.user) if bot.user else None,
        }

    @app.post("/action")
    async def action_endpoint(
        body: ActionRequest,
        authorization: str = Header(None),
    ):
        _require_token(authorization)
        handler = ACTION_HANDLERS.get(body.action)
        if not handler:
            return fail(f"Unknown action: {body.action}")
        try:
            return await handler(bot, body.params or {})
        except HTTPException:
            raise
        except Exception as e:
            log.exception("action %s failed", body.action)
            return fail(f"{type(e).__name__}: {e}")

    @app.get("/actions")
    async def list_actions(authorization: str = Header(None)):
        _require_token(authorization)
        return {"actions": sorted(ACTION_HANDLERS.keys())}

    @app.get("/status")
    async def status_endpoint(authorization: str = Header(None)):
        """Full status JSON. Same data the /status slash command shows."""
        _require_token(authorization)
        guild = bot.get_guild(config.DEV_GUILD_ID) if config.DEV_GUILD_ID else None
        bans_count = 0
        if guild:
            try:
                bans_count = sum(1 async for _ in guild.bans(limit=None))
            except Exception:
                bans_count = -1

        active_warns_row = None
        top_flagged = []
        if guild:
            active_warns_row = await bot.db.fetchone(
                "SELECT COUNT(*) AS n FROM warns WHERE guild_id = $1 AND cleared_at IS NULL",
                (guild.id,),
            )
            top_flagged_rows = await bot.db.fetchall(
                "SELECT user_id, COUNT(*) AS n FROM warns "
                "WHERE guild_id = $1 AND cleared_at IS NULL "
                "GROUP BY user_id ORDER BY n DESC LIMIT 5",
                (guild.id,),
            )
            top_flagged = [{"user_id": r["user_id"], "count": r["n"]} for r in top_flagged_rows]

        automod_rules_row = None
        if guild:
            automod_rules_row = await bot.db.fetchone(
                "SELECT COUNT(*) AS n FROM automod_rules WHERE guild_id = $1 AND enabled = TRUE",
                (guild.id,),
            )

        verdict = "green"
        if active_warns_row and active_warns_row["n"] >= 10:
            verdict = "yellow"
        if not bot.is_ready():
            verdict = "red"

        return ok({
            "bot": {
                "ready": bot.is_ready(),
                "user": str(bot.user) if bot.user else None,
                "latency_ms": round(bot.latency * 1000) if bot.is_ready() else None,
            },
            "guild": {
                "id": guild.id if guild else None,
                "name": guild.name if guild else None,
                "member_count": guild.member_count if guild else 0,
                "channels": len(guild.channels) if guild else 0,
                "roles": len(guild.roles) if guild else 0,
            },
            "moderation": {
                "bans": bans_count,
                "active_warns": active_warns_row["n"] if active_warns_row else 0,
                "top_flagged": top_flagged,
            },
            "automod": {
                "rules": automod_rules_row["n"] if automod_rules_row else 0,
            },
            "verdict": verdict,
        })

    return app
