"""Top Shooter DB layer (asyncpg / Postgres).

Backwards-compatible API surface with the previous aiosqlite wrapper so
cogs only need to update their SQL syntax (`?` → `$1, $2`, etc.) not
their call patterns.

Cogs use `bot.db.execute(...)`, `fetchone(...)`, `fetchall(...)`, `commit()`.
`commit()` is a no-op under asyncpg autocommit — kept for API parity.

Cursor-like return from `execute()`: a small object with `.rowcount` so
existing cogs that read `cur.rowcount` continue to work.
"""

import logging
import re
from pathlib import Path
from typing import Any, Iterable, Sequence

import asyncpg

import config

log = logging.getLogger("topshooter.db")

SCHEMA_PATH = Path(__file__).parent / "schema.sql"


class _ExecuteResult:
    """Lightweight mimic of aiosqlite.Cursor — exposes `rowcount` and `lastrowid`."""

    __slots__ = ("rowcount", "lastrowid")

    def __init__(self, rowcount: int = 0, lastrowid: int | None = None):
        self.rowcount = rowcount
        self.lastrowid = lastrowid


def _parse_rowcount(status: str) -> int:
    """Postgres command tags look like 'UPDATE 3', 'DELETE 0', 'INSERT 0 1'."""
    if not status:
        return 0
    parts = status.split()
    if not parts:
        return 0
    cmd = parts[0].upper()
    if cmd == "INSERT" and len(parts) >= 3:
        # 'INSERT oid count'
        try:
            return int(parts[2])
        except ValueError:
            return 0
    if len(parts) >= 2:
        try:
            return int(parts[-1])
        except ValueError:
            return 0
    return 0


class Database:
    """Async Postgres wrapper. Single shared connection pool."""

    def __init__(self, url: str | None = None):
        self.url = url or config.DATABASE_URL
        self._pool: asyncpg.Pool | None = None

    # -- lifecycle ----------------------------------------------------------

    async def connect(self) -> None:
        self._pool = await asyncpg.create_pool(self.url, min_size=1, max_size=10)
        await self._apply_schema()
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow("SELECT version FROM schema_version ORDER BY version DESC LIMIT 1")
        log.info("DB connected to %s (schema v%s)", self._safe_url(), row["version"] if row else "?")

    def _safe_url(self) -> str:
        return re.sub(r"://[^:]+:[^@]+@", "://***:***@", self.url)

    async def close(self) -> None:
        if self._pool is not None:
            await self._pool.close()
            self._pool = None

    async def _apply_schema(self) -> None:
        assert self._pool is not None
        schema_sql = SCHEMA_PATH.read_text()
        async with self._pool.acquire() as conn:
            await conn.execute(schema_sql)

    # -- helpers ------------------------------------------------------------

    def _require_pool(self) -> asyncpg.Pool:
        if self._pool is None:
            raise RuntimeError("Database not connected — call .connect() first")
        return self._pool

    async def execute(self, sql: str, params: Sequence[Any] = ()) -> _ExecuteResult:
        """Run a non-SELECT statement. Returns rowcount + lastrowid (for RETURNING).

        Note: asyncpg uses $1, $2, ... positional parameters (not ?).
        """
        async with self._require_pool().acquire() as conn:
            # If the caller's SQL contains 'RETURNING', use fetchval to capture lastrowid
            upper = sql.lstrip().upper()
            if "RETURNING" in upper:
                row = await conn.fetchrow(sql, *params)
                last = row[0] if row else None
                return _ExecuteResult(rowcount=1 if row else 0, lastrowid=last)
            status = await conn.execute(sql, *params)
            return _ExecuteResult(rowcount=_parse_rowcount(status))

    async def executemany(self, sql: str, params_seq: Iterable[Sequence[Any]]) -> _ExecuteResult:
        async with self._require_pool().acquire() as conn:
            await conn.executemany(sql, list(params_seq))
        return _ExecuteResult()

    async def fetchone(self, sql: str, params: Sequence[Any] = ()) -> asyncpg.Record | None:
        async with self._require_pool().acquire() as conn:
            return await conn.fetchrow(sql, *params)

    async def fetchall(self, sql: str, params: Sequence[Any] = ()) -> list[asyncpg.Record]:
        async with self._require_pool().acquire() as conn:
            return list(await conn.fetch(sql, *params))

    async def commit(self) -> None:
        # asyncpg autocommits each statement outside an explicit transaction.
        # Kept as a no-op for compatibility with the aiosqlite-era cogs.
        return None

    # -- convenience helpers used by cogs ----------------------------------

    async def ensure_guild_settings(self, guild_id: int) -> None:
        await self.execute(
            "INSERT INTO guild_settings (guild_id) VALUES ($1) ON CONFLICT (guild_id) DO NOTHING",
            (guild_id,),
        )

    async def get_guild_settings(self, guild_id: int) -> asyncpg.Record | None:
        return await self.fetchone(
            "SELECT * FROM guild_settings WHERE guild_id = $1",
            (guild_id,),
        )
