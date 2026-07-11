"""Tests for Azure Cost Management API endpoint.

The route delegates to the cloud-provider abstraction. We patch
``app.providers.azure.AzureCloudProvider`` (the class the registered
factory instantiates) to drive the route without touching Azure.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.api.routes.azure import azure_provider_dependency
from app.auth.dependencies import get_current_active_user
from app.auth.models import User
from app.main import app
from app.providers import CostResponse, ServiceCost
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


@pytest_asyncio.fixture
async def client() -> AsyncIterator[AsyncClient]:
    """HTTPX ASGI client for Azure route tests without DB setup."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def auth_client() -> AsyncIterator[AsyncClient]:
    """Authenticated HTTPX ASGI client for Azure route tests.

    These tests exercise Azure route behavior, not the auth/database stack.
    Overriding ``get_current_active_user`` keeps the tests isolated from the
    SQLite fixture used by auth-specific tests.
    """

    async def _current_user() -> User:
        return User(
            id=uuid4(),
            email="azure-route-test@example.com",
            full_name="Azure Route Test",
            password_hash="unused",
            is_active=True,
        )

    app.dependency_overrides[get_current_active_user] = _current_user
    default_provider = _build_mock_provider()
    default_provider.get_costs = AsyncMock(
        return_value=CostResponse(
            provider="azure",
            currency="USD",
            total_cost=0.0,
            date_range={
                "start": "2024-01-01",
                "end": "2024-01-02",
                "granularity": "DAILY",
            },
            services=[],
        )
    )
    _override_provider(default_provider)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


def _build_mock_provider() -> MagicMock:
    """Build a mock ``CloudProvider`` whose ``get_costs`` returns a ``CostResponse``."""
    mock_provider = MagicMock()
    mock_provider.provider_name.return_value = "azure"
    return mock_provider


def _override_provider(mock_provider: MagicMock) -> None:
    """Override the Azure provider dependency with an async test dependency."""

    async def _provider() -> MagicMock:
        return mock_provider

    app.dependency_overrides[azure_provider_dependency] = _provider


class TestAzureEndpoint:
    """Test suite for the /api/v1/azure/costs endpoint."""

    @pytest.mark.asyncio
    async def test_get_costs_success(self, auth_client: AsyncClient) -> None:
        """Successful authenticated request returns normalized costs."""
        cost_response = CostResponse(
            provider="azure",
            currency="USD",
            total_cost=250.00,
            date_range={
                "start": "2024-01-01",
                "end": "2024-01-02",
                "granularity": "DAILY",
            },
            services=[
                ServiceCost(service_name="Virtual Machines", cost=150.00),
                ServiceCost(service_name="Storage", cost=100.00),
            ],
        )
        mock_provider = _build_mock_provider()
        mock_provider.get_costs = AsyncMock(return_value=cost_response)
        _override_provider(mock_provider)

        response = await auth_client.get(
            "/api/v1/azure/costs",
            params={
                "start_date": "2024-01-01",
                "end_date": "2024-01-02",
                "granularity": "DAILY",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["provider"] == "azure"
        assert data["total_cost"] == 250.00
        assert len(data["services"]) == 2
        assert data["services"][0]["service_name"] == "Virtual Machines"
        assert data["services"][0]["cost"] == 150.00
        assert data["date_range"]["granularity"] == "DAILY"

    @pytest.mark.asyncio
    async def test_get_costs_unauthorized(self, client: AsyncClient) -> None:
        """Missing auth returns 401."""
        response = await client.get(
            "/api/v1/azure/costs",
            params={
                "start_date": "2024-01-01",
                "end_date": "2024-01-02",
            },
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_get_costs_invalid_granularity(
        self, auth_client: AsyncClient
    ) -> None:
        """Invalid granularity returns 422."""
        response = await auth_client.get(
            "/api/v1/azure/costs",
            params={
                "start_date": "2024-01-01",
                "end_date": "2024-01-02",
                "granularity": "HOURLY",
            },
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_get_costs_bad_dates(self, auth_client: AsyncClient) -> None:
        """end_date before start_date returns 422 (Pydantic validation)."""
        response = await auth_client.get(
            "/api/v1/azure/costs",
            params={
                "start_date": "2024-01-31",
                "end_date": "2024-01-01",
            },
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_get_costs_azure_credentials_error(
        self, auth_client: AsyncClient
    ) -> None:
        """Provider credentials error returns 500."""
        mock_provider = _build_mock_provider()
        mock_provider.get_costs = AsyncMock(
            side_effect=ProviderCredentialsError("No credentials")
        )
        _override_provider(mock_provider)

        response = await auth_client.get(
            "/api/v1/azure/costs",
            params={
                "start_date": "2024-01-01",
                "end_date": "2024-01-02",
            },
        )
        assert response.status_code == 500

    @pytest.mark.asyncio
    async def test_get_costs_azure_throttling(self, auth_client: AsyncClient) -> None:
        """Provider throttling error returns 429."""
        mock_provider = _build_mock_provider()
        mock_provider.get_costs = AsyncMock(
            side_effect=ProviderThrottlingError("Rate limited")
        )
        _override_provider(mock_provider)

        response = await auth_client.get(
            "/api/v1/azure/costs",
            params={
                "start_date": "2024-01-01",
                "end_date": "2024-01-02",
            },
        )
        assert response.status_code == 429

    @pytest.mark.asyncio
    async def test_get_costs_azure_permissions(self, auth_client: AsyncClient) -> None:
        """Provider permissions error returns 403."""
        mock_provider = _build_mock_provider()
        mock_provider.get_costs = AsyncMock(
            side_effect=ProviderPermissionsError("Access denied")
        )
        _override_provider(mock_provider)

        response = await auth_client.get(
            "/api/v1/azure/costs",
            params={
                "start_date": "2024-01-01",
                "end_date": "2024-01-02",
            },
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_get_costs_empty_response(self, auth_client: AsyncClient) -> None:
        """A cost response with no services still returns 200."""
        cost_response = CostResponse(
            provider="azure",
            currency="USD",
            total_cost=0.0,
            date_range={
                "start": "2024-01-01",
                "end": "2024-01-02",
                "granularity": "DAILY",
            },
            services=[],
        )
        mock_provider = _build_mock_provider()
        mock_provider.get_costs = AsyncMock(return_value=cost_response)
        _override_provider(mock_provider)

        response = await auth_client.get(
            "/api/v1/azure/costs",
            params={
                "start_date": "2024-01-01",
                "end_date": "2024-01-02",
                "granularity": "DAILY",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total_cost"] == 0.0
        assert data["services"] == []

    @pytest.mark.asyncio
    async def test_get_costs_invalid_subscription(
        self, auth_client: AsyncClient
    ) -> None:
        """Azure invalid subscription error returns 400 with X-Error-Code."""
        mock_provider = _build_mock_provider()
        mock_provider.get_costs = AsyncMock(
            side_effect=AzureInvalidSubscriptionError("Invalid subscription")
        )
        _override_provider(mock_provider)

        response = await auth_client.get(
            "/api/v1/azure/costs",
            params={
                "start_date": "2024-01-01",
                "end_date": "2024-01-02",
            },
        )
        assert response.status_code == 400
        assert response.headers["X-Error-Code"] == "AZURE_INVALID_SUBSCRIPTION"

    @pytest.mark.asyncio
    async def test_get_costs_invalid_date_range(self, auth_client: AsyncClient) -> None:
        """Provider invalid date range error returns 400 with X-Error-Code."""
        mock_provider = _build_mock_provider()
        mock_provider.get_costs = AsyncMock(
            side_effect=ProviderInvalidDateRangeError("Bad range")
        )
        _override_provider(mock_provider)

        response = await auth_client.get(
            "/api/v1/azure/costs",
            params={
                "start_date": "2024-01-01",
                "end_date": "2024-01-02",
            },
        )
        assert response.status_code == 400
        assert response.headers["X-Error-Code"] == "PROVIDER_INVALID_DATE_RANGE"

    @pytest.mark.asyncio
    async def test_get_costs_azure_native_credentials_error(
        self, auth_client: AsyncClient
    ) -> None:
        """Azure credentials error returns 500 with X-Error-Code."""
        mock_provider = _build_mock_provider()
        mock_provider.get_costs = AsyncMock(
            side_effect=AzureCredentialsError("No credentials")
        )
        _override_provider(mock_provider)

        response = await auth_client.get(
            "/api/v1/azure/costs",
            params={
                "start_date": "2024-01-01",
                "end_date": "2024-01-02",
            },
        )
        assert response.status_code == 500
        assert response.headers["X-Error-Code"] == "AZURE_CREDENTIALS_ERROR"

    @pytest.mark.asyncio
    async def test_get_costs_azure_native_throttling(
        self, auth_client: AsyncClient
    ) -> None:
        """Azure throttling error returns 429 with X-Error-Code."""
        mock_provider = _build_mock_provider()
        mock_provider.get_costs = AsyncMock(
            side_effect=AzureThrottlingError("Rate limited")
        )
        _override_provider(mock_provider)

        response = await auth_client.get(
            "/api/v1/azure/costs",
            params={
                "start_date": "2024-01-01",
                "end_date": "2024-01-02",
            },
        )
        assert response.status_code == 429
        assert response.headers["X-Error-Code"] == "AZURE_THROTTLING_ERROR"

    @pytest.mark.asyncio
    async def test_get_costs_azure_native_permissions(
        self, auth_client: AsyncClient
    ) -> None:
        """Azure permissions error returns 403 with X-Error-Code."""
        mock_provider = _build_mock_provider()
        mock_provider.get_costs = AsyncMock(
            side_effect=AzurePermissionsError("Access denied")
        )
        _override_provider(mock_provider)

        response = await auth_client.get(
            "/api/v1/azure/costs",
            params={
                "start_date": "2024-01-01",
                "end_date": "2024-01-02",
            },
        )
        assert response.status_code == 403
        assert response.headers["X-Error-Code"] == "AZURE_PERMISSIONS_ERROR"

    @pytest.mark.asyncio
    async def test_get_costs_azure_service_error(
        self, auth_client: AsyncClient
    ) -> None:
        """Azure service error returns 502 with X-Error-Code."""
        mock_provider = _build_mock_provider()
        mock_provider.get_costs = AsyncMock(
            side_effect=AzureServiceError("Azure service error")
        )
        _override_provider(mock_provider)

        response = await auth_client.get(
            "/api/v1/azure/costs",
            params={
                "start_date": "2024-01-01",
                "end_date": "2024-01-02",
            },
        )
        assert response.status_code == 502
        assert response.headers["X-Error-Code"] == "AZURE_SERVICE_ERROR"

    @pytest.mark.asyncio
    async def test_get_costs_provider_service_error(
        self, auth_client: AsyncClient
    ) -> None:
        """Provider service error returns 502."""
        mock_provider = _build_mock_provider()
        mock_provider.get_costs = AsyncMock(
            side_effect=ProviderServiceError("Service error")
        )
        _override_provider(mock_provider)

        response = await auth_client.get(
            "/api/v1/azure/costs",
            params={
                "start_date": "2024-01-01",
                "end_date": "2024-01-02",
            },
        )
        assert response.status_code == 502
