import asyncio

import pytest

from app.runtime import redis as runtime_redis


class FakeRedis:
    def __init__(self):
        self.keys: dict[str, int] = {}
        self.renewals = 0

    async def set(self, key, value, nx=False, ex=None):
        if nx and key in self.keys:
            return None
        self.keys[key] = ex
        return True

    async def expire(self, key, seconds):
        self.renewals += 1
        self.keys[key] = seconds

    async def delete(self, key):
        self.keys.pop(key, None)


@pytest.fixture
def fake(monkeypatch):
    redis = FakeRedis()
    monkeypatch.setattr(runtime_redis, "get_redis", lambda: redis)
    return redis


async def test_lock_lives_while_owner_works(fake):
    async with runtime_redis.owned_lock("job", seconds=1) as acquired:
        assert acquired is True
        await asyncio.sleep(1.1)
        assert fake.keys == {"job": 1}
    assert fake.renewals >= 2
    assert fake.keys == {}


async def test_second_owner_is_refused(fake):
    async with runtime_redis.owned_lock("job") as first:
        async with runtime_redis.owned_lock("job") as second:
            assert (first, second) == (True, False)
        assert "job" in fake.keys
    assert fake.keys == {}


async def test_lock_is_released_when_owner_fails(fake):
    with pytest.raises(RuntimeError):
        async with runtime_redis.owned_lock("job"):
            raise RuntimeError("boom")
    assert fake.keys == {}
