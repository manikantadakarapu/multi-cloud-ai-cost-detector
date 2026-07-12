"""High-level tests for the Azure cloud provider abstraction.

These tests exercise :class:`AzureCloudProvider` as an implementation of
:class:`CloudProvider`: the public ``provider_name``, ``authenticate``,
``validate_credentials``, and ``get_costs`` methods and the translation of
Azure-specific errors into the provider-agnostic hierarchy. They are
intentionally focused on the abstraction boundary and avoid duplicating the
exhaustive exception matrix in :mod:`tests.test_providers_azure`.
"""

from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from azure.core.exceptions import ClientAuthenticationError

from app.providers.azure import AzureCloudProvider, AzureMapper
from app.providers.base import CloudProvider
from app.providers.exceptions import (
    ProviderCredentialsError,
    ProviderError,
    ProviderPermissionsError,
    ProviderServiceError,
)
from app.providers.registry import get_provider, list_providers
from app.providers.schemas import CostResponse, ServiceCost
from app.services.azure.exceptions import (
    AzureCredentialsError,
    AzurePermissionsError,
    AzureServiceError,
)


class TestAzureMapper:
    """Unit tests for :class:`AzureMapper` matching the AWS mapper shape."""

    def test_map_converts_complete_raw_dict(self) -> None:
        """A complete raw dict becomes a correctly populated ``CostResponse``."""
        raw = {
            "provider": "azure",
            "currency": "EUR",
            "total_cost": 300.00,
            "date_range": {
                "start": "2024-06-01",
                "end": "2024-06-30",
                "granularity": "MONTHLY",
            },
            "services": [
                {"service_name": "Compute", "cost": 200.00},
                {"service_name": "Storage", "cost": 100.00},
            ],
        }

        response = AzureMapper().map(
            raw,
            start_date=date(2024, 6, 1),
            end_date=date(2024, 6, 30),
            granularity="MONTHLY",
        )

        assert response == CostResponse(
            provider="azure",
            currency="EUR",
            total_cost=300.00,
            date_range={
                "start": "2024-06-01",
                "end": "2024-06-30",
                "granularity": "MONTHLY",
            },
            services=[
                ServiceCost(service_name="Compute", cost=200.00),
                ServiceCost(service_name="Storage", cost=100.00),
            ],
        )

    def test_map_preserves_descending_service_order(self) -> None:
        """Services are returned in the descending cost order supplied by the service."""
        raw = {
            "provider": "azure",
            "currency": "USD",
            "total_cost": 60.00,
            "date_range": {
                "start": "2024-07-01",
                "end": "2024-07-31",
                "granularity": "DAILY",
            },
            "services": [
                {"service_name": "Compute", "cost": 50.00},
                {"service_name": "Storage", "cost": 9.00},
                {"service_name": "Network", "cost": 1.00},
            ],
        }

        response = AzureMapper().map(
            raw,
            start_date=date(2024, 7, 1),
            end_date=date(2024, 7, 31),
            granularity="DAILY",
        )

        assert [service.cost for service in response.services] == [50.00, 9.00, 1.00]

    def test_map_handles_none_services_as_empty(self) -> None:
        """A ``None`` services key is treated as an empty list."""
        raw = {
            "provider": "azure",
            "currency": "USD",
            "total_cost": 0.0,
            "date_range": {
                "start": "2024-08-01",
                "end": "2024-08-31",
                "granularity": "DAILY",
            },
            "services": None,
        }

        response = AzureMapper().map(
            raw,
            start_date=date(2024, 8, 1),
            end_date=date(2024, 8, 31),
            granularity="DAILY",
        )

        assert response.services == []

    def test_map_falls_back_to_passed_date_range_when_none(self) -> None:
        """A ``None`` date_range is replaced with the caller-provided range."""
        raw = {
            "provider": "azure",
            "currency": "USD",
            "total_cost": 10.00,
            "date_range": None,
            "services": [{"service_name": "Storage", "cost": 10.00}],
        }

        response = AzureMapper().map(
            raw,
            start_date=date(2024, 9, 1),
            end_date=date(2024, 9, 30),
            granularity="MONTHLY",
        )

        assert response.date_range == {
            "start": "2024-09-01",
            "end": "2024-09-30",
            "granularity": "MONTHLY",
        }

    def test_map_uses_default_values_for_missing_keys(self) -> None:
        """Missing top-level keys fall back to safe defaults."""
        response = AzureMapper().map(
            {},
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 31),
            granularity="DAILY",
        )

        assert response.provider == "azure"
        assert response.currency == "USD"
        assert response.total_cost == 0.0
        assert response.services == []
        assert response.date_range == {
            "start": "2024-01-01",
            "end": "2024-01-31",
            "granularity": "DAILY",
        }


class TestAzureCloudProviderBasics:
    def test_is_cloud_provider(self) -> None:
        """``AzureCloudProvider`` satisfies the abstract base contract."""
        with patch(
            "app.providers.azure.provider.AzureCostManagementService"
        ) as mock_service_cls:
            mock_service_cls.return_value = MagicMock()
            provider = AzureCloudProvider()

        assert isinstance(provider, CloudProvider)

    def test_provider_name_returns_azure(self) -> None:
        """``provider_name`` identifies the implementation as ``azure``."""
        with patch(
            "app.providers.azure.provider.AzureCostManagementService"
        ) as mock_service_cls:
            mock_service_cls.return_value = MagicMock()
            provider = AzureCloudProvider()

        assert provider.provider_name() == "azure"


class TestAzureCloudProviderAuthenticate:
    def test_authenticate_success(self) -> None:
        """Successful authentication returns ``None``."""
        with patch(
            "app.providers.azure.provider.AzureCostManagementService"
        ) as mock_service_cls:
            mock_service = MagicMock()
            mock_service_cls.return_value = mock_service
            provider = AzureCloudProvider()

            result = provider.authenticate()

        assert result is None
        mock_service._ensure_credential.assert_called_once_with()

    def test_authenticate_failure(self) -> None:
        """Credential failures are allowed to propagate."""
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


class TestAzureCloudProviderValidateCredentials:
    def test_validate_credentials_success(self) -> None:
        """Valid credentials yield ``True``."""
        with patch(
            "app.providers.azure.provider.AzureCostManagementService"
        ) as mock_service_cls:
            mock_service = MagicMock()
            mock_service._ensure_credential.return_value = None
            mock_service_cls.return_value = mock_service
            provider = AzureCloudProvider()

        assert provider.validate_credentials() is True

    def test_validate_credentials_failure_azure_credentials(self) -> None:
        """``AzureCredentialsError`` is reported as invalid credentials."""
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

    def test_validate_credentials_failure_client_auth_error(self) -> None:
        """``ClientAuthenticationError`` is also reported as invalid credentials."""
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


class TestAzureCloudProviderGetCosts:
    @pytest.mark.asyncio
    async def test_get_costs_success(self) -> None:
        """A successful call returns a correctly-shaped ``CostResponse``."""
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
    async def test_get_costs_translates_credentials_error(self) -> None:
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
                await provider.get_costs(
                    start_date=date(2024, 1, 1),
                    end_date=date(2024, 1, 2),
                    granularity="DAILY",
                )

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
                await provider.get_costs(
                    start_date=date(2024, 1, 1),
                    end_date=date(2024, 1, 2),
                    granularity="DAILY",
                )

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
                await provider.get_costs(
                    start_date=date(2024, 1, 1),
                    end_date=date(2024, 1, 2),
                    granularity="DAILY",
                )


class TestAzureRegistry:
    """Registry-level integration tests for Azure and AWS factories."""

    def test_list_providers_includes_azure_and_aws(self) -> None:
        """Both ``azure`` and ``aws`` factories are advertised by the registry."""
        providers = list_providers()
        assert "azure" in providers
        assert "aws" in providers

    def test_get_provider_azure_returns_cloud_provider(self) -> None:
        """The ``azure`` factory builds a :class:`CloudProvider` named ``azure``."""
        with patch(
            "app.providers.azure.provider.AzureCostManagementService"
        ) as mock_service_cls:
            mock_service_cls.return_value = MagicMock()
            provider = get_provider("azure")()

        assert isinstance(provider, CloudProvider)
        assert provider.provider_name() == "azure"

    def test_get_provider_aws_returns_cloud_provider(self) -> None:
        """The ``aws`` factory builds a :class:`CloudProvider` named ``aws``."""
        with patch(
            "app.providers.aws.provider.CostExplorerService"
        ) as mock_service_cls:
            mock_service_cls.return_value = MagicMock()
            provider = get_provider("aws")()

        assert isinstance(provider, CloudProvider)
        assert provider.provider_name() == "aws"

    def test_get_provider_unknown_raises_provider_error(self) -> None:
        """An unregistered provider name raises :class:`ProviderError`."""
        with pytest.raises(ProviderError):
            get_provider("unknown")
