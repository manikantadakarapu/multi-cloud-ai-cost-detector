"""Tests for the cloud-provider registry and :func:`get_provider` dependency."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date

import pytest
from fastapi import Depends, FastAPI

from app.providers import (
    PROVIDER_REGISTRY,
    CloudProvider,
    CostResponse,
    ProviderError,
    ServiceCost,
    get_provider,
    get_provider_factory,
    register_provider,
)


class FakeCloudProvider(CloudProvider):
    """Minimal concrete :class:`CloudProvider` used only by these tests."""

    def provider_name(self) -> str:
        return "fake"

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
            provider="fake",
            total_cost=100.0,
            date_range={
                "start": start_date.isoformat(),
                "end": end_date.isoformat(),
                "granularity": granularity,
            },
            services=[ServiceCost(service_name="FakeService", cost=100.0)],
        )


@pytest.fixture
def registered_fake(monkeypatch: pytest.MonkeyPatch) -> str:
    """Register a fake provider under a unique name and clean up afterwards."""
    name = "fake-provider"
    monkeypatch.setitem(PROVIDER_REGISTRY, name, FakeCloudProvider)
    yield name
    PROVIDER_REGISTRY.pop(name, None)


class TestProviderRegistry:
    def test_registry_is_a_dict(self) -> None:
        """The registry is exposed as a plain dict."""
        assert isinstance(PROVIDER_REGISTRY, dict)

    def test_register_provider_stores_factory(self, registered_fake: str) -> None:
        """``register_provider`` stores the factory under the given name."""
        assert PROVIDER_REGISTRY[registered_fake] is FakeCloudProvider

    def test_register_provider_overwrites_existing_entry(
        self, registered_fake: str
    ) -> None:
        """Re-registering the same name replaces the previous factory."""

        class OtherFake(CloudProvider):
            def provider_name(self) -> str:
                return "other"

            def authenticate(self) -> None:
                return None

            def validate_credentials(self) -> bool:
                return False

            def get_costs(  # pragma: no cover - unused in this test
                self,
                start_date: date,
                end_date: date,
                granularity: str,
            ) -> CostResponse:
                raise NotImplementedError

        register_provider(registered_fake, OtherFake)
        assert PROVIDER_REGISTRY[registered_fake] is OtherFake

    def test_get_provider_factory_returns_registered_factory(
        self, registered_fake: str
    ) -> None:
        """``get_provider_factory`` returns the registered factory."""
        factory = get_provider_factory(registered_fake)
        assert factory is FakeCloudProvider

    def test_get_provider_factory_raises_for_missing_name(self) -> None:
        """An unregistered name raises :class:`ProviderError`."""
        with pytest.raises(ProviderError) as exc_info:
            get_provider_factory("does-not-exist")
        assert exc_info.value.error_code == "PROVIDER_NOT_REGISTERED"
        assert "does-not-exist" in exc_info.value.message

    def test_get_provider_factory_callable_builds_instance(
        self, registered_fake: str
    ) -> None:
        """The factory returned by ``get_provider_factory`` builds a new instance."""
        factory = get_provider_factory(registered_fake)
        provider = factory()
        assert isinstance(provider, FakeCloudProvider)
        assert provider.provider_name() == "fake"


class TestGetProviderDependency:
    def test_get_provider_returns_zero_arg_callable(self, registered_fake: str) -> None:
        """``get_provider`` returns a callable taking no arguments."""
        dependency = get_provider(registered_fake)
        assert isinstance(dependency, Callable)
        provider = dependency()
        assert isinstance(provider, FakeCloudProvider)

    def test_get_provider_raises_for_missing_name(self) -> None:
        """``get_provider`` propagates the :class:`ProviderError` for missing names."""
        with pytest.raises(ProviderError):
            get_provider("missing")

    def test_get_provider_works_as_fastapi_dependency(
        self, registered_fake: str
    ) -> None:
        """The returned factory works end-to-end as a FastAPI ``Depends`` dependency."""
        factory = get_provider(registered_fake)
        app = FastAPI()

        @app.get("/provider-name")
        def read_provider_name(
            provider: CloudProvider = Depends(factory),  # noqa: B008
        ) -> str:
            return provider.provider_name()

        from fastapi.testclient import TestClient

        client = TestClient(app)
        response = client.get("/provider-name")
        assert response.status_code == 200
        assert response.json() == "fake"
