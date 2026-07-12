"""Tests for the provider-independent cost aggregation service."""

from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.cache import RedisCache
from app.providers.exceptions import ProviderError
from app.providers.schemas import CostResponse, ServiceCost
from app.services.cost_aggregator import CostAggregatorService


def _build_response(provider: str = "aws") -> CostResponse:
    return CostResponse(
        provider=provider,
        currency="USD",
        total_cost=12.34,
        date_range={
            "start": "2024-01-01",
            "end": "2024-01-31",
            "granularity": "DAILY",
        },
        services=[ServiceCost(service_name="Compute", cost=12.34)],
    )


@pytest.mark.asyncio
async def test_cost_aggregator_returns_cached_payload() -> None:
    provider = MagicMock()
    provider.provider_name.return_value = "aws"
    provider.get_costs = AsyncMock(return_value=_build_response())

    cache = MagicMock(spec=RedisCache)
    cache.get_json = AsyncMock(return_value=_build_response().model_dump(mode="json"))
    cache.set_json = AsyncMock()

    service = CostAggregatorService("aws", provider, cache)
    result = await service.get_costs(
        start_date=date(2024, 1, 1),
        end_date=date(2024, 1, 31),
        granularity="DAILY",
    )

    assert result.provider == "aws"
    provider.get_costs.assert_not_awaited()
    cache.set_json.assert_not_awaited()


@pytest.mark.asyncio
async def test_cost_aggregator_populates_cache_on_miss() -> None:
    provider = MagicMock()
    provider.provider_name.return_value = "azure"
    provider.get_costs = AsyncMock(return_value=_build_response("azure"))

    cache = MagicMock(spec=RedisCache)
    cache.get_json = AsyncMock(return_value=None)
    cache.set_json = AsyncMock()

    service = CostAggregatorService("azure", provider, cache)
    result = await service.get_costs(
        start_date=date(2024, 1, 1),
        end_date=date(2024, 1, 31),
        granularity="DAILY",
    )

    assert result.provider == "azure"
    provider.get_costs.assert_awaited_once()
    cache.set_json.assert_awaited_once()


@pytest.mark.asyncio
async def test_cost_aggregator_rejects_provider_mismatch() -> None:
    provider = MagicMock()
    provider.provider_name.return_value = "aws"
    provider.get_costs = AsyncMock(return_value=_build_response())

    cache = MagicMock(spec=RedisCache)
    cache.get_json = AsyncMock(return_value=None)
    cache.set_json = AsyncMock()

    with pytest.raises(ProviderError):
        CostAggregatorService("azure", provider, cache)
