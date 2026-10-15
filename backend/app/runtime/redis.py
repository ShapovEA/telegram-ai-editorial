import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from redis.asyncio import Redis

from app.config import get_settings

LOCK_SECONDS = 60

_client: Redis | None = None


def get_redis() -> Redis:
    global _client
    if _client is None:
        _client = Redis.from_url(get_settings().redis_url, decode_responses=True)
    return _client


async def _prolong(redis: Redis, key: str, seconds: int) -> None:
    while True:
        await asyncio.sleep(seconds / 3)
        await redis.expire(key, seconds)


@asynccontextmanager
async def owned_lock(key: str, seconds: int = LOCK_SECONDS) -> AsyncIterator[bool]:
    redis = get_redis()
    if not await redis.set(key, "1", nx=True, ex=seconds):
        yield False
        return
    renewal = asyncio.create_task(_prolong(redis, key, seconds))
    try:
        yield True
    finally:
        renewal.cancel()
        await redis.delete(key)


def run_channel(run_id: str) -> str:
    return f"run:{run_id}"


def channel_feed(channel_id: int) -> str:
    return f"channel:{channel_id}"
