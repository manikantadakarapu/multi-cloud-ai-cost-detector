"""Tests for the AWS :class:`CloudProvider` implementation and mapper."""

from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from botocore.exceptions import ClientError, NoCredentialsError

from app.providers import (
    PROVIDER_REGISTRY,
    CostResponse,
    ServiceCost,
)
from app.providers.aws import AWSCloudProvider, AWSMapper
from app.providers.exceptions import (
    ProviderCredentialsError,
    ProviderInvalidDateRangeError,
    ProviderPermissionsError,
    ProviderServiceError,
    ProviderThrottlingError,
)
from app.services.aws.exceptions import (
    AWSCredentialsError,
    AWSInvalidDateRangeError,
    AWSPermissionsError,
    AWSServiceError,
    AWSThrottlingError,
)


class TestAWSProviderRegistration:
    def test_aws_provider_registered_in_registry(self) -> None:
        """``app.providers.aws`` registers a factory for ``"aws"``."""
        from app.providers.aws import AWSCloudProvider as Cls

        factory = PROVIDER_REGISTRY.get("aws")
        assert factory is not None
        assert callable(factory)
        provider = factory()
        assert isinstance(provider, Cls)
        assert isinstance(provider, AWSCloudProvider)


class TestAWSProviderMetadata:
    def test_provider_name(self) -> None:
        """``provider_name`` returns ``"aws"``."""
        with patch("app.providers.aws.provider.CostExplorerService") as mock_service_cls:
            mock_service_cls.return_value = MagicMock()
            provider = AWSCloudProvider()
        assert provider.provider_name() == "aws"


class TestAWSProviderAuthenticate:
    def test_authenticate_calls_ensure_client(self) -> None:
        """``authenticate`` delegates to the service's client bootstrap."""
        with patch("app.providers.aws.provider.CostExplorerService") as mock_service_cls:
            mock_service = MagicMock()
            mock_service_cls.return_value = mock_service
            provider = AWSCloudProvider()
            result = provider.authenticate()
        assert result is None
        mock_service._ensure_client.assert_called_once_with()

    def test_authenticate_propagates_credential_errors(self) -> None:
        """``authenticate`` does not swallow credential errors."""
        with patch("app.providers.aws.provider.CostExplorerService") as mock_service_cls:
            mock_service = MagicMock()
            mock_service._ensure_client.side_effect = AWSCredentialsError("missing")
            mock_service_cls.return_value = mock_service
            provider = AWSCloudProvider()
            with pytest.raises(AWSCredentialsError):
                provider.authenticate()


class TestAWSProviderValidateCredentials:
    def test_validate_credentials_true_when_authenticate_succeeds(self) -> None:
        """Successful ``authenticate`` yields ``True``."""
        with patch("app.providers.aws.provider.CostExplorerService") as mock_service_cls:
            mock_service = MagicMock()
            mock_service._ensure_client.return_value = None
            mock_service_cls.return_value = mock_service
            provider = AWSCloudProvider()
        assert provider.validate_credentials() is True

    def test_validate_credentials_false_on_aws_credentials_error(self) -> None:
        """``AWSCredentialsError`` is swallowed and yields ``False``."""
        with patch("app.providers.aws.provider.CostExplorerService") as mock_service_cls:
            mock_service = MagicMock()
            mock_service._ensure_client.side_effect = AWSCredentialsError("missing")
            mock_service_cls.return_value = mock_service
            provider = AWSCloudProvider()
        assert provider.validate_credentials() is False

    def test_validate_credentials_false_on_no_credentials_error(self) -> None:
        """``NoCredentialsError`` is swallowed and yields ``False``."""
        with patch("app.providers.aws.provider.CostExplorerService") as mock_service_cls:
            mock_service = MagicMock()
            mock_service._ensure_client.side_effect = NoCredentialsError()
            mock_service_cls.return_value = mock_service
            provider = AWSCloudProvider()
        assert provider.validate_credentials() is False

    def test_validate_credentials_propagates_other_errors(self) -> None:
        """Non-credential exceptions propagate unchanged."""
        with patch("app.providers.aws.provider.CostExplorerService") as mock_service_cls:
            mock_service = MagicMock()
            mock_service._ensure_client.side_effect = RuntimeError("boom")
            mock_service_cls.return_value = mock_service
            provider = AWSCloudProvider()
        with pytest.raises(RuntimeError):
            provider.validate_credentials()


class TestAWSProviderGetCosts:
    @pytest.mark.asyncio
    async def test_get_costs_happy_path(self) -> None:
        """Successful service call returns a populated ``CostResponse``."""
        raw = {
            "provider": "aws",
            "currency": "USD",
            "total_cost": 150.75,
            "date_range": {
                "start": "2024-01-01",
                "end": "2024-01-31",
                "granularity": "DAILY",
            },
            "services": [
                {"service_name": "AmazonEC2", "cost": 100.50},
                {"service_name": "AmazonS3", "cost": 50.25},
            ],
        }
        with patch("app.providers.aws.provider.CostExplorerService") as mock_service_cls:
            mock_service = MagicMock()
            mock_service.get_costs = AsyncMock(return_value=raw)
            mock_service_cls.return_value = mock_service
            provider = AWSCloudProvider()
            response = await provider.get_costs(
                start_date=date(2024, 1, 1),
                end_date=date(2024, 1, 31),
                granularity="DAILY",
            )

        assert isinstance(response, CostResponse)
        assert response.provider == "aws"
        assert response.currency == "USD"
        assert response.total_cost == 150.75
        assert response.services == [
            ServiceCost(service_name="AmazonEC2", cost=100.50),
            ServiceCost(service_name="AmazonS3", cost=50.25),
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
            "provider": "aws",
            "currency": "USD",
            "total_cost": 0.0,
            "date_range": {
                "start": "2024-01-01",
                "end": "2024-01-02",
                "granularity": "DAILY",
            },
            "services": [],
        }
        with patch("app.providers.aws.provider.CostExplorerService") as mock_service_cls:
            mock_service = MagicMock()
            mock_service.get_costs = AsyncMock(return_value=raw)
            mock_service_cls.return_value = mock_service
            provider = AWSCloudProvider()
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
    async def test_get_costs_translates_aws_credentials_error(self) -> None:
        """``AWSCredentialsError`` becomes ``ProviderCredentialsError``."""
        with patch("app.providers.aws.provider.CostExplorerService") as mock_service_cls:
            mock_service = MagicMock()
            mock_service.get_costs = AsyncMock(side_effect=AWSCredentialsError("missing"))
            mock_service_cls.return_value = mock_service
            provider = AWSCloudProvider()
            with pytest.raises(ProviderCredentialsError):
                await provider.get_costs(date(2024, 1, 1), date(2024, 1, 2), "DAILY")

    @pytest.mark.asyncio
    async def test_get_costs_translates_no_credentials_error(self) -> None:
        """``NoCredentialsError`` becomes ``ProviderCredentialsError``."""
        with patch("app.providers.aws.provider.CostExplorerService") as mock_service_cls:
            mock_service = MagicMock()
            mock_service.get_costs = AsyncMock(side_effect=NoCredentialsError())
            mock_service_cls.return_value = mock_service
            provider = AWSCloudProvider()
            with pytest.raises(ProviderCredentialsError):
                await provider.get_costs(date(2024, 1, 1), date(2024, 1, 2), "DAILY")

    @pytest.mark.asyncio
    async def test_get_costs_translates_throttling_error(self) -> None:
        """``AWSThrottlingError`` becomes ``ProviderThrottlingError``."""
        with patch("app.providers.aws.provider.CostExplorerService") as mock_service_cls:
            mock_service = MagicMock()
            mock_service.get_costs = AsyncMock(side_effect=AWSThrottlingError("slow down"))
            mock_service_cls.return_value = mock_service
            provider = AWSCloudProvider()
            with pytest.raises(ProviderThrottlingError):
                await provider.get_costs(date(2024, 1, 1), date(2024, 1, 2), "DAILY")

    @pytest.mark.asyncio
    async def test_get_costs_translates_permissions_error(self) -> None:
        """``AWSPermissionsError`` becomes ``ProviderPermissionsError``."""
        with patch("app.providers.aws.provider.CostExplorerService") as mock_service_cls:
            mock_service = MagicMock()
            mock_service.get_costs = AsyncMock(side_effect=AWSPermissionsError("denied"))
            mock_service_cls.return_value = mock_service
            provider = AWSCloudProvider()
            with pytest.raises(ProviderPermissionsError):
                await provider.get_costs(date(2024, 1, 1), date(2024, 1, 2), "DAILY")

    @pytest.mark.asyncio
    async def test_get_costs_translates_invalid_date_range(self) -> None:
        """``AWSInvalidDateRangeError`` becomes ``ProviderInvalidDateRangeError``."""
        with patch("app.providers.aws.provider.CostExplorerService") as mock_service_cls:
            mock_service = MagicMock()
            mock_service.get_costs = AsyncMock(side_effect=AWSInvalidDateRangeError("bad range"))
            mock_service_cls.return_value = mock_service
            provider = AWSCloudProvider()
            with pytest.raises(ProviderInvalidDateRangeError):
                await provider.get_costs(date(2024, 1, 1), date(2024, 1, 2), "DAILY")

    @pytest.mark.asyncio
    async def test_get_costs_translates_service_error(self) -> None:
        """``AWSServiceError`` becomes ``ProviderServiceError``."""
        with patch("app.providers.aws.provider.CostExplorerService") as mock_service_cls:
            mock_service = MagicMock()
            mock_service.get_costs = AsyncMock(side_effect=AWSServiceError("boom"))
            mock_service_cls.return_value = mock_service
            provider = AWSCloudProvider()
            with pytest.raises(ProviderServiceError):
                await provider.get_costs(date(2024, 1, 1), date(2024, 1, 2), "DAILY")

    @pytest.mark.asyncio
    async def test_get_costs_translates_unexpected_client_error(self) -> None:
        """Generic ``ClientError`` becomes ``ProviderServiceError``."""
        client_error = ClientError(
            {"Error": {"Code": "InternalError", "Message": "oh no"}},
            "GetCostAndUsage",
        )
        with patch("app.providers.aws.provider.CostExplorerService") as mock_service_cls:
            mock_service = MagicMock()
            mock_service.get_costs = AsyncMock(side_effect=client_error)
            mock_service_cls.return_value = mock_service
            provider = AWSCloudProvider()
            with pytest.raises(ProviderServiceError):
                await provider.get_costs(date(2024, 1, 1), date(2024, 1, 2), "DAILY")


class TestAWSMapper:
    def test_map_minimal_raw_dict(self) -> None:
        """Mapper builds a ``CostResponse`` from a complete raw dict."""
        raw = {
            "provider": "aws",
            "currency": "USD",
            "total_cost": 12.34,
            "date_range": {
                "start": "2024-02-01",
                "end": "2024-02-29",
                "granularity": "MONTHLY",
            },
            "services": [{"service_name": "AmazonEC2", "cost": 12.34}],
        }
        response = AWSMapper().map(
            raw,
            start_date=date(2024, 2, 1),
            end_date=date(2024, 2, 29),
            granularity="MONTHLY",
        )
        assert isinstance(response, CostResponse)
        assert response.provider == "aws"
        assert response.currency == "USD"
        assert response.total_cost == 12.34
        assert response.services == [ServiceCost(service_name="AmazonEC2", cost=12.34)]
        assert response.date_range["granularity"] == "MONTHLY"

    def test_map_fills_missing_date_range(self) -> None:
        """Mapper falls back to caller-provided dates when ``date_range`` is missing."""
        raw = {
            "provider": "aws",
            "currency": "USD",
            "total_cost": 0.0,
            "services": [],
        }
        response = AWSMapper().map(
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
            "provider": "aws",
            "currency": "USD",
            "total_cost": 0.0,
            "date_range": {
                "start": "2024-04-01",
                "end": "2024-04-30",
                "granularity": "DAILY",
            },
        }
        response = AWSMapper().map(
            raw,
            start_date=date(2024, 4, 1),
            end_date=date(2024, 4, 30),
            granularity="DAILY",
        )
        assert response.services == []
