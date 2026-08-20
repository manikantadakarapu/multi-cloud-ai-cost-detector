"""Tests for the Azure :class:`CloudProvider` implementation and mapper."""

from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from azure.core.exceptions import AzureError, ClientAuthenticationError

from app.providers import (
    PROVIDER_REGISTRY,
    CostResponse,
    ServiceCost,
)
from app.providers.azure import AzureCloudProvider, AzureMapper
from app.providers.exceptions import (
    ProviderCredentialsError,
    ProviderInvalidDateRangeError,
    ProviderPermissionsError,
    ProviderServiceError,
    ProviderThrottlingError,
)
from app.services.azure.exceptions import (
    AzureCredentialsError,
    AzureInvalidSubscriptionError,
    AzurePermissionsError,
    AzureServiceError,
    AzureThrottlingError,
)


class TestAzureProviderRegistration:
    def test_azure_provider_registered_in_registry(self) -> None:
        """``app.providers.azure`` registers a factory for ``"azure"``."""
        from app.providers.azure import AzureCloudProvider as Cls

        factory = PROVIDER_REGISTRY.get("azure")
        assert factory is not None
        assert callable(factory)
        provider = factory()
        assert isinstance(provider, Cls)
        assert isinstance(provider, AzureCloudProvider)


class TestAzureProviderMetadata:
    def test_provider_name(self) -> None:
        """``provider_name`` returns ``"azure"``."""
        with patch(
            "app.providers.azure.provider.AzureCostManagementService"
        ) as mock_service_cls:
            mock_service_cls.return_value = MagicMock()
            provider = AzureCloudProvider()
        assert provider.provider_name() == "azure"

    def test_provider_implements_cloud_provider_interface(self) -> None:
        """``AzureCloudProvider`` is a concrete subclass of :class:`CloudProvider`."""
        from app.providers.base import CloudProvider

        with patch(
            "app.providers.azure.provider.AzureCostManagementService"
        ) as mock_service_cls:
            mock_service_cls.return_value = MagicMock()
            provider = AzureCloudProvider()
        assert isinstance(provider, CloudProvider)


class TestAzureProviderAuthenticate:
    def test_authenticate_calls_ensure_credential(self) -> None:
        """``authenticate`` delegates to the service's credential bootstrap."""
        with patch(
            "app.providers.azure.provider.AzureCostManagementService"
        ) as mock_service_cls:
            mock_service = MagicMock()
            mock_service_cls.return_value = mock_service
            provider = AzureCloudProvider()
            result = provider.authenticate()
        assert result is None
        mock_service._ensure_credential.assert_called_once_with()

    def test_authenticate_propagates_credential_errors(self) -> None:
        """``authenticate`` does not swallow credential errors."""
        with patch(
            "app.providers.azure.provider.AzureCostManagementService"
        ) as mock_service_cls:
            mock_service = MagicMock()
            mock_service._ensure_credential.side_effect = AzureCredentialsError(
                "missing"
            )
            mock_service_cls.return_value = mock_service
            provider = AzureCloudProvider()
            with pytest.raises(AzureCredentialsError):
                provider.authenticate()


class TestAzureProviderValidateCredentials:
    def test_validate_credentials_true_when_authenticate_succeeds(self) -> None:
        """Successful ``authenticate`` yields ``True``."""
        with patch(
            "app.providers.azure.provider.AzureCostManagementService"
        ) as mock_service_cls:
            mock_service = MagicMock()
            mock_service._ensure_credential.return_value = None
            mock_service_cls.return_value = mock_service
            provider = AzureCloudProvider()
        assert provider.validate_credentials() is True

    def test_validate_credentials_false_on_azure_credentials_error(self) -> None:
        """``AzureCredentialsError`` is swallowed and yields ``False``."""
        with patch(
            "app.providers.azure.provider.AzureCostManagementService"
        ) as mock_service_cls:
            mock_service = MagicMock()
            mock_service._ensure_credential.side_effect = AzureCredentialsError(
                "missing"
            )
            mock_service_cls.return_value = mock_service
            provider = AzureCloudProvider()
        assert provider.validate_credentials() is False

    def test_validate_credentials_false_on_client_authentication_error(self) -> None:
        """``ClientAuthenticationError`` is swallowed and yields ``False``."""
        with patch(
            "app.providers.azure.provider.AzureCostManagementService"
        ) as mock_service_cls:
            mock_service = MagicMock()
            mock_service._ensure_credential.side_effect = ClientAuthenticationError(
                "bad token"
            )
            mock_service_cls.return_value = mock_service
            provider = AzureCloudProvider()
        assert provider.validate_credentials() is False

    def test_validate_credentials_propagates_other_errors(self) -> None:
        """Non-credential exceptions propagate unchanged."""
        with patch(
            "app.providers.azure.provider.AzureCostManagementService"
        ) as mock_service_cls:
            mock_service = MagicMock()
            mock_service._ensure_credential.side_effect = RuntimeError("boom")
            mock_service_cls.return_value = mock_service
            provider = AzureCloudProvider()
        with pytest.raises(RuntimeError):
            provider.validate_credentials()


class TestAzureProviderGetCosts:
    @pytest.mark.asyncio
    async def test_get_costs_happy_path(self) -> None:
        """Successful service call returns a populated ``CostResponse``."""
        raw = {
            "provider": "azure",
            "currency": "USD",
            "total_cost": 175.75,
            "date_range": {
                "start": "2024-01-01",
                "end": "2024-01-31",
                "granularity": "DAILY",
            },
            "services": [
                {"service_name": "Storage", "cost": 125.75},
                {"service_name": "Compute", "cost": 50.00},
            ],
        }
        with patch(
            "app.providers.azure.provider.AzureCostManagementService"
        ) as mock_service_cls:
            mock_service = MagicMock()
            mock_service.get_costs = AsyncMock(return_value=raw)
            mock_service_cls.return_value = mock_service
            provider = AzureCloudProvider()
            response = await provider.get_costs(
                start_date=date(2024, 1, 1),
                end_date=date(2024, 1, 31),
                granularity="DAILY",
            )

        assert isinstance(response, CostResponse)
        assert response.provider == "azure"
        assert response.currency == "USD"
        assert response.total_cost == 175.75
        assert response.services == [
            ServiceCost(service_name="Storage", cost=125.75),
            ServiceCost(service_name="Compute", cost=50.00),
        ]
        assert response.date_range == {
            "start": "2024-01-01",
            "end": "2024-01-31",
            "granularity": "DAILY",
        }

    @pytest.mark.asyncio
    async def test_get_costs_disabled_returns_empty_response(self) -> None:
        """When the service returns the disabled-flag structure we still
        produce a valid ``CostResponse``."""
        raw = {
            "provider": "azure",
            "currency": "USD",
            "total_cost": 0.0,
            "date_range": {
                "start": "2024-01-01",
                "end": "2024-01-02",
                "granularity": "DAILY",
            },
            "services": [],
        }
        with patch(
            "app.providers.azure.provider.AzureCostManagementService"
        ) as mock_service_cls:
            mock_service = MagicMock()
            mock_service.get_costs = AsyncMock(return_value=raw)
            mock_service_cls.return_value = mock_service
            provider = AzureCloudProvider()
            response = await provider.get_costs(
                start_date=date(2024, 1, 1),
                end_date=date(2024, 1, 2),
                granularity="DAILY",
            )

        assert isinstance(response, CostResponse)
        assert response.total_cost == 0.0
        assert response.services == []
        assert response.date_range["start"] == "2024-01-01"
        assert response.date_range["end"] == "2024-01-02"
        assert response.date_range["granularity"] == "DAILY"

    @pytest.mark.asyncio
    async def test_get_costs_translates_azure_credentials_error(self) -> None:
        """``AzureCredentialsError`` becomes ``ProviderCredentialsError``."""
        with patch(
            "app.providers.azure.provider.AzureCostManagementService"
        ) as mock_service_cls:
            mock_service = MagicMock()
            mock_service.get_costs = AsyncMock(
                side_effect=AzureCredentialsError("missing")
            )
            mock_service_cls.return_value = mock_service
            provider = AzureCloudProvider()
            with pytest.raises(ProviderCredentialsError):
                await provider.get_costs(date(2024, 1, 1), date(2024, 1, 2), "DAILY")

    @pytest.mark.asyncio
    async def test_get_costs_translates_throttling_error(self) -> None:
        """``AzureThrottlingError`` becomes ``ProviderThrottlingError``."""
        with patch(
            "app.providers.azure.provider.AzureCostManagementService"
        ) as mock_service_cls:
            mock_service = MagicMock()
            mock_service.get_costs = AsyncMock(
                side_effect=AzureThrottlingError("slow down")
            )
            mock_service_cls.return_value = mock_service
            provider = AzureCloudProvider()
            with pytest.raises(ProviderThrottlingError):
                await provider.get_costs(date(2024, 1, 1), date(2024, 1, 2), "DAILY")

    @pytest.mark.asyncio
    async def test_get_costs_translates_permissions_error(self) -> None:
        """``AzurePermissionsError`` becomes ``ProviderPermissionsError``."""
        with patch(
            "app.providers.azure.provider.AzureCostManagementService"
        ) as mock_service_cls:
            mock_service = MagicMock()
            mock_service.get_costs = AsyncMock(
                side_effect=AzurePermissionsError("denied")
            )
            mock_service_cls.return_value = mock_service
            provider = AzureCloudProvider()
            with pytest.raises(ProviderPermissionsError):
                await provider.get_costs(date(2024, 1, 1), date(2024, 1, 2), "DAILY")

    @pytest.mark.asyncio
    async def test_get_costs_translates_invalid_subscription_error(self) -> None:
        """``AzureInvalidSubscriptionError`` becomes ``ProviderInvalidDateRangeError``."""
        with patch(
            "app.providers.azure.provider.AzureCostManagementService"
        ) as mock_service_cls:
            mock_service = MagicMock()
            mock_service.get_costs = AsyncMock(
                side_effect=AzureInvalidSubscriptionError("no subscription")
            )
            mock_service_cls.return_value = mock_service
            provider = AzureCloudProvider()
            with pytest.raises(ProviderInvalidDateRangeError):
                await provider.get_costs(date(2024, 1, 1), date(2024, 1, 2), "DAILY")

    @pytest.mark.asyncio
    async def test_get_costs_translates_service_error(self) -> None:
        """``AzureServiceError`` becomes ``ProviderServiceError``."""
        with patch(
            "app.providers.azure.provider.AzureCostManagementService"
        ) as mock_service_cls:
            mock_service = MagicMock()
            mock_service.get_costs = AsyncMock(side_effect=AzureServiceError("boom"))
            mock_service_cls.return_value = mock_service
            provider = AzureCloudProvider()
            with pytest.raises(ProviderServiceError):
                await provider.get_costs(date(2024, 1, 1), date(2024, 1, 2), "DAILY")

    @pytest.mark.asyncio
    async def test_get_costs_translates_unexpected_azure_error(self) -> None:
        """Generic ``AzureError`` becomes ``ProviderServiceError``."""
        azure_error = AzureError("unexpected azure failure")
        with patch(
            "app.providers.azure.provider.AzureCostManagementService"
        ) as mock_service_cls:
            mock_service = MagicMock()
            mock_service.get_costs = AsyncMock(side_effect=azure_error)
            mock_service_cls.return_value = mock_service
            provider = AzureCloudProvider()
            with pytest.raises(ProviderServiceError):
                await provider.get_costs(date(2024, 1, 1), date(2024, 1, 2), "DAILY")


class TestAzureMapper:
    def test_map_minimal_raw_dict(self) -> None:
        """Mapper builds a ``CostResponse`` from a complete raw dict."""
        raw = {
            "provider": "azure",
            "currency": "USD",
            "total_cost": 12.34,
            "date_range": {
                "start": "2024-02-01",
                "end": "2024-02-29",
                "granularity": "MONTHLY",
            },
            "services": [{"service_name": "Storage", "cost": 12.34}],
        }
        response = AzureMapper().map(
            raw,
            start_date=date(2024, 2, 1),
            end_date=date(2024, 2, 29),
            granularity="MONTHLY",
        )
        assert isinstance(response, CostResponse)
        assert response.provider == "azure"
        assert response.currency == "USD"
        assert response.total_cost == 12.34
        assert response.services == [ServiceCost(service_name="Storage", cost=12.34)]
        assert response.date_range["granularity"] == "MONTHLY"

    def test_map_fills_missing_date_range(self) -> None:
        """Mapper falls back to caller-provided dates when ``date_range`` is missing."""
        raw = {
            "provider": "azure",
            "currency": "USD",
            "total_cost": 0.0,
            "services": [],
        }
        response = AzureMapper().map(
            raw,
            start_date=date(2024, 3, 1),
            end_date=date(2024, 3, 31),
            granularity="DAILY",
        )
        assert response.date_range == {
            "start": "2024-03-01",
            "end": "2024-03-31",
            "granularity": "DAILY",
        }

    def test_map_handles_missing_services(self) -> None:
        """Mapper tolerates a missing ``services`` key."""
        raw = {
            "provider": "azure",
            "currency": "USD",
            "total_cost": 0.0,
            "date_range": {
                "start": "2024-04-01",
                "end": "2024-04-30",
                "granularity": "DAILY",
            },
        }
        response = AzureMapper().map(
            raw,
            start_date=date(2024, 4, 1),
            end_date=date(2024, 4, 30),
            granularity="DAILY",
        )
        assert response.services == []

    def test_map_defensive_defaults_for_empty_raw(self) -> None:
        """Mapper falls back to safe defaults when ``raw`` is empty."""
        response = AzureMapper().map(
            {},
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 31),
            granularity="MONTHLY",
        )
        assert response.provider == "azure"
        assert response.currency == "USD"
        assert response.total_cost == 0.0
        assert response.services == []
        assert response.date_range["granularity"] == "MONTHLY"
