"""Tests for deterministic cost analytics and authenticated endpoints."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from httpx import AsyncClient

from app.api.routes.analytics import get_analytics_service
from app.main import app
from app.providers.base import CloudProvider
from app.providers.schemas import CostResponse, DailyCost, ServiceCost
from app.schemas.analytics import AnalyticsQuery, ComparisonQuery
from app.services.analytics.exceptions import AnalyticsCurrencyError
from app.services.analytics.service import AnalyticsService


class _AnalyticsProvider(CloudProvider):
    def __init__(self, name: str, response: CostResponse) -> None:
        self._name = name
        self._response = response

    def provider_name(self) -> str:
        return self._name

    def authenticate(self) -> None:
        return None

    def validate_credentials(self) -> bool:
        return True

    async def get_costs(
        self,
        start_date: date,
        end_date: date,
        granularity: str,
    ) -> CostResponse:
        return self._response


class _PeriodProvider(_AnalyticsProvider):
    def __init__(
        self,
        name: str,
        current_response: CostResponse,
        previous_response: CostResponse,
    ) -> None:
        super().__init__(name, current_response)
        self._previous_response = previous_response

    async def get_costs(
        self,
        start_date: date,
        end_date: date,
        granularity: str,
    ) -> CostResponse:
        if start_date < date(2026, 8, 1):
            return self._previous_response
        return self._response


def _response(
    provider: str,
    total: str,
    services: list[tuple[str, str]],
    daily: list[tuple[str, str]] | None = None,
    currency: str = "USD",
) -> CostResponse:
    return CostResponse(
        provider=provider,
        currency=currency,
        total_cost=float(total),
        date_range={
            "start": "2026-08-01",
            "end": "2026-08-03",
            "granularity": "DAILY",
        },
        services=[
            ServiceCost(service_name=name, cost=float(cost)) for name, cost in services
        ],
        daily_costs=[
            DailyCost(date=day, cost=float(cost)) for day, cost in (daily or [])
        ],
    )


def _service(
    responses: dict[str, CostResponse],
) -> AnalyticsService:
    return AnalyticsService(
        provider_factory=lambda name: _AnalyticsProvider(name, responses[name])
    )


@pytest.mark.asyncio
async def test_summary_provider_service_percentages_and_top_n() -> None:
    service = _service(
        {
            "aws": _response("aws", "100", [("EC2", "70"), ("S3", "30")]),
            "azure": _response("azure", "50", [("SQL", "50")]),
            "gcp": _response("gcp", "0", []),
        }
    )

    result = await service.summary(
        AnalyticsQuery(
            start_date=date(2026, 8, 1),
            end_date=date(2026, 8, 3),
            top_n=2,
        )
    )

    assert result.total_cost == Decimal("150.00")
    assert [(item.provider, item.cost) for item in result.providers] == [
        ("aws", Decimal("100.00")),
        ("azure", Decimal("50.00")),
        ("gcp", Decimal("0.00")),
    ]
    assert result.providers[0].percentage == Decimal("66.67")
    assert [(item.service_name, item.cost) for item in result.top_services] == [
        ("EC2", Decimal("70.00")),
        ("SQL", Decimal("50.00")),
    ]


@pytest.mark.asyncio
async def test_daily_trends_fill_missing_days_with_zero() -> None:
    service = _service(
        {
            "aws": _response(
                "aws",
                "30",
                [("EC2", "30")],
                [("2026-08-01", "10"), ("2026-08-03", "20")],
            )
        }
    )

    result = await service.trends(
        AnalyticsQuery(
            start_date=date(2026, 8, 1), end_date=date(2026, 8, 3), provider="aws"
        )
    )

    assert [item.cost for item in result] == [
        Decimal("10.00"),
        Decimal("0.00"),
        Decimal("20.00"),
    ]


@pytest.mark.asyncio
async def test_comparison_handles_zero_previous_period() -> None:
    service = AnalyticsService(
        provider_factory=lambda name: _PeriodProvider(
            name,
            _response("aws", "25", [("EC2", "25")]),
            _response("aws", "0", []),
        )
    )
    query = ComparisonQuery(
        current_start_date=date(2026, 8, 1),
        current_end_date=date(2026, 8, 3),
        previous_start_date=date(2026, 7, 29),
        previous_end_date=date(2026, 7, 31),
        provider="aws",
    )

    result = await service.compare(query)

    assert result.absolute_change == Decimal("25.00")
    assert result.percentage_change is None


@pytest.mark.asyncio
async def test_currency_mismatch_is_rejected() -> None:
    service = _service(
        {
            "aws": _response("aws", "10", [("EC2", "10")], currency="USD"),
            "azure": _response("azure", "20", [("SQL", "20")], currency="EUR"),
            "gcp": _response("gcp", "0", [], currency="USD"),
        }
    )

    with pytest.raises(AnalyticsCurrencyError):
        await service.summary(
            AnalyticsQuery(
                start_date=date(2026, 8, 1),
                end_date=date(2026, 8, 3),
            )
        )


@pytest.mark.asyncio
async def test_drivers_are_sorted_and_limited() -> None:
    service = AnalyticsService(
        provider_factory=lambda name: _PeriodProvider(
            name,
            _response("aws", "120", [("EC2", "120")]),
            _response("aws", "20", [("EC2", "20")]),
        )
    )
    query = ComparisonQuery(
        current_start_date=date(2026, 8, 1),
        current_end_date=date(2026, 8, 3),
        previous_start_date=date(2026, 7, 29),
        previous_end_date=date(2026, 7, 31),
        provider="aws",
        top_n=1,
    )

    result = await service.drivers(query, top_n=1)

    assert len(result.drivers) == 1
    assert result.drivers[0].absolute_change == Decimal("100.00")


@pytest.mark.asyncio
async def test_analytics_endpoint_requires_authentication(client: AsyncClient) -> None:
    response = await client.get(
        "/api/v1/analytics/summary",
        params={"start_date": "2026-08-01", "end_date": "2026-08-03"},
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_analytics_endpoint_returns_explicit_schema(
    auth_client: AsyncClient,
) -> None:
    async def override_service() -> AnalyticsService:
        return _service({"aws": _response("aws", "10", [("EC2", "10")])})

    app.dependency_overrides[get_analytics_service] = override_service
    try:
        response = await auth_client.get(
            "/api/v1/analytics/summary",
            params={
                "start_date": "2026-08-01",
                "end_date": "2026-08-03",
                "provider": "aws",
            },
        )
    finally:
        app.dependency_overrides.pop(get_analytics_service, None)

    assert response.status_code == 200
    assert response.json()["total_cost"] == "10.00"
    assert response.json()["providers"][0]["provider"] == "aws"
