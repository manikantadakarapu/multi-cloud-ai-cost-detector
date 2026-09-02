"""Unit tests for deterministic anomaly detection without provider calls."""

from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.schemas.anomaly import AnomalyQuery, AnomalySeverity
from app.schemas.explorer import CostRecord
from app.services.anomaly import AnomalyDetectionService, median_mad


class FakeExplorer:
    def __init__(self, records):
        self.records = records
        self.calls = 0

    async def get_cost_records(self, start_date, end_date, provider=None):
        self.calls += 1
        return self.records


class FakeCache:
    def __init__(self):
        self.values = {}
        self.writes = 0

    async def get_json(self, key):
        return self.values.get(key)

    async def set_json(self, key, value, ttl_seconds=None):
        self.writes += 1
        self.values[key] = value.model_dump(mode="json")


def records_for(
    values, service="Compute", provider="aws", account="a-1", region="us-east-1"
):
    start = date(2026, 7, 1)
    return [
        CostRecord(
            date=start + timedelta(days=i),
            provider=provider,
            account_id=account,
            service=service,
            region=region,
            cost=Decimal(str(cost)),
        )
        for i, cost in enumerate(values)
    ]


def query():
    return AnomalyQuery(start_date=date(2026, 7, 8), end_date=date(2026, 7, 8))


def test_median_mad_is_robust_to_single_spike():
    center, mad = median_mad(
        [Decimal("10"), Decimal("10"), Decimal("11"), Decimal("100")]
    )
    assert center == Decimal("10.5")
    assert mad == Decimal("0.5")


@pytest.mark.asyncio
async def test_detects_significant_deviation_and_is_cached():
    explorer = FakeExplorer(records_for([10, 10, 11, 10, 10, 11, 10, 40]))
    cache = FakeCache()
    service = AnomalyDetectionService(explorer=explorer, cache=cache)
    first = await service.detect(query())
    second = await service.detect(query())
    assert first.anomalies[0].actual_cost == Decimal("40.00")
    assert first.anomalies[0].severity is AnomalySeverity.CRITICAL
    assert first.anomalies[0].detection_method.value == "median_mad"
    assert second.anomalies[0].id == first.anomalies[0].id
    assert explorer.calls == 1
    assert cache.writes == 1


@pytest.mark.asyncio
async def test_insufficient_history_and_new_service_are_safe():
    service = AnomalyDetectionService(
        explorer=FakeExplorer(records_for([10, 10, 10, 100]))
    )
    response = await service.detect(query())
    assert response.anomalies == []


@pytest.mark.asyncio
async def test_zero_baseline_uses_explicit_method():
    service = AnomalyDetectionService(
        explorer=FakeExplorer(records_for([0, 0, 0, 0, 0, 0, 0, 5]))
    )
    response = await service.detect(query())
    assert response.anomalies[0].detection_method.value == "zero_baseline"
    assert response.anomalies[0].deviation_percentage is None


@pytest.mark.asyncio
async def test_filters_dimensions_and_sorting():
    records = records_for([10] * 7 + [40], service="Compute") + records_for(
        [10] * 7 + [30], service="Storage"
    )
    service = AnomalyDetectionService(explorer=FakeExplorer(records))
    response = await service.detect(
        AnomalyQuery(
            **{**query().model_dump(), "service": "Storage", "sort_by": "date"}
        )
    )
    assert len(response.anomalies) == 1
    assert response.anomalies[0].service == "Storage"


@pytest.mark.asyncio
async def test_filters_are_applied_before_pagination():
    records = records_for([10] * 7 + [40], service="Compute") + records_for(
        [10] * 7 + [35], service="Storage"
    )
    service = AnomalyDetectionService(explorer=FakeExplorer(records))
    response = await service.detect(
        AnomalyQuery(
            **{
                **query().model_dump(),
                "limit": 1,
                "offset": 1,
                "sort_by": "deviation_amount",
            }
        )
    )
    assert response.total == 2
    assert response.limit == 1
    assert response.offset == 1
    assert len(response.anomalies) == 1
    assert response.anomalies[0].service == "Storage"


def test_query_rejects_invalid_pagination():
    with pytest.raises(ValueError):
        AnomalyQuery(**{**query().model_dump(), "limit": 0})

    with pytest.raises(ValueError):
        AnomalyQuery(**{**query().model_dump(), "limit": 1001})


def test_cache_key_changes_for_filters_and_pagination():
    service = AnomalyDetectionService()
    base = query()
    assert service._cache_key(base) != service._cache_key(
        base.model_copy(update={"service": "Storage"})
    )
    assert service._cache_key(base) != service._cache_key(
        base.model_copy(update={"limit": 1})
    )
