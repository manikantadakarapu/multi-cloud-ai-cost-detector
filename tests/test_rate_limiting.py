"""Tests for request rate limiting on provider cost endpoints."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.api.routes.aws import aws_cost_aggregator_dependency, aws_provider_dependency
from app.auth.dependencies import get_current_active_user
from app.auth.models import User
from app.core.config import settings
from app.main import app
from app.providers import CostResponse, ServiceCost
from app.services.cost_aggregator import CostAggregatorService


def _build_mock_provider() -> MagicMock:
    provider = MagicMock()
    provider.provider_name.return_value = "aws"
    provider.get_costs = AsyncMock(
        return_value=CostResponse(
            provider="aws",
            currency="USD",
            total_cost=1.0,
            date_range={
                "start": "2024-01-01",
                "end": "2024-01-01",
                "granularity": "DAILY",
            },
            services=[ServiceCost(service_name="Compute", cost=1.0)],
        )
    )
    return provider


@pytest_asyncio.fixture
async def auth_client() -> AsyncClient:
    async def _current_user() -> User:
        return User(
            id=uuid4(),
            email="rate-limit@example.com",
            full_name="Rate Limit Test",
            password_hash="unused",
            is_active=True,
        )

    provider = _build_mock_provider()

    async def _provider() -> MagicMock:
        return provider

    async def _aggregator() -> CostAggregatorService:
        return CostAggregatorService("aws", provider, cache=None)

    app.dependency_overrides[get_current_active_user] = _current_user
    app.dependency_overrides[aws_provider_dependency] = _provider
    app.dependency_overrides[aws_cost_aggregator_dependency] = _aggregator
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_cost_endpoint_is_rate_limited(auth_client: AsyncClient) -> None:
    limit = settings.rate_limit_per_minute

    for _ in range(limit):
        response = await auth_client.get(
            "/api/v1/aws/costs",
            params={
                "start_date": "2024-01-01",
                "end_date": "2024-01-01",
            },
        )
        assert response.status_code == 200

    response = await auth_client.get(
        "/api/v1/aws/costs",
        params={
            "start_date": "2024-01-01",
            "end_date": "2024-01-01",
        },
    )
    assert response.status_code == 429
    assert response.json()["detail"] == "Rate limit exceeded"
