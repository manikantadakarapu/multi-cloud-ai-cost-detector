"""Tests for deterministic provider-independent cost forecasting."""

from datetime import date, timedelta
from decimal import Decimal

import pytest
from httpx import AsyncClient
from pydantic import ValidationError

from app.api.routes.forecast import get_forecasting_service
from app.core.cache import RedisCache
from app.main import app
from app.schemas.explorer import CostRecord
from app.schemas.forecast import (
    ForecastDimension,
    ForecastQuery,
    ForecastStatus,
)
from app.services.forecasting import ForecastingService, calculate_accuracy


class FakeExplorer:
    def __init__(self, records: list[CostRecord]):
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
        self.values[key] = value.model_dump(mode="json")


def records(days: int = 30, start: date = date(2026, 8, 1)) -> list[CostRecord]:
    result = []
    for index in range(days):
        day = start + timedelta(days=index)
        result.extend(
            [
                CostRecord(
                    date=day,
                    provider="aws",
                    account_id="account-1",
                    service="Compute",
                    region="us-east-1",
                    cost=Decimal(str(10 + index)),
                ),
                CostRecord(
                    date=day,
                    provider="azure",
                    account_id="subscription-1",
                    service="SQL",
                    region="eastus",
                    cost=Decimal("5.00"),
                ),
            ]
        )
    return result


def query(**overrides) -> ForecastQuery:
    values = {
        "start_date": date(2026, 8, 1),
        "end_date": date(2026, 8, 30),
        "horizon_days": 7,
    }
    values.update(overrides)
    return ForecastQuery(**values)


@pytest.mark.asyncio
async def test_forecast_is_deterministic_and_supports_horizon():
    service = ForecastingService(explorer=FakeExplorer(records()))
    first = await service.forecast(query(horizon_days=14))
    second = await service.forecast(query(horizon_days=14))

    assert first.status is ForecastStatus.READY
    assert len(first.forecasts[0].daily_forecast) == 14
    assert first.forecasts[0].projected_cost == second.forecasts[0].projected_cost
    assert first.forecasts[0].lower_bound <= first.forecasts[0].projected_cost
    assert first.forecasts[0].projected_cost <= first.forecasts[0].upper_bound


@pytest.mark.asyncio
async def test_forecast_supports_provider_and_service_dimensions():
    service = ForecastingService(explorer=FakeExplorer(records()))
    by_provider = await service.forecast(query(dimension=ForecastDimension.PROVIDER))
    by_service = await service.forecast(query(dimension=ForecastDimension.SERVICE))

    assert {item.dimension_value for item in by_provider.forecasts} == {"aws", "azure"}
    assert {item.dimension_value for item in by_service.forecasts} == {"Compute", "SQL"}


@pytest.mark.asyncio
async def test_insufficient_and_empty_data_are_explicit():
    short = ForecastingService(explorer=FakeExplorer(records(4)))
    empty = ForecastingService(explorer=FakeExplorer([]))

    short_result = await short.forecast(query(end_date=date(2026, 8, 4)))
    empty_result = await empty.forecast(query())

    assert short_result.status is ForecastStatus.INSUFFICIENT_DATA
    assert short_result.forecasts == []
    assert short_result.data_quality.required_observations == 7
    assert empty_result.status is ForecastStatus.EMPTY
    assert empty_result.summary.projected_spend == Decimal("0")


@pytest.mark.asyncio
async def test_missing_dates_duplicates_and_recent_spike_are_transparent():
    source = records(30)
    missing_day = date(2026, 8, 12)
    source = [record for record in source if record.date != missing_day]
    source.append(source[-1])
    source.append(
        CostRecord(
            date=date(2026, 8, 29),
            provider="aws",
            account_id="account-1",
            service="Compute",
            region="us-east-1",
            cost=Decimal("1000.00"),
        )
    )
    result = await ForecastingService(explorer=FakeExplorer(source)).forecast(query())

    assert result.status is ForecastStatus.READY
    assert missing_day in result.data_quality.missing_dates
    assert result.data_quality.duplicate_records_removed == 1
    assert date(2026, 8, 29) in result.data_quality.excluded_anomaly_dates


def test_invalid_horizon_and_bounds_are_rejected():
    with pytest.raises(ValidationError):
        ForecastQuery(
            start_date=date(2026, 8, 1), end_date=date(2026, 8, 30), horizon_days=8
        )


@pytest.mark.asyncio
async def test_cache_hit_avoids_recalculation():
    cache = FakeCache()
    explorer = FakeExplorer(records())
    service = ForecastingService(cache=cache, explorer=explorer)

    await service.forecast(query())
    await service.forecast(query())

    assert explorer.calls == 1
    assert cache.writes == 1


@pytest.mark.asyncio
async def test_forecast_endpoint_requires_authentication(client: AsyncClient):
    response = await client.get(
        "/api/v1/forecast",
        params={"start_date": "2026-08-01", "end_date": "2026-08-30"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_forecast_endpoint_returns_typed_response(auth_client: AsyncClient):
    service = ForecastingService(explorer=FakeExplorer(records()))
    app.dependency_overrides[get_forecasting_service] = lambda: service
    try:
        response = await auth_client.get(
            "/api/v1/forecast",
            params={
                "start_date": "2026-08-01",
                "end_date": "2026-08-30",
                "horizon_days": 30,
            },
        )
    finally:
        app.dependency_overrides.pop(get_forecasting_service, None)

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "ready"
    assert len(response.json()["forecasts"][0]["daily_forecast"]) == 30


@pytest.mark.asyncio
async def test_completed_forecast_accuracy_uses_only_matching_actuals():
    response = await ForecastingService(explorer=FakeExplorer(records())).forecast(
        query()
    )
    forecast = response.forecasts[0]
    actuals = {
        point.date: point.forecast_cost + Decimal("1.00")
        for point in forecast.daily_forecast
    }

    accuracy = calculate_accuracy(forecast, actuals)

    assert accuracy.observations == 7
    assert accuracy.mean_absolute_error == Decimal("1.00")
