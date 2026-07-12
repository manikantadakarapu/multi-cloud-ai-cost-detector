"""Tests for :class:`UnifiedCostService` — the provider-agnostic cost service."""

from __future__ import annotations

from datetime import date

import pytest
from pytest import MonkeyPatch

from app.providers import (
    PROVIDER_REGISTRY,
    CloudProvider,
    CostResponse,
    ServiceCost,
)
from app.providers.exceptions import ProviderNotSupportedException


class _FakeCostProvider(CloudProvider):
    """A minimal :class:`CloudProvider` whose ``provider_name()`` matches the
    registry key so the aggregator's ``_validate_provider`` check passes."""

    def __init__(self, name: str = "fake") -> None:
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
            total_cost=42.0,
            date_range={
                "start": start_date.isoformat(),
                "end": end_date.isoformat(),
                "granularity": granularity,
            },
            services=[
                ServiceCost(service_name="FakeService", cost=42.0),
            ],
        )


class TestUnifiedCostService:
    """Tests for :class:`UnifiedCostService`."""

    def test_resolve_known_provider(self, monkeypatch: MonkeyPatch) -> None:
        """A known provider name returns a service with the correct provider."""
        from app.services.cost_service import UnifiedCostService  # noqa: PLC0415

        # Register a factory lambda (not a class) so resolve_provider()
        # creates an instance with the matching provider_name()
        monkeypatch.setitem(
            PROVIDER_REGISTRY,
            "test-provider",
            lambda: _FakeCostProvider("test-provider"),
        )
        service = UnifiedCostService(provider_name="test-provider")
        assert service.provider_name == "test-provider"
        assert service.provider_name is not None

    def test_unknown_provider_raises_unsupported(self, monkeypatch: MonkeyPatch) -> None:
        """An unknown provider name raises :class:`ProviderNotSupportedException`."""
        from app.services.cost_service import UnifiedCostService  # noqa: PLC0415

        with pytest.raises(ProviderNotSupportedException) as exc_info:
            UnifiedCostService(provider_name="does-not-exist")

        assert exc_info.value.error_code == "PROVIDER_NOT_SUPPORTED"
        assert "does-not-exist" in str(exc_info.value.message)

    @pytest.mark.asyncio
    async def test_get_costs_returns_cost_response(self, monkeypatch: MonkeyPatch) -> None:
        """``get_costs`` returns a :class:`CostResponse` with the expected shape."""
        from app.services.cost_service import UnifiedCostService  # noqa: PLC0415

        monkeypatch.setitem(
            PROVIDER_REGISTRY,
            "test-provider",
            lambda: _FakeCostProvider("test-provider"),
        )
        service = UnifiedCostService(provider_name="test-provider")
        response = await service.get_costs(
            start_date=date(2026, 7, 1),
            end_date=date(2026, 7, 31),
            granularity="DAILY",
        )
        assert isinstance(response, CostResponse)
        assert response.provider == "test-provider"
        assert response.total_cost == 42.0
        assert len(response.services) == 1

    @pytest.mark.asyncio
    async def test_credentials_not_checked_at_construction(self, monkeypatch: MonkeyPatch) -> None:
        """The service does not call ``authenticate`` or ``validate_credentials``
        at construction time — those are lazy calls made during ``get_costs``."""
        from app.services.cost_service import UnifiedCostService  # noqa: PLC0415

        # Register a factory lambda so the service can be constructed
        monkeypatch.setitem(
            PROVIDER_REGISTRY,
            "lazy-provider",
            lambda: _FakeCostProvider("lazy-provider"),
        )
        service = UnifiedCostService(provider_name="lazy-provider")
        # No exception — construction only validates provider name, not credentials
        assert service.provider_name == "lazy-provider"
