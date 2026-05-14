"""Parse duration strings into timedelta objects.

Accepts compact forms ('10m', '2h', '3d', '1w', '30s') with optional
combinations ('1h30m'). Rejects anything else.
"""

import re
from datetime import timedelta

_TOKEN_RE = re.compile(r"(\d+)\s*([smhdw])", re.IGNORECASE)
_UNIT_SECONDS = {
    "s": 1,
    "m": 60,
    "h": 3600,
    "d": 86400,
    "w": 604800,
}

MIN_SECONDS = 1
MAX_SECONDS = 28 * 86400  # Discord caps timeouts at 28 days


def parse_duration(s: str) -> timedelta:
    """Parse '10m', '2h30m', '3d', etc. Raises ValueError on garbage."""
    if not s:
        raise ValueError("Duration string is empty.")
    s = s.strip()
    if not s:
        raise ValueError("Duration string is empty.")
    # Whole string must be tokens with optional whitespace
    consumed = 0
    total_seconds = 0
    for match in _TOKEN_RE.finditer(s):
        if match.start() != consumed:
            # Gap of non-token text
            raise ValueError(f"Bad duration: {s!r}")
        amount = int(match.group(1))
        unit = match.group(2).lower()
        total_seconds += amount * _UNIT_SECONDS[unit]
        consumed = match.end()
    if consumed != len(s.rstrip()):
        raise ValueError(f"Bad duration: {s!r}")
    if total_seconds < MIN_SECONDS:
        raise ValueError("Duration must be at least 1 second.")
    if total_seconds > MAX_SECONDS:
        raise ValueError("Duration exceeds 28 days (Discord max).")
    return timedelta(seconds=total_seconds)


def format_duration(td: timedelta) -> str:
    """Format a timedelta as a compact string for display."""
    total = int(td.total_seconds())
    if total <= 0:
        return "0s"
    weeks, rem = divmod(total, 604800)
    days, rem = divmod(rem, 86400)
    hours, rem = divmod(rem, 3600)
    mins, secs = divmod(rem, 60)
    parts = []
    if weeks:
        parts.append(f"{weeks}w")
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    if mins:
        parts.append(f"{mins}m")
    if secs:
        parts.append(f"{secs}s")
    return "".join(parts) or "0s"
