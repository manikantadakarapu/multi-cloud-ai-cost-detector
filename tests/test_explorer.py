"""Tests for Cost Explorer schemas, service, and API routes."""

from datetime import date, timedelta
from decimal import Decimal

import pytest
from httpx import AsyncClient

from app.api.routes.explorer import get_explorer_service
from app.core.cache import RedisCache
from app.main import app
from app.providers.base import CloudProvider
from app.providers.schemas import CostResponse, DailyCost, ServiceCost
from app.schemas.explorer import (
    CostRecord,
    ExplorerQuery,
)
from app.services.explorer.service import CostExplorerService


class MockProvider(CloudProvider):
    def __init__(
        self, name: str, total_cost: float, services: list[tuple[str, float]]
    ) -> None:
        self._name = name
        self._total = total_cost
        self._services = services

    def provider_name(self) -> str:
        return self._name

    def authenticate(self) -> None:
        pass

    def validate_credentials(self) -> bool:
        return True

    async def get_costs(
        self, start_date: date, end_date: date, granularity: str
    ) -> CostResponse:
        return CostResponse(
            provider=self._name,
            currency="USD",
            total_cost=self._total,
            date_range={
                "start": start_date.isoformat(),
                "end": end_date.isoformat(),
                "granularity": granularity,
            },
            services=[ServiceCost(service_name=s, cost=c) for s, c in self._services],
            daily_costs=[
                DailyCost(date=start_date, cost=self._total * 0.4),
                DailyCost(date=end_date, cost=self._total * 0.6),
            ],
        )


class MockExplorerRichProvider(CloudProvider):
    def __init__(self, name: str, records: list[CostRecord]) -> None:
        self._name = name
        self._records = records

    def provider_name(self) -> str:
        return self._name

    def authenticate(self) -> None:
        pass

    def validate_credentials(self) -> bool:
        return True

    async def get_costs(
        self, start_date: date, end_date: date, granularity: str
    ) -> CostResponse:
        total = sum(float(r.cost) for r in self._records)
        return CostResponse(
            provider=self._name,
            currency="USD",
            total_cost=total,
            date_range={
                "start": start_date.isoformat(),
                "end": end_date.isoformat(),
                "granularity": granularity,
            },
            services=[],
            daily_costs=[],
        )

    async def get_explorer_records(
        self, start_date: date, end_date: date, granularity: str
    ) -> list[CostRecord]:
        return [r for r in self._records if start_date <= r.date <= end_date]


class InMemoryCache(RedisCache):
    def __init__(self) -> None:
        self.store: dict[str, str] = {}

    async def get(self, key: str) -> str | None:
        return self.store.get(key)

    async def set(self, key: str, value: str, ttl: int | None = None) -> None:
        self.store[key] = value


# --- Schema Unit Tests ---


def test_explorer_query_validation_success() -> None:
    today = date.today()
    yesterday = today - timedelta(days=1)
    q = ExplorerQuery(
        start_date=yesterday,
        end_date=today,
        service="  EC2  ",
        region="  us-east-1 ",
    )
    assert q.service == "EC2"
    assert q.region == "us-east-1"
    assert q.limit == 100
    assert q.offset == 0


def test_explorer_query_validation_invalid_dates() -> None:
    today = date.today()
    tomorrow = today + timedelta(days=1)
    with pytest.raises(ValueError, match="end_date must be on or after start_date"):
        ExplorerQuery(start_date=tomorrow, end_date=today)


# --- Service Unit Tests ---


@pytest.mark.asyncio
async def test_explorer_service_multi_provider_aggregation() -> None:
    providers = {
        "aws": MockProvider("aws", 100.0, [("AmazonEC2", 70.0), ("AmazonS3", 30.0)]),
        "azure": MockProvider("azure", 50.0, [("Virtual Machines", 50.0)]),
        "gcp": MockProvider("gcp", 30.0, [("Compute Engine", 30.0)]),
    }

    service = CostExplorerService(
        cache=None, provider_factory=lambda name: providers[name]
    )

    start = date(2026, 8, 1)
    end = date(2026, 8, 10)
    query = ExplorerQuery(start_date=start, end_date=end)

    response = await service.get_explorer_data(query)

    assert response.overview.total_cost == Decimal("180.00")
    assert response.overview.currency == "USD"
    assert response.total_records > 0

    # Provider breakdown
    by_provider = {p.key: p.cost for p in response.dimension_totals.by_provider}
    assert by_provider["aws"] == Decimal("100.00")
    assert by_provider["azure"] == Decimal("50.00")
    assert by_provider["gcp"] == Decimal("30.00")

    # Available filters
    assert set(response.available_filters.providers) == {"aws", "azure", "gcp"}
    assert "AmazonEC2" in response.available_filters.services


@pytest.mark.asyncio
async def test_explorer_service_filtering_and_drilldown() -> None:
    records = [
        CostRecord(
            date=date(2026, 8, 5),
            provider="aws",
            account_id="111122223333",
            account_name="Production AWS",
            service="AmazonEC2",
            region="us-east-1",
            cost=Decimal("45.50"),
            currency="USD",
        ),
        CostRecord(
            date=date(2026, 8, 5),
            provider="aws",
            account_id="111122223333",
            account_name="Production AWS",
            service="AmazonS3",
            region="us-west-2",
            cost=Decimal("15.20"),
            currency="USD",
        ),
        CostRecord(
            date=date(2026, 8, 5),
            provider="azure",
            account_id="sub-abc",
            account_name="Azure Core",
            service="Virtual Machines",
            region="eastus",
            cost=Decimal("20.00"),
            currency="USD",
        ),
    ]

    rich_provider = MockExplorerRichProvider("aws", records)
    service = CostExplorerService(
        cache=None,
        provider_factory=lambda name: (
            rich_provider if name == "aws" else MockProvider(name, 0.0, [])
        ),
    )

    # Filter by service
    q = ExplorerQuery(
        start_date=date(2026, 8, 1),
        end_date=date(2026, 8, 10),
        provider="aws",
        service="EC2",
    )
    res = await service.get_explorer_data(q)
    assert res.overview.total_cost == Decimal("45.50")
    assert len(res.records) == 1
    assert res.records[0].service == "AmazonEC2"
    assert res.records[0].region == "us-east-1"


@pytest.mark.asyncio
async def test_explorer_service_caching_behavior() -> None:
    cache = InMemoryCache()
    provider = MockProvider("aws", 50.0, [("AmazonEC2", 50.0)])
    service = CostExplorerService(cache=cache, provider_factory=lambda name: provider)

    query = ExplorerQuery(
        start_date=date(2026, 8, 1), end_date=date(2026, 8, 5), provider="aws"
    )

    # First call: populates cache
    res1 = await service.get_explorer_data(query)
    assert len(cache.store) == 1

    # Second call: reads from cache
    res2 = await service.get_explorer_data(query)
    assert res1.overview.total_cost == res2.overview.total_cost
    assert res1.records == res2.records


# --- API Route Integration Tests ---


@pytest.mark.asyncio
async def test_explorer_api_unauthenticated(client: AsyncClient) -> None:
    response = await client.get(
        "/api/v1/explorer?start_date=2026-08-01&end_date=2026-08-10"
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_explorer_api_authenticated(auth_client: AsyncClient) -> None:
    providers = {
        "aws": MockProvider("aws", 100.0, [("AmazonEC2", 70.0), ("AmazonS3", 30.0)]),
        "azure": MockProvider("azure", 50.0, [("Virtual Machines", 50.0)]),
        "gcp": MockProvider("gcp", 30.0, [("Compute Engine", 30.0)]),
    }
    test_service = CostExplorerService(
        cache=None, provider_factory=lambda name: providers[name]
    )

    app.dependency_overrides[get_explorer_service] = lambda: test_service
    try:
        response = await auth_client.get(
            "/api/v1/explorer",
            params={
                "start_date": "2026-08-01",
                "end_date": "2026-08-10",
                "provider": "aws",
            },
        )
    finally:
        app.dependency_overrides.pop(get_explorer_service, None)

    assert response.status_code == 200
    data = response.json()
    assert "overview" in data
    assert "records" in data
    assert "dimension_totals" in data
    assert "available_filters" in data
    assert data["overview"]["currency"] == "USD"
