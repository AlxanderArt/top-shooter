# Top Shooter

*A production Discord bot for [PROJECTKIDCREATIONS](https://projectkidcreations.io) — branded, built, deployed in 10 incremental phases.*

> ⬛ **ENGINEERED REBELLION.**

---

## What it is

**Top Shooter** is the custom Discord bot powering the PROJECTKIDCREATIONS server — a tactical 3D-print gel-blaster brand. The bot is built in Python on `discord.py` 2.x, deployed in Docker on a VPS alongside the brand's existing n8n stack, and exposed as a callable mega-tool to an LLM orchestrator agent.

Three things make it interesting:

1. **Brand-first.** Every embed sidebar, every voice line, every role color obeys the [PKC design system](https://github.com/AlxanderArt/PKCDesignSystem). The bot speaks milspec: `RANK UP — LEVEL 20.` not `Congrats!`.
2. **Self-contained substrate.** PostgreSQL persistence, FastAPI on the same asyncio loop as the gateway, healthchecked container, autoscaling restart on crash + reboot.
3. **Agent-callable.** An n8n sub-workflow wraps the bot's REST API. The brand's LLM orchestrator agent has a `discord_bot` tool — it can post messages, fetch member info, run moderation actions, etc., as part of any workflow.

---

## Architecture

```
                  Hostinger VPS (Docker)
   ┌───────────────────────────────────────────────────┐
   │                                                   │
   │  ┌─────────────┐     ┌─────────────────────────┐ │
   │  │  topshooter │◄───►│   postgres:16-alpine    │ │
   │  │             │     │   topshooter-pg-data    │ │
   │  │ discord.py  │     └─────────────────────────┘ │
   │  │ FastAPI     │                                  │
   │  │ 11 cogs     │                                  │
   │  └──────┬──────┘                                  │
   │         │  REST :8000                             │
   │         │                                         │
   │  ┌──────▼──────────────────────────────────────┐ │
   │  │             n8n (orchestrator)               │ │
   │  │  Tool: discord_bot → POST /action            │ │
   │  │  Webhook: /webhook/pkcw-discord-events  ◄── (bot pushes events) │ │
   │  └──────────────────────────────────────────────┘ │
   └───────────────────────────────────────────────────┘
                       ▲
                       │ Discord Gateway
                       ▼
                    Discord
```

---

## The 10-phase build

The whole bot was built in 10 incremental, deployable phases. Each is its own cog under `cogs/`:

| Phase | Cog | What it adds |
|---|---|---|
| **0** | `general` | Scaffold, env loader, cog loader, `/ping` |
| **1** | `general` (UI) | `/demo` (button + select + modal), paginated `/help` |
| **2** | DB layer + `admin` | aiosqlite → asyncpg, 10-table schema, `/dbstats`, `/reload`, `/sync` |
| **3** | `moderation` | `/kick`, `/ban`, `/timeout`, `/role add/remove`, `/warn` with **auto-escalation** (3 warns → timeout, 7 → kick) |
| **4** | `audit_log` | `/setlog` + listeners for joins/leaves/edits/deletes/role-changes/timeouts/external-mod-actions |
| **5** | `welcome` | `/setwelcome`, `/setleave` with `{user.mention}` `{server}` `{member_count}` placeholders |
| **6** | `roles` | `/autorole`, `/reactionrole`, `/levelrole` — bindings stored for Phase 7 to consume |
| **7** | `levels` | XP on every message (5–10 per msg, 60s cooldown), `level = floor(sqrt(xp/100))`, `/rank`, `/leaderboard`, auto-grant level roles |
| **8** | `automod` | Regex pattern filter, anti-spam (5 msgs in 5s → 10m timeout), anti-raid (10 joins in 30s → 5min auto-kick mode), `/slowmode` |
| **9** | `channels` | `/channel create/delete`, `/category create/delete`, `/thread create` — all destructive ops gated by confirmation buttons |
| **10** | `tempvoice` | Join-to-create voice channels with orphan cleanup on boot |

A bonus `status` cog runs scheduled health snapshots and exposes a `/status` slash command + REST endpoint.

---

## REST API

The bot embeds a FastAPI server on its asyncio loop. Two endpoints matter:

```
GET  /health         (unauth)  → {"ok": true, "bot_ready": true, "latency_ms": 73}
POST /action         (bearer)  → mega-dispatcher
```

The `/action` endpoint accepts `{action, params}` and routes to one of **19 handlers** across messaging, reads, and moderation:

- **Messaging** — `send_message`, `send_dm`, `edit_message`, `delete_message`, `react`, `unreact`
- **Reads** — `get_member`, `list_members`, `list_channels`, `recent_messages`, `audit_log_recent`
- **Moderation** — `grant_role`, `revoke_role`, `timeout`, `untimeout`, `warn`, `kick`, `ban`, `unban`

Every action runs role-hierarchy guards before acting and returns `{ok, result, error}` consistently.

---

## Event push

The bot fires off-thread POSTs to a configured n8n webhook every time something happens on the server — joins, mod actions, level-ups, AutoMod hits, message edits/deletes, external bans. Bounded retry, fire-and-forget, never blocks command latency. The downstream workflow can route to Sheets, Slack, the orchestrator's wakeup webhook — wherever.

---

## Server build

`setup_server.py` is the one-shot builder that takes a blank Discord server to a fully-shaped PKC RANGE: 7 categories, 22 channels (text + voice + stage + forum + announcement), 11 hierarchy roles, 14 tag/ping roles, Community feature, verification level High, AutoMod (anti-spam + profanity + mention-spam), 5-prompt onboarding, Welcome Screen — all idempotent.

`publish_guide.py` posts the server's documentation: 7 pinned welcome embeds + 11 forum threads in `#server-guide` (brand story, channel map, role tiers, build pipeline, drop pipeline, mod reporting, FAQ, glossary, history, roadmap, reader tracks).

---

## Stack

| Layer | Choice |
|---|---|
| Language | Python 3.11 |
| Discord library | `discord.py` 2.7 |
| HTTP API | FastAPI + uvicorn (on the bot's event loop) |
| Persistence | PostgreSQL 16 via `asyncpg` |
| Container | Docker + docker-compose |
| Reverse infra | n8n (existing) on the same Docker network |
| Hosting | Hostinger KVM VPS, Ubuntu 24.04 |

---

## Deploying your own

```bash
# Clone, build secrets, run
git clone https://github.com/AlxanderArt/top-shooter.git topshooter
cd topshooter
cp .env.example .env
# Fill DISCORD_TOKEN, OWNER_ID, DEV_GUILD_ID; generate BOT_API_TOKEN + POSTGRES_PASSWORD
docker compose up -d --build
docker logs topshooter -f
```

The bot will:
1. Wait for Postgres health
2. Apply the schema
3. Load all 11 cogs
4. Sync slash commands to your dev guild
5. Connect to the Discord gateway
6. Start the REST API on `:8000` (internal-only)

Run `setup_server.py` once to build the channel layout, then `publish_guide.py` to drop the documentation.

---

## Brand context

PKC's brand system (palette, type, voice) lives at [`AlxanderArt/PKCDesignSystem`](https://github.com/AlxanderArt/PKCDesignSystem) (private). The bot is one of the first surfaces to fully apply it. Channel colors, embed sidebars, role colors, and string templates all derive from the locked PKC tokens — hi-vis orange `#FF5F1F` (onboarding / in-progress), alarm-red `#FF1F1F` (warn / error), neon-green `#39FF14` (verified / earned), tactical-black `#0A0A0A` (founder).

---

## Tagline

> **The whole point of this place** is to make better gear than what's on the shelf — and to build it openly.

Top Shooter is the brand's voice on Discord. It runs the range.

---

*Built by [@AlxanderArt](https://github.com/AlxanderArt) for PROJECTKIDCREATIONS · 2026*
