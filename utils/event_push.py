"""Fire-and-forget event publisher → n8n webhook.

Every interesting Discord event the bot observes (member join, mod action,
level-up, automod hit, etc.) is pushed to the n8n webhook configured by
`config.N8N_WEBHOOK_URL`. The PKCW orchestrator's "Events Inbox" workflow
receives these and can route them anywhere (Slack, Sheets, etc.).

Design:
- Async. Never blocks the caller. Each push is fire-and-forget via
  `asyncio.create_task`.
- Bounded retry (3 attempts, exponential backoff) before dropping.
- Optional shared-secret header `X-PKC-Event-Token` so n8n can verify the
  payload came from this bot.
- If N8N_WEBHOOK_URL is unset, the publisher is a no-op (handy for local dev).
"""

import asyncio
import logging
import time
from typing import Any

import aiohttp

import config

log = logging.getLogger("topshooter.events")

_session: aiohttp.ClientSession | None = None


def _get_session() -> aiohttp.ClientSession:
    global _session
    if _session is None or _session.closed:
        _session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10))
    return _session


async def close_session() -> None:
    global _session
    if _session is not None and not _session.closed:
        await _session.close()
        _session = None


async def _send(payload: dict) -> None:
    if not config.N8N_WEBHOOK_URL:
        return
    headers = {"Content-Type": "application/json"}
    if config.N8N_WEBHOOK_TOKEN:
        headers["X-PKC-Event-Token"] = config.N8N_WEBHOOK_TOKEN
    session = _get_session()
    delay = 0.5
    for attempt in range(3):
        try:
            async with session.post(config.N8N_WEBHOOK_URL, json=payload, headers=headers) as resp:
                if 200 <= resp.status < 300:
                    return
                log.warning("event push %s returned %s", payload.get("event_type"), resp.status)
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            log.warning("event push attempt %d failed: %s", attempt + 1, e)
        await asyncio.sleep(delay)
        delay *= 2
    log.warning("event push dropped after retries: %s", payload.get("event_type"))


def push(
    event_type: str,
    *,
    guild_id: int | None = None,
    target_id: int | None = None,
    actor_id: int | None = None,
    details: dict | None = None,
) -> None:
    """Schedule a fire-and-forget event push. Safe to call from any async context."""
    if not config.N8N_WEBHOOK_URL:
        return
    payload = {
        "event_type": event_type,
        "guild_id": guild_id,
        "target_id": target_id,
        "actor_id": actor_id,
        "details": details or {},
        "timestamp": int(time.time()),
    }
    try:
        asyncio.create_task(_send(payload))
    except RuntimeError:
        # No running loop; should never happen inside the bot.
        log.debug("event push skipped — no event loop running")
