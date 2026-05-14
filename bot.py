import os
import sys

import certifi

os.environ.setdefault("SSL_CERT_FILE", certifi.where())
os.environ.setdefault("REQUESTS_CA_BUNDLE", certifi.where())

import asyncio
import logging
import logging.handlers

import discord
import uvicorn
from discord.ext import commands

import config
from api import create_app
from db import Database
from utils import event_push


def _setup_logging() -> logging.Logger:
    config.LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("topshooter")
    logger.setLevel(logging.INFO)

    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    stream = logging.StreamHandler(sys.stdout)
    stream.setFormatter(fmt)
    logger.addHandler(stream)

    file_handler = logging.handlers.TimedRotatingFileHandler(
        config.LOG_PATH, when="midnight", backupCount=7, encoding="utf-8"
    )
    file_handler.setFormatter(fmt)
    logger.addHandler(file_handler)

    discord_logger = logging.getLogger("discord")
    discord_logger.setLevel(logging.WARNING)

    return logger


log = _setup_logging()


class TopShooter(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        super().__init__(command_prefix="!", intents=intents, help_command=None)
        self.db = Database()
        self._api_server: uvicorn.Server | None = None
        self._api_task: asyncio.Task | None = None

    async def setup_hook(self) -> None:
        await self.db.connect()
        if config.DEV_GUILD_ID:
            await self.db.ensure_guild_settings(config.DEV_GUILD_ID)

        for ext in config.COGS:
            await self.load_extension(ext)
            log.info("Loaded cog: %s", ext)

        if config.DEV_GUILD_ID:
            guild = discord.Object(id=config.DEV_GUILD_ID)
            self.tree.copy_global_to(guild=guild)
            synced = await self.tree.sync(guild=guild)
            log.info("Synced %d slash commands to dev guild %s", len(synced), config.DEV_GUILD_ID)
        else:
            log.warning("DEV_GUILD_ID not set — slash commands not synced. Set it in .env for instant updates.")

        # Start the REST API server on the same event loop.
        if config.BOT_API_TOKEN:
            api_app = create_app(self)
            uv_config = uvicorn.Config(
                api_app,
                host=config.BOT_API_HOST,
                port=config.BOT_API_PORT,
                log_level="warning",
                access_log=False,
            )
            self._api_server = uvicorn.Server(uv_config)
            self._api_task = asyncio.create_task(self._api_server.serve(), name="bot-api")
            log.info("REST API listening on %s:%s", config.BOT_API_HOST, config.BOT_API_PORT)
        else:
            log.warning("BOT_API_TOKEN not set — REST API disabled.")

    async def close(self) -> None:
        if self._api_server is not None:
            self._api_server.should_exit = True
            if self._api_task is not None:
                try:
                    await asyncio.wait_for(self._api_task, timeout=5)
                except asyncio.TimeoutError:
                    pass
        await event_push.close_session()
        await self.db.close()
        await super().close()

    async def on_ready(self):
        log.info("Logged on as %s (%s)", self.user, self.user.id)
        await self.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name=config.BRAND_PRESENCE.replace("Watching ", ""),
            )
        )


def main():
    if not config.TOKEN:
        log.error("DISCORD_TOKEN missing in .env — bot cannot start.")
        sys.exit(1)

    bot = TopShooter()
    try:
        asyncio.run(bot.start(config.TOKEN))
    except KeyboardInterrupt:
        log.info("Shutdown requested.")


if __name__ == "__main__":
    main()
