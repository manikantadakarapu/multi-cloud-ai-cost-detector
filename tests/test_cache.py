"""Tests for the Redis cache adapter."""

from __future__ import annotations

import pytest

from app.core.cache import RedisCache


class _FakeRedisClient:
    def __init__(self) -> None:
        self.store: dict[str, str] = {}
        self.closed = False

    async def ping(self) -> bool:
        return True

    async def get(self, key: str) -> str | None:
        return self.store.get(key)

    async def set(self, key: str, value: str, ex: int | None = None) -> bool:
        self.store[key] = value
        return True

    async def aclose(self) -> None:
        self.closed = True


class _BrokenRedisClient:
    async def ping(self) -> bool:
        raise RuntimeError("redis down")

    async def get(self, key: str) -> str:
        raise RuntimeError("redis down")

    async def set(self, key: str, value: str, ex: int | None = None) -> None:
        raise RuntimeError("redis down")


@pytest.mark.asyncio
async def test_cache_hit_and_set_round_trip() -> None:
    cache = RedisCache(redis_url="redis://example", ttl_seconds=123)
    client = _FakeRedisClient()
    cache._client = client

    await cache.set_json("costs:test", {"provider": "aws", "total_cost": 1.23})
    payload = await cache.get_json("costs:test")

    assert payload == {"provider": "aws", "total_cost": 1.23}
    assert client.store["costs:test"]


@pytest.mark.asyncio
async def test_cache_handles_redis_failure_gracefully() -> None:
    cache = RedisCache(redis_url="redis://example")
    cache._client = _BrokenRedisClient()

    assert await cache.health() is False
    assert await cache.get_json("missing") is None

    await cache.set_json("missing", {"provider": "aws"})
    assert cache.available is False


@pytest.mark.asyncio
async def test_cache_treats_invalid_json_as_a_cache_miss() -> None:
    cache = RedisCache(redis_url="redis://example")
    client = _FakeRedisClient()
    client.store["costs:invalid"] = "not-json"
    cache._client = client

    assert await cache.get_json("costs:invalid") is None
