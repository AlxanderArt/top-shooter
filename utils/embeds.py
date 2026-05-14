import discord
from config import (
    BRAND_FOOTER,
    COLOR_BRAND,
    COLOR_INFO,
    COLOR_SUCCESS,
    COLOR_WARN,
    COLOR_ERROR,
)


def _base(title: str, description: str | None, color: int) -> discord.Embed:
    embed = discord.Embed(
        title=title.upper() if title else None,
        description=description,
        color=color,
    )
    embed.set_footer(text=BRAND_FOOTER)
    return embed


def brand(title: str, description: str | None = None) -> discord.Embed:
    return _base(title, description, COLOR_BRAND)


def info(title: str, description: str | None = None) -> discord.Embed:
    return _base(title, description, COLOR_INFO)


def success(title: str, description: str | None = None) -> discord.Embed:
    return _base(title, description, COLOR_SUCCESS)


def warn(title: str, description: str | None = None) -> discord.Embed:
    return _base(f"[WARN] {title}", description, COLOR_WARN)


def error(title: str, description: str | None = None) -> discord.Embed:
    return _base(f"[ERROR] {title}", description, COLOR_ERROR)
