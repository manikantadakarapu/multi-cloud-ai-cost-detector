"""Focused tests for the frontend-ready dashboard contracts."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from httpx import AsyncClient

from app.api.routes.dashboard import get_dashboard_service
from app.main import app
from app.providers.base import CloudProvider
from app.providers.schemas import CostResponse, DailyCost, ServiceCost
from app.schemas.analytics import AnalyticsQuery
from app.schemas.dashboard import DashboardSummary
from app.schemas.insights import InsightType
from app.services.ai.insights import AIInsightService
from app.services.analytics.service import AnalyticsService
from app.services.dashboard import DashboardService


class _DashboardProvider(CloudProvider):
    def __init__(self, name: str) -> None:
        self._name = name

    def provider_name(self) -> str:
        return self._name

    def authenticate(self) -> None:
        return None

    def validate_credentials(self) -> bool:
        return True

    async def get_costs(
        self, start_date: date, end_date: date, granularity: str
    ) -> CostResponse:
        previous = start_date < date(2026, 8, 1)
        total = 40 if previous else 100
        service_cost = 20 if previous else 80
        daily_total = 20 if previous else 50
        return CostResponse(
            provider=self._name,
            currency="USD",
            total_cost=total,
            date_range={
                "start": start_date.isoformat(),
                "end": end_date.isoformat(),
                "granularity": granularity,
            },
            services=[ServiceCost(service_name="EC2", cost=service_cost)],
            daily_costs=[
                DailyCost(date=start_date, cost=daily_total),
                DailyCost(date=end_date, cost=total - daily_total),
            ],
        )


class _FakeCache:
    def __init__(self) -> None:
        self.values: dict[str, dict] = {}
        self.writes = 0

    async def get_json(self, key: str):  # noqa: ANN001
        return self.values.get(key)

    async def set_json(
        self, key: str, value, ttl_seconds: int | None = None
    ):  # noqa: ANN001
        self.values[key] = value.model_dump(mode="json")
        self.writes += 1


def _service(cache: _FakeCache | None = None) -> DashboardService:
    analytics = AnalyticsService(
        cache=cache,
        provider_factory=lambda name: _DashboardProvider(name),
    )
    return DashboardService(
        analytics=analytics,
        cache=cache,
        user_scope="test-user",
        ai_service=AIInsightService(enabled=False),
    )


def _query() -> AnalyticsQuery:
    return AnalyticsQuery(
        start_date=date(2026, 8, 1),
        end_date=date(2026, 8, 3),
        provider="aws",
        top_n=3,
    )


@pytest.mark.asyncio
async def test_dashboard_summary_composes_frontend_contract() -> None:
    result = await _service().summary(_query())

    assert isinstance(result, DashboardSummary)
    assert result.overview.total_cost == Decimal("100.00")
    assert result.overview.previous_period_cost == Decimal("40.00")
    assert result.overview.absolute_change == Decimal("60.00")
    assert result.providers[0].provider == "aws"
    assert [item.date for item in result.trend] == [
        date(2026, 8, 1),
        date(2026, 8, 2),
        date(2026, 8, 3),
    ]
    assert result.trend[1].cost == Decimal("0.00")


@pytest.mark.asyncio
async def test_dashboard_insights_include_increase_and_driver() -> None:
    result = await _service().insights(_query())

    assert [item.type for item in result.insights] == [
        InsightType.COST_INCREASE,
        InsightType.TOP_COST_DRIVER,
    ]
    assert result.insights[1].provider == "aws"
    assert result.insights[1].service == "EC2"
    assert result.insights[1].impact == Decimal("60.00")
    assert result.insights[0].severity.value == "high"


@pytest.mark.asyncio
async def test_dashboard_summary_reuses_dashboard_cache() -> None:
    cache = _FakeCache()
    service = _service(cache)

    await service.summary(_query())
    writes_after_first = cache.writes
    await service.summary(_query())

    assert writes_after_first > 0
    assert cache.writes == writes_after_first


@pytest.mark.asyncio
async def test_dashboard_endpoint_requires_authentication(client: AsyncClient) -> None:
    response = await client.get(
        "/api/v1/dashboard/summary",
        params={"start_date": "2026-08-01", "end_date": "2026-08-03"},
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_dashboard_endpoint_returns_explicit_schema(
    auth_client: AsyncClient,
) -> None:
    async def override_service() -> DashboardService:
        return _service()

    app.dependency_overrides[get_dashboard_service] = override_service
    try:
        response = await auth_client.get(
            "/api/v1/dashboard/summary",
            params={
                "start_date": "2026-08-01",
                "end_date": "2026-08-03",
                "provider": "aws",
            },
        )
    finally:
        app.dependency_overrides.pop(get_dashboard_service, None)

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"overview", "providers", "services", "trend", "drivers"}
    assert body["overview"]["currency"] == "USD"


@pytest.mark.asyncio
async def test_dashboard_insights_endpoint_returns_schema(
    auth_client: AsyncClient,
) -> None:
    async def override_service() -> DashboardService:
        return _service()

    app.dependency_overrides[get_dashboard_service] = override_service
    try:
        response = await auth_client.get(
            "/api/v1/dashboard/insights",
            params={
                "start_date": "2026-08-01",
                "end_date": "2026-08-03",
                "provider": "aws",
            },
        )
    finally:
        app.dependency_overrides.pop(get_dashboard_service, None)

    assert response.status_code == 200, f"422 body: {response.json()}"
    body = response.json()
    assert body["insights"][0]["type"] == "cost_increase"
    assert body["ai_insights"] == []
    assert body["ai_status"] == "disabled"


def test_dashboard_query_rejects_invalid_date_range() -> None:
    with pytest.raises(ValueError, match="end_date must be on or after start_date"):
        AnalyticsQuery(start_date=date(2026, 8, 4), end_date=date(2026, 8, 1))
