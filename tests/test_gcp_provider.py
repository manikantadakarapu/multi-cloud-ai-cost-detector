"""Tests for the GCP :class:`CloudProvider` implementation and mapper."""

from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from google.api_core.exceptions import Forbidden, GoogleAPIError
from google.auth.exceptions import DefaultCredentialsError, RefreshError

from app.providers import PROVIDER_REGISTRY, CostResponse, ServiceCost
from app.providers.exceptions import (
    ProviderCredentialsError,
    ProviderInvalidDateRangeError,
    ProviderServiceError,
    ProviderThrottlingError,
)
from app.providers.gcp import GCPCloudProvider, GCPMapper
from app.services.gcp.exceptions import (
    GCPBigQueryError,
    GCPBillingAccountNotFoundError,
    GCPCredentialsError,
    GCPQuotaExceededError,
)


class TestGCPProviderRegistration:
    def test_gcp_provider_registered_in_registry(self) -> None:
        """``app.providers.gcp`` registers a factory for ``"gcp"``."""
        from app.providers.gcp import GCPCloudProvider as Cls

        factory = PROVIDER_REGISTRY.get("gcp")
        assert factory is not None
        assert callable(factory)
        provider = factory()
        assert isinstance(provider, Cls)
        assert isinstance(provider, GCPCloudProvider)


class TestGCPProviderMetadata:
    def test_provider_name(self) -> None:
        """``provider_name`` returns ``\"gcp\"``."""
        with patch("app.providers.gcp.provider.GCPBillingService") as mock_service_cls:
            mock_service_cls.return_value = MagicMock()
            provider = GCPCloudProvider()
        assert provider.provider_name() == "gcp"


class TestGCPProviderAuthenticate:
    def test_authenticate_calls_ensure_client(self) -> None:
        """``authenticate`` delegates to the service's client bootstrap."""
        with patch("app.providers.gcp.provider.GCPBillingService") as mock_service_cls:
            mock_service = MagicMock()
            mock_service_cls.return_value = mock_service
            provider = GCPCloudProvider()
            result = provider.authenticate()
        assert result is None
        mock_service._ensure_client.assert_called_once_with()

    def test_authenticate_propagates_credential_errors(self) -> None:
        """``authenticate`` does not swallow credential errors."""
        with patch("app.providers.gcp.provider.GCPBillingService") as mock_service_cls:
            mock_service = MagicMock()
            mock_service._ensure_client.side_effect = GCPCredentialsError("missing")
            mock_service_cls.return_value = mock_service
            provider = GCPCloudProvider()
            with pytest.raises(GCPCredentialsError):
                provider.authenticate()


class TestGCPProviderValidateCredentials:
    def test_validate_credentials_true_when_authenticate_succeeds(self) -> None:
        """Successful ``authenticate`` yields ``True``."""
        with patch("app.providers.gcp.provider.GCPBillingService") as mock_service_cls:
            mock_service = MagicMock()
            mock_service._ensure_client.return_value = None
            mock_service_cls.return_value = mock_service
            provider = GCPCloudProvider()
        assert provider.validate_credentials() is True

    @pytest.mark.parametrize(
        "side_effect",
        [
            GCPCredentialsError("missing"),
            DefaultCredentialsError("no creds"),
            RefreshError("refresh failed"),
        ],
    )
    def test_validate_credentials_false_on_credential_errors(
        self, side_effect: Exception
    ) -> None:
        """Credential-related exceptions are swallowed and yield ``False``."""
        with patch("app.providers.gcp.provider.GCPBillingService") as mock_service_cls:
            mock_service = MagicMock()
            mock_service._ensure_client.side_effect = side_effect
            mock_service_cls.return_value = mock_service
            provider = GCPCloudProvider()
        assert provider.validate_credentials() is False

    def test_validate_credentials_propagates_other_errors(self) -> None:
        """Non-credential exceptions propagate unchanged."""
        with patch("app.providers.gcp.provider.GCPBillingService") as mock_service_cls:
            mock_service = MagicMock()
            mock_service._ensure_client.side_effect = GCPBigQueryError("boom")
            mock_service_cls.return_value = mock_service
            provider = GCPCloudProvider()
        with pytest.raises(GCPBigQueryError):
            provider.validate_credentials()


class TestGCPProviderGetCosts:
    @pytest.mark.asyncio
    async def test_returns_cost_response_from_raw(self) -> None:
        """Happy path: service output is mapped to ``CostResponse``."""
        raw = {
            "provider": "gcp",
            "currency": "USD",
            "total_cost": 200.0,
            "services": [
                {"service_name": "Compute Engine", "cost": 150.0},
                {"service_name": "Cloud Storage", "cost": 50.0},
            ],
            "date_range": {
                "start": "2024-01-01",
                "end": "2024-01-31",
                "granularity": "DAILY",
            },
        }
        with patch("app.providers.gcp.provider.GCPBillingService") as mock_service_cls:
            mock_service = MagicMock()
            mock_service.get_costs = AsyncMock(return_value=raw)
            mock_service_cls.return_value = mock_service
            provider = GCPCloudProvider()

            response = await provider.get_costs(
                start_date=date(2024, 1, 1),
                end_date=date(2024, 1, 31),
                granularity="DAILY",
            )

        assert isinstance(response, CostResponse)
        assert response.provider == "gcp"
        assert response.currency == "USD"
        assert response.total_cost == 200.0
        assert response.date_range == {
            "start": "2024-01-01",
            "end": "2024-01-31",
            "granularity": "DAILY",
        }
        assert response.services == [
            ServiceCost(service_name="Compute Engine", cost=150.0),
            ServiceCost(service_name="Cloud Storage", cost=50.0),
        ]
        mock_service.get_costs.assert_awaited_once_with(
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 31),
            granularity="DAILY",
        )

    @pytest.mark.asyncio
    async def test_credentials_error_translates(self) -> None:
        with patch("app.providers.gcp.provider.GCPBillingService") as mock_service_cls:
            mock_service = MagicMock()
            mock_service.get_costs = AsyncMock(
                side_effect=GCPCredentialsError("missing")
            )
            mock_service_cls.return_value = mock_service
            provider = GCPCloudProvider()

            with pytest.raises(ProviderCredentialsError):
                await provider.get_costs(date(2024, 1, 1), date(2024, 1, 31), "DAILY")

    @pytest.mark.asyncio
    async def test_quota_exceeded_translates_to_throttling(self) -> None:
        with patch("app.providers.gcp.provider.GCPBillingService") as mock_service_cls:
            mock_service = MagicMock()
            mock_service.get_costs = AsyncMock(
                side_effect=GCPQuotaExceededError("rate limited")
            )
            mock_service_cls.return_value = mock_service
            provider = GCPCloudProvider()

            with pytest.raises(ProviderThrottlingError):
                await provider.get_costs(date(2024, 1, 1), date(2024, 1, 31), "DAILY")

    @pytest.mark.asyncio
    async def test_billing_account_not_found_translates_to_invalid_date_range(
        self,
    ) -> None:
        with patch("app.providers.gcp.provider.GCPBillingService") as mock_service_cls:
            mock_service = MagicMock()
            mock_service.get_costs = AsyncMock(
                side_effect=GCPBillingAccountNotFoundError("no table")
            )
            mock_service_cls.return_value = mock_service
            provider = GCPCloudProvider()

            with pytest.raises(ProviderInvalidDateRangeError):
                await provider.get_costs(date(2024, 1, 1), date(2024, 1, 31), "DAILY")

    @pytest.mark.asyncio
    async def test_bigquery_error_translates_to_service_error(self) -> None:
        with patch("app.providers.gcp.provider.GCPBillingService") as mock_service_cls:
            mock_service = MagicMock()
            mock_service.get_costs = AsyncMock(
                side_effect=GCPBigQueryError("boom")
            )
            mock_service_cls.return_value = mock_service
            provider = GCPCloudProvider()

            with pytest.raises(ProviderServiceError):
                await provider.get_costs(date(2024, 1, 1), date(2024, 1, 31), "DAILY")

    @pytest.mark.asyncio
    async def test_default_credentials_error_translates(self) -> None:
        with patch("app.providers.gcp.provider.GCPBillingService") as mock_service_cls:
            mock_service = MagicMock()
            mock_service.get_costs = AsyncMock(
                side_effect=DefaultCredentialsError("no creds")
            )
            mock_service_cls.return_value = mock_service
            provider = GCPCloudProvider()

            with pytest.raises(ProviderCredentialsError):
                await provider.get_costs(date(2024, 1, 1), date(2024, 1, 31), "DAILY")

    @pytest.mark.asyncio
    async def test_refresh_error_translates(self) -> None:
        with patch("app.providers.gcp.provider.GCPBillingService") as mock_service_cls:
            mock_service = MagicMock()
            mock_service.get_costs = AsyncMock(
                side_effect=RefreshError("refresh failed")
            )
            mock_service_cls.return_value = mock_service
            provider = GCPCloudProvider()

            with pytest.raises(ProviderCredentialsError):
                await provider.get_costs(date(2024, 1, 1), date(2024, 1, 31), "DAILY")

    @pytest.mark.asyncio
    async def test_forbidden_translates_to_credentials_error(self) -> None:
        with patch("app.providers.gcp.provider.GCPBillingService") as mock_service_cls:
            mock_service = MagicMock()
            mock_service.get_costs = AsyncMock(side_effect=Forbidden("denied"))
            mock_service_cls.return_value = mock_service
            provider = GCPCloudProvider()

            with pytest.raises(ProviderCredentialsError):
                await provider.get_costs(date(2024, 1, 1), date(2024, 1, 31), "DAILY")

    @pytest.mark.asyncio
    async def test_generic_google_api_error_translates(self) -> None:
        with patch("app.providers.gcp.provider.GCPBillingService") as mock_service_cls:
            mock_service = MagicMock()
            mock_service.get_costs = AsyncMock(
                side_effect=GoogleAPIError("service down")
            )
            mock_service_cls.return_value = mock_service
            provider = GCPCloudProvider()

            with pytest.raises(ProviderServiceError):
                await provider.get_costs(date(2024, 1, 1), date(2024, 1, 31), "DAILY")


class TestGCPMapper:
    def test_maps_full_raw_response(self) -> None:
        raw = {
            "provider": "gcp",
            "currency": "EUR",
            "total_cost": 100.5,
            "services": [
                {"service_name": "BigQuery", "cost": 60.0},
                {"service_name": "Storage", "cost": 40.5},
            ],
            "date_range": {
                "start": "2024-01-01",
                "end": "2024-01-31",
                "granularity": "MONTHLY",
            },
        }
        response = GCPMapper().map(
            raw,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 31),
            granularity="MONTHLY",
        )
        assert response.provider == "gcp"
        assert response.currency == "EUR"
        assert response.total_cost == 100.5
        assert response.services == [
            ServiceCost(service_name="BigQuery", cost=60.0),
            ServiceCost(service_name="Storage", cost=40.5),
        ]
        assert response.date_range == {
            "start": "2024-01-01",
            "end": "2024-01-31",
            "granularity": "MONTHLY",
        }

    def test_fills_missing_date_range_from_arguments(self) -> None:
        raw = {
            "provider": "gcp",
            "currency": "USD",
            "total_cost": 0.0,
            "services": [],
        }
        response = GCPMapper().map(
            raw,
            start_date=date(2024, 2, 1),
            end_date=date(2024, 2, 28),
            granularity="DAILY",
        )
        assert response.date_range == {
            "start": "2024-02-01",
            "end": "2024-02-28",
            "granularity": "DAILY",
        }

    def test_handles_missing_services_key(self) -> None:
        raw = {"provider": "gcp", "total_cost": 0.0}
        response = GCPMapper().map(
            raw,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 31),
            granularity="DAILY",
        )
        assert response.services == []
