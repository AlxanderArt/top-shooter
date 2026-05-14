# TOP SHOOTER

A Python Discord bot for the range. Branded with the ProjectKidCreations style guide.

## Setup

1. Create and activate a virtualenv:
   ```
   python3 -m venv .venv
   source .venv/bin/activate
   ```
2. Install dependencies:
   ```
   pip install -r requirements.txt
   ```
3. Fill in `.env`:
   - `DISCORD_TOKEN` — from the Discord Developer Portal
   - `OWNER_ID` — your Discord user ID
   - `DEV_GUILD_ID` — your test server ID (slash commands sync here instantly)
4. Run:
   ```
   python bot.py
   ```

## Phase 0 capability

- `/ping` (slash) and `!ping` (prefix) → returns latency in PKC-branded embed.

More phases land incrementally.
