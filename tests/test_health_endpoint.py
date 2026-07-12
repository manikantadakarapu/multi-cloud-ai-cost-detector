"""Tests for the health endpoint with Redis-aware health reporting."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from fastapi import Response

from app.api.routes.health import health_check
from app.schemas.health import HealthCheckResponse


class _FakeHealthService:
    def __init__(self, session_factory, cache) -> None:  # noqa: ANN001
        self._payload = {
            "status": "healthy",
            "database": "up",
            "redis": "up",
            "application": "up",
            "version": "0.1.0",
            "environment": "local",
            "timestamp": "2024-01-01T00:00:00Z",
        }

    async def get_status(self) -> dict[str, str]:
        return self._payload


class _FakeUnhealthyHealthService(_FakeHealthService):
    def __init__(self, session_factory, cache) -> None:  # noqa: ANN001
        super().__init__(session_factory, cache)
        self._payload = {
            "status": "unhealthy",
            "database": "up",
            "redis": "down",
            "application": "up",
            "version": "0.1.0",
            "environment": "local",
            "timestamp": "2024-01-01T00:00:00Z",
        }


@pytest.mark.asyncio
async def test_health_endpoint_reports_database_and_redis_up(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.api.routes.health.HealthService",
        _FakeHealthService,
    )
    response = Response()
    cache = AsyncMock()
    cache.health = AsyncMock(return_value=True)
    payload = await health_check(
        response=response,
        session_factory=object(),
        cache=cache,
    )

    assert response.status_code == 200
    assert isinstance(payload, HealthCheckResponse)
    assert payload.status == "healthy"
    assert payload.database == "up"
    assert payload.redis == "up"
    assert payload.application == "up"


@pytest.mark.asyncio
async def test_health_endpoint_reports_redis_down(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.api.routes.health.HealthService",
        _FakeUnhealthyHealthService,
    )
    response = Response()
    cache = AsyncMock()
    cache.health = AsyncMock(return_value=False)
    payload = await health_check(
        response=response,
        session_factory=object(),
        cache=cache,
    )

    assert response.status_code == 503
    assert payload.status == "unhealthy"
    assert payload.redis == "down"
