import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).parent
load_dotenv(ROOT / ".env")

# --- Discord ----------------------------------------------------------------
TOKEN = os.getenv("DISCORD_TOKEN", "").strip()
OWNER_ID = int(os.getenv("OWNER_ID") or 0)
DEV_GUILD_ID = int(os.getenv("DEV_GUILD_ID") or 0)

# --- DB ---------------------------------------------------------------------
# Postgres connection URL. Required.
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()

# --- HTTP API (n8n integration) --------------------------------------------
BOT_API_TOKEN = os.getenv("BOT_API_TOKEN", "").strip()
BOT_API_HOST = os.getenv("BOT_API_HOST", "0.0.0.0").strip()
BOT_API_PORT = int(os.getenv("BOT_API_PORT") or 8000)

# --- Outbound event webhook (push to n8n) ----------------------------------
N8N_WEBHOOK_URL = os.getenv("N8N_WEBHOOK_URL", "").strip()
N8N_WEBHOOK_TOKEN = os.getenv("N8N_WEBHOOK_TOKEN", "").strip()  # optional

# --- Status auto-post -------------------------------------------------------
_status_ch = os.getenv("STATUS_AUTO_POST_CHANNEL_ID", "").strip()
STATUS_AUTO_POST_CHANNEL_ID = int(_status_ch) if _status_ch.isdigit() else 0
STATUS_TIMEZONE = os.getenv("STATUS_TIMEZONE", "America/Chicago").strip()

# --- Paths ------------------------------------------------------------------
LOG_PATH = ROOT / "logs" / "bot.log"

# --- Brand ------------------------------------------------------------------
BRAND_NAME = "TOP SHOOTER"
BRAND_TAGLINE = "ENGINEERED REBELLION"
BRAND_FOOTER = f"{BRAND_NAME} · {BRAND_TAGLINE}"
BRAND_PRESENCE = "Watching PROJECTKIDCREATIONS"

COLOR_BRAND = 0xFF5F1F   # hi-vis-orange
COLOR_INFO = 0x3F4448    # anodized-slate
COLOR_SUCCESS = 0xFF5F1F # hi-vis-orange
COLOR_WARN = 0xFF1F1F    # alarm-red
COLOR_ERROR = 0xFF1F1F   # alarm-red

COGS = [
    "cogs.general",
    "cogs.admin",
    "cogs.moderation",
    "cogs.audit_log",
    "cogs.welcome",
    "cogs.roles",
    "cogs.levels",
    "cogs.automod",
    "cogs.channels",
    "cogs.tempvoice",
    "cogs.status",
]
