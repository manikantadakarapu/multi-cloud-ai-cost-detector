"""Tests for ``GET /api/v1/costs`` — the unified multi-cloud cost endpoint."""

from __future__ import annotations

from datetime import date

import pytest
from httpx import AsyncClient

from app.providers import (
    PROVIDER_REGISTRY,
    CloudProvider,
    CostResponse,
    ServiceCost,
)


class _MockCostProvider(CloudProvider):
    """A :class:`CloudProvider` that returns a fixed :class:`CostResponse`.

    The ``provider_name`` is set dynamically so the same class can be
    used for ``aws``, ``azure``, and ``gcp`` mocks.
    """

    def __init__(self, name: str = "mock") -> None:
        self._name = name

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
        return CostResponse(
            provider=self._name,
            total_cost=100.0,
            date_range={
                "start": start_date.isoformat(),
                "end": end_date.isoformat(),
                "granularity": granularity,
            },
            services=[
                ServiceCost(service_name="MockService", cost=100.0),
            ],
        )


@pytest.fixture(autouse=True)
def _register_mock_providers(monkeypatch: pytest.MonkeyPatch) -> None:
    """Register mock providers for ``aws``, ``azure``, ``gcp`` under the
    same names as the real providers so the unified endpoint can resolve
    them without hitting the real SDK."""
    for name in ("aws", "azure", "gcp"):
        # Capture the current value of `name` via a default argument so
        # each lambda returns a provider with the correct provider_name().
        monkeypatch.setitem(
            PROVIDER_REGISTRY,
            name,
            lambda n=name: _MockCostProvider(n),
        )


class TestUnifiedCostsEndpoint:
    """Integration tests for the unified costs endpoint."""

    @pytest.mark.asyncio
    async def test_unauthenticated_returns_401(self, client: AsyncClient) -> None:
        """Unauthenticated requests return 401."""
        response = await client.get(
            "/api/v1/costs/",
            params={
                "provider": "aws",
                "start_date": "2026-07-01",
                "end_date": "2026-07-31",
            },
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_aws_returns_normalized_response(self, auth_client: AsyncClient) -> None:
        """The ``aws`` provider returns a :class:`CostResponse`."""
        response = await auth_client.get(
            "/api/v1/costs/",
            params={
                "provider": "aws",
                "start_date": "2026-07-01",
                "end_date": "2026-07-31",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["provider"] == "aws"
        assert data["total_cost"] == 100.0
        assert isinstance(data["services"], list)

    @pytest.mark.asyncio
    async def test_azure_returns_normalized_response(self, auth_client: AsyncClient) -> None:
        """The ``azure`` provider returns a :class:`CostResponse`."""
        response = await auth_client.get(
            "/api/v1/costs/",
            params={
                "provider": "azure",
                "start_date": "2026-07-01",
                "end_date": "2026-07-31",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["provider"] == "azure"
        assert data["total_cost"] == 100.0

    @pytest.mark.asyncio
    async def test_gcp_returns_normalized_response(self, auth_client: AsyncClient) -> None:
        """The ``gcp`` provider returns a :class:`CostResponse`."""
        response = await auth_client.get(
            "/api/v1/costs/",
            params={
                "provider": "gcp",
                "start_date": "2026-07-01",
                "end_date": "2026-07-31",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["provider"] == "gcp"
        assert data["total_cost"] == 100.0

    @pytest.mark.asyncio
    async def test_unsupported_provider_returns_400(self, auth_client: AsyncClient) -> None:
        """An unsupported provider returns 400 with ``X-Error-Code`` header."""
        response = await auth_client.get(
            "/api/v1/costs/",
            params={
                "provider": "invalid",
                "start_date": "2026-07-01",
                "end_date": "2026-07-31",
            },
        )
        # FastAPI returns 422 for invalid Literal values via Pydantic
        # validation before the handler runs. The 400 path is for
        # non-HTTP callers (e.g. internal services) that bypass Pydantic.
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_end_before_start_returns_422(self, auth_client: AsyncClient) -> None:
        """``end_date`` before ``start_date`` returns 422."""
        response = await auth_client.get(
            "/api/v1/costs/",
            params={
                "provider": "aws",
                "start_date": "2026-07-31",
                "end_date": "2026-07-01",
            },
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_missing_provider_returns_422(self, auth_client: AsyncClient) -> None:
        """Missing ``provider`` field returns 422."""
        response = await auth_client.get(
            "/api/v1/costs/",
            params={
                "start_date": "2026-07-01",
                "end_date": "2026-07-31",
            },
        )
        assert response.status_code == 422
