"""Cache for Blizzard API responses stored in Postgres (table api_cache)."""
import hashlib
import json
import time
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


def cache_key(path: str, params: dict) -> str:
    raw = path + "?" + json.dumps(params, sort_keys=True)
    return hashlib.sha256(raw.encode()).hexdigest()


def _maybe_json(payload):
    if isinstance(payload, (str, bytes, bytearray)):
        return json.loads(payload)
    return payload


async def get_cached(db: AsyncSession, key: str) -> Any | None:
    row = (await db.execute(
        text("SELECT payload, fetched_at, ttl_seconds FROM api_cache WHERE key = :k"),
        {"k": key},
    )).first()
    if row is None:
        return None
    payload, fetched_at, ttl = row
    if time.time() - fetched_at > ttl:
        return None
    return _maybe_json(payload)


async def set_cached(db: AsyncSession, key: str, payload: Any, ttl: int) -> None:
    import time as _t
    await db.execute(
        text("""
            INSERT INTO api_cache (key, payload, fetched_at, ttl_seconds)
            VALUES (:k, :p, :t, :ttl)
            ON CONFLICT (key) DO UPDATE
              SET payload = :p, fetched_at = :t, ttl_seconds = :ttl
        """),
        {"k": key, "p": json.dumps(payload, default=str), "t": _t.time(), "ttl": ttl},
    )
    await db.commit()
