"""Redis cache integration for provider cost responses.

The cache is intentionally thin: it stores JSON payloads under a caller-provided
key, tolerates connection failures by degrading to a no-op, and exposes a small
dependency-injection surface for FastAPI routes and services.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable
from typing import Any

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

try:  # pragma: no cover - exercised when redis is installed
    import redis.asyncio as redis_asyncio
except ImportError:  # pragma: no cover - local fallback when dependency is absent
    redis_asyncio = None  # type: ignore[assignment]


class RedisCache:
    """Async Redis-backed cache with graceful failure handling."""

    def __init__(
        self,
        redis_url: str | None = None,
        ttl_seconds: int | None = None,
    ) -> None:
        self._redis_url = redis_url or settings.redis_url
        self._ttl_seconds = ttl_seconds or settings.cache_ttl_seconds
        self._client: Any | None = None
        self._available = False

    @property
    def ttl_seconds(self) -> int:
        """Return the default cache time-to-live."""
        return self._ttl_seconds

    @property
    def available(self) -> bool:
        """Return ``True`` when Redis is reachable."""
        return self._available

    async def startup(self) -> None:
        """Initialise the Redis client and probe connectivity."""
        if redis_asyncio is None:
            logger.warning("redis_dependency_missing")
            self._client = None
            self._available = False
            return

        try:
            self._client = redis_asyncio.from_url(
                self._redis_url,
                encoding="utf-8",
                decode_responses=True,
                socket_connect_timeout=1,
                socket_timeout=1,
            )
            await self._client.ping()
            self._available = True
            logger.info("redis_cache_started")
        except Exception:  # pragma: no cover - network / environment specific
            logger.exception("redis_cache_startup_failed")
            self._client = None
            self._available = False

    async def shutdown(self) -> None:
        """Close the Redis client if it was created."""
        client = self._client
        self._client = None
        self._available = False

        if client is None:
            return

        close = getattr(client, "aclose", None)
        if callable(close):
            result = close()
            if isinstance(result, Awaitable):  # pragma: no branch - defensive
                await result
            return

        close = getattr(client, "close", None)
        if callable(close):
            result = close()
            if isinstance(result, Awaitable):  # pragma: no branch - defensive
                await result

    async def health(self) -> bool:
        """Return ``True`` when Redis responds to a ping."""
        client = self._client
        if client is None:
            return False

        try:
            return bool(await client.ping())
        except Exception:  # pragma: no cover - network / environment specific
            logger.exception("redis_cache_health_check_failed")
            self._available = False
            return False

    async def get_json(self, key: str) -> dict[str, Any] | None:
        """Return a cached JSON payload or ``None`` on cache miss."""
        client = self._client
        if client is None:
            return None

        try:
            payload = await client.get(key)
        except Exception:  # pragma: no cover - network / environment specific
            logger.exception("redis_cache_get_failed")
            self._available = False
            return None

        if payload in (None, ""):
            return None
        if isinstance(payload, (bytes, bytearray)):
            payload = payload.decode("utf-8")
        try:
            if isinstance(payload, str):
                return json.loads(payload)
            if isinstance(payload, dict):
                return payload
            return json.loads(str(payload))
        except (TypeError, ValueError):
            logger.warning("redis_cache_payload_invalid")
            return None

    async def set_json(
        self,
        key: str,
        value: Any,
        ttl_seconds: int | None = None,
    ) -> None:
        """Store ``value`` as JSON under ``key``."""
        client = self._client
        if client is None:
            return

        ttl = ttl_seconds or self._ttl_seconds
        payload = _json_payload(value)
        try:
            await client.set(key, payload, ex=ttl)
        except Exception:  # pragma: no cover - network / environment specific
            logger.exception("redis_cache_set_failed")
            self._available = False


def _json_payload(value: Any) -> str:
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    return json.dumps(value, separators=(",", ":"), sort_keys=True)


_cache = RedisCache()


def get_cache() -> RedisCache:
    """Return the shared Redis cache dependency."""
    return _cache


async def cache_health() -> bool:
    """Return the current Redis health status."""
    return await _cache.health()


async def startup_cache() -> None:
    """Start the shared cache client."""
    await _cache.startup()


async def shutdown_cache() -> None:
    """Stop the shared cache client."""
    await _cache.shutdown()
