"""Tests for deterministic FinOps optimization recommendations."""

from datetime import date, timedelta
from decimal import Decimal

import pytest
from httpx import AsyncClient
from pydantic import ValidationError

from app.api.routes.optimization import get_optimization_service
from app.core.cache import RedisCache
from app.main import app
from app.schemas.explorer import CostRecord
from app.schemas.optimization import (
    OptimizationQuery,
    RecommendationCategory,
    RecommendationStatus,
)
from app.services.optimization import OptimizationService


class FakeExplorer:
    def __init__(self, records):
        self.records = records
        self.calls = 0

    async def get_cost_records(self, start_date, end_date, provider=None):
        self.calls += 1
        return self.records


class FakeCache(RedisCache):
    def __init__(self):
        self.values = {}
        self.writes = 0

    async def get_json(self, key):
        return self.values.get(key)

    async def set_json(self, key, value, ttl_seconds=None):
        self.writes += 1
        self.values[key] = (
            value.model_dump(mode="json") if hasattr(value, "model_dump") else value
        )


def source_records():
    result = []
    for index in range(30):
        day = date(2026, 8, 1) + timedelta(days=index)
        recent = index >= 15
        result.extend(
            [
                CostRecord(
                    date=day,
                    provider="aws",
                    account_id="account-1",
                    service="Compute",
                    region="us-east-1",
                    cost=Decimal("10.00") if not recent else Decimal("25.00"),
                ),
                CostRecord(
                    date=day,
                    provider="aws",
                    account_id="account-1",
                    service="Storage",
                    region="us-east-1",
                    cost=Decimal("5.00") if not recent else Decimal("9.00"),
                ),
                CostRecord(
                    date=day,
                    provider="azure",
                    account_id="subscription-1",
                    service="Network Transfer",
                    region="eastus",
                    cost=Decimal("1.00") if not recent else Decimal("3.00"),
                ),
            ]
        )
    return result


def query(**updates):
    values = {"start_date": date(2026, 8, 1), "end_date": date(2026, 8, 30)}
    values.update(updates)
    return OptimizationQuery(**values)


@pytest.mark.asyncio
async def test_engine_detects_growth_storage_network_and_high_cost_signals():
    response = await OptimizationService(
        explorer=FakeExplorer(source_records())
    ).list_recommendations(query())
    categories = {item.category for item in response.recommendations}

    assert RecommendationCategory.COST_GROWTH in categories
    assert RecommendationCategory.STORAGE in categories
    assert RecommendationCategory.NETWORK in categories
    assert RecommendationCategory.HIGH_COST_SERVICE in categories
    assert all(item.evidence for item in response.recommendations)


@pytest.mark.asyncio
async def test_savings_are_deterministic_and_deduplicated():
    records = source_records()
    records.append(records[-1])
    service = OptimizationService(explorer=FakeExplorer(records))
    first = await service.list_recommendations(query())
    second = await service.list_recommendations(query())

    assert [item.recommendation_id for item in first.recommendations] == [
        item.recommendation_id for item in second.recommendations
    ]
    assert len({item.recommendation_id for item in first.recommendations}) == len(
        first.recommendations
    )
    growth = next(
        item
        for item in first.recommendations
        if item.category is RecommendationCategory.COST_GROWTH
    )
    assert growth.estimated_monthly_savings is not None
    assert growth.estimated_annual_savings == growth.estimated_monthly_savings * 12


@pytest.mark.asyncio
async def test_insufficient_data_returns_no_recommendations():
    records = source_records()[:6]
    response = await OptimizationService(
        explorer=FakeExplorer(records)
    ).list_recommendations(query(end_date=date(2026, 8, 6)))

    assert response.recommendations == []
    assert response.insufficient_data is True
    assert response.message


@pytest.mark.asyncio
async def test_cache_hit_and_rule_versioned_key():
    cache = FakeCache()
    explorer = FakeExplorer(source_records())
    service = OptimizationService(cache=cache, explorer=explorer)
    await service.list_recommendations(query())
    await service.list_recommendations(query())

    assert explorer.calls == 1
    assert cache.writes == 1
    assert any("optimization-rules-v1" in key for key in cache.values)


@pytest.mark.asyncio
async def test_status_lifecycle_is_scoped_and_persisted():
    cache = FakeCache()
    service = OptimizationService(
        cache=cache, user_scope="user-1", explorer=FakeExplorer(source_records())
    )
    response = await service.list_recommendations(query())
    recommendation_id = response.recommendations[0].recommendation_id

    updated = await service.update_status(
        recommendation_id, RecommendationStatus.REVIEWED, query()
    )
    refreshed = await service.get_recommendation(recommendation_id, query())

    assert updated is not None
    assert refreshed is not None
    assert refreshed.status is RecommendationStatus.REVIEWED


def test_invalid_dates_and_sort_order_are_rejected():
    with pytest.raises(ValidationError):
        OptimizationQuery(start_date=date(2026, 8, 2), end_date=date(2026, 8, 1))
    with pytest.raises(ValidationError):
        OptimizationQuery(
            start_date=date(2026, 8, 1),
            end_date=date(2026, 8, 2),
            sort_order="sideways",
        )


@pytest.mark.asyncio
async def test_optimization_endpoint_requires_authentication(client: AsyncClient):
    response = await client.get(
        "/api/v1/optimization/recommendations",
        params={"start_date": "2026-08-01", "end_date": "2026-08-30"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_optimization_endpoint_status_update(auth_client: AsyncClient):
    service = OptimizationService(explorer=FakeExplorer(source_records()))
    app.dependency_overrides[get_optimization_service] = lambda: service
    try:
        listing = await auth_client.get(
            "/api/v1/optimization/recommendations",
            params={"start_date": "2026-08-01", "end_date": "2026-08-30"},
        )
        recommendation_id = listing.json()["recommendations"][0]["recommendation_id"]
        response = await auth_client.patch(
            f"/api/v1/optimization/recommendations/{recommendation_id}/status",
            json={
                "status": "dismissed",
                "start_date": "2026-08-01",
                "end_date": "2026-08-30",
            },
        )
    finally:
        app.dependency_overrides.pop(get_optimization_service, None)

    assert response.status_code == 200
    assert response.json()["status"] == "dismissed"
