from redis.asyncio import Redis

from app.config import get_settings

_client: Redis | None = None


def get_redis() -> Redis:
    global _client
    if _client is None:
        _client = Redis.from_url(get_settings().redis_url, decode_responses=True)
    return _client


def run_channel(run_id: str) -> str:
    return f"run:{run_id}"


def channel_feed(channel_id: int) -> str:
    return f"channel:{channel_id}"
