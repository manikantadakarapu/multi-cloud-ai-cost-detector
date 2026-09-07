from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from httpx import AsyncClient
from pydantic import ValidationError

from app.budgets.models import Budget
from app.budgets.service import BudgetEvaluationService
from app.schemas.budgets import BudgetCreate, BudgetStatus
from app.schemas.explorer import CostRecord
from app.schemas.forecast import ForecastStatus


class FakeExplorer:
    def __init__(self, records: list[CostRecord]):
        self.records = records
        self.calls = 0

    async def get_cost_records(self, start_date, end_date, provider=None):
        self.calls += 1
        return self.records


class FakeForecasting:
    def __init__(self, status=ForecastStatus.INSUFFICIENT_DATA, daily=None):
        self.status = status
        self.daily = daily or []
        self.calls = 0

    async def forecast(self, query):
        self.calls += 1
        if self.status is not ForecastStatus.READY:
            return type(
                "ForecastResponse", (), {"status": self.status, "forecasts": []}
            )()
        result = type(
            "ForecastResult",
            (),
            {"currency": "USD", "daily_forecast": self.daily},
        )()
        return type(
            "ForecastResponse", (), {"status": self.status, "forecasts": [result]}
        )()


class FakeCache:
    def __init__(self):
        self.values = {}
        self.writes = 0

    async def get_json(self, key):
        return self.values.get(key)

    async def set_json(self, key, value, ttl_seconds=None):
        self.values[key] = value.model_dump(mode="json")
        self.writes += 1


def make_budget(**overrides) -> Budget:
    values = {
        "id": uuid4(),
        "user_id": uuid4(),
        "name": "Monthly cloud budget",
        "scope": "total",
        "provider": None,
        "account_id": None,
        "service": None,
        "region": None,
        "period": "monthly",
        "amount": Decimal("100"),
        "currency": "USD",
        "warning_threshold": Decimal("80"),
        "critical_threshold": Decimal("90"),
        "enabled": True,
        "updated_at": datetime(2026, 9, 1, tzinfo=UTC),
    }
    values.update(overrides)
    return Budget(**values)


def make_service(records, forecasting=None, cache=None):
    explorer = FakeExplorer(records)
    service = BudgetEvaluationService(
        explorer=explorer,
        forecasting=forecasting or FakeForecasting(),
        cache=cache,
        user_scope="user-1",
        now=lambda *_: datetime(2026, 9, 7, tzinfo=UTC),
    )
    return service, explorer


def record(cost: str, currency: str = "USD") -> CostRecord:
    return CostRecord(
        date=date(2026, 9, 7),
        provider="aws",
        account_id="account-1",
        service="AmazonEC2",
        region="us-east-1",
        cost=Decimal(cost),
        currency=currency,
    )


@pytest.mark.parametrize(
    ("cost", "expected"),
    [
        ("79.99", BudgetStatus.HEALTHY),
        ("80", BudgetStatus.WARNING),
        ("90", BudgetStatus.CRITICAL),
        ("100", BudgetStatus.CRITICAL),
        ("100.01", BudgetStatus.EXCEEDED),
    ],
)
@pytest.mark.asyncio
async def test_actual_status_boundaries_are_deterministic(cost, expected):
    service, _ = make_service([record(cost)])
    result = await service.evaluate(make_budget())
    assert result.actual_status is expected
    assert result.actual_spend == Decimal(cost).quantize(Decimal("0.01"))


@pytest.mark.asyncio
async def test_forecast_status_is_separate_from_actual_status():
    forecast = FakeForecasting(
        ForecastStatus.READY,
        [
            type(
                "DailyForecast",
                (),
                {"date": date(2026, 9, 8), "forecast_cost": Decimal("19")},
            )()
        ],
    )
    service, _ = make_service([record("82")], forecast)
    result = await service.evaluate(make_budget())
    assert result.actual_status is BudgetStatus.WARNING
    assert result.forecast_status is BudgetStatus.EXCEEDED
    assert result.forecast_spend == Decimal("101.00")
    assert result.forecast_variance == Decimal("1.00")
    assert "Forecasted spend" in result.reason


@pytest.mark.asyncio
async def test_missing_cost_and_forecast_data_are_explicit():
    service, _ = make_service([])
    result = await service.evaluate(make_budget())
    assert result.actual_status is BudgetStatus.UNAVAILABLE
    assert result.forecast_status is BudgetStatus.UNAVAILABLE
    assert result.data_available is False
    assert result.forecast_spend is None

    service, _ = make_service([record("12")])
    result = await service.evaluate(make_budget())
    assert result.actual_status is BudgetStatus.HEALTHY
    assert result.forecast_status is BudgetStatus.UNAVAILABLE
    assert result.forecast_spend is None


@pytest.mark.asyncio
async def test_disabled_budget_does_not_read_cost_data():
    service, explorer = make_service([record("120")])
    result = await service.evaluate(make_budget(enabled=False))
    assert result.actual_status is BudgetStatus.DISABLED
    assert result.forecast_status is BudgetStatus.DISABLED
    assert explorer.calls == 0


@pytest.mark.asyncio
async def test_currency_mismatch_is_not_silently_converted():
    service, _ = make_service([record("12", currency="EUR")])
    with pytest.raises(Exception, match="Currency mismatch"):
        await service.evaluate(make_budget())


@pytest.mark.asyncio
async def test_evaluation_cache_is_scoped_and_reused():
    cache = FakeCache()
    forecasting = FakeForecasting()
    service, explorer = make_service([record("12")], forecasting, cache)
    budget = make_budget()
    await service.evaluate(budget)
    await service.evaluate(budget)
    assert cache.writes == 1
    assert explorer.calls == 1
    assert forecasting.calls == 1


def test_budget_validation_rejects_invalid_amount_and_threshold_order():
    with pytest.raises(ValidationError):
        BudgetCreate(name="Invalid", amount=0)
    with pytest.raises(ValidationError):
        BudgetCreate(
            name="Invalid", amount=100, warning_threshold=90, critical_threshold=80
        )


@pytest.mark.asyncio
async def test_budget_api_requires_authentication(client: AsyncClient):
    response = await client.get("/api/v1/budgets")
    assert response.status_code == 401
