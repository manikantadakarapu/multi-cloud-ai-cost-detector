"""Tests for the :class:`CloudProvider` abstract base class."""

from __future__ import annotations

from datetime import date
from inspect import isabstract

import pytest

from app.providers import CloudProvider
from app.providers.schemas import CostResponse, ServiceCost
from tests.test_providers_registry import FakeCloudProvider


class TestCloudProviderABC:
    def test_cannot_instantiate_directly(self) -> None:
        """The ABC must not be directly instantiable."""
        with pytest.raises(TypeError):
            CloudProvider()  # type: ignore[abstract]

    def test_is_marked_abstract(self) -> None:
        """The ABC still has unimplemented abstract methods."""
        assert isabstract(CloudProvider)

    def test_abstract_methods_exist(self) -> None:
        """All four expected abstract methods are declared."""
        abstract_names = frozenset(CloudProvider.__abstractmethods__)
        assert abstract_names == frozenset(
            {
                "provider_name",
                "authenticate",
                "validate_credentials",
                "get_costs",
            }
        )

    def test_partial_subclass_cannot_be_instantiated(self) -> None:
        """A subclass that does not implement every abstract method is also abstract."""

        class PartialProvider(CloudProvider):
            def provider_name(self) -> str:
                return "partial"

        with pytest.raises(TypeError):
            PartialProvider()  # type: ignore[abstract]

    def test_complete_subclass_is_instantiable(self) -> None:
        """A subclass that implements every abstract method can be instantiated."""
        provider = FakeCloudProvider()
        assert provider.provider_name() == "fake"
        assert provider.validate_credentials() is True
        assert provider.authenticate() is None

    @pytest.mark.asyncio
    async def test_complete_subclass_get_costs_returns_cost_response(self) -> None:
        """A complete subclass's ``get_costs`` returns a :class:`CostResponse`."""
        provider = FakeCloudProvider()
        response = await provider.get_costs(
            date(2024, 1, 1), date(2024, 1, 31), "DAILY"
        )
        assert isinstance(response, CostResponse)
        assert response.provider == "fake"
        assert response.total_cost == 100.0
        assert response.services == [
            ServiceCost(service_name="FakeService", cost=100.0)
        ]
