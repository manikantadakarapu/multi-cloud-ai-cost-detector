"""Tests for AWS Cost Explorer API endpoint.

The route now delegates to the cloud-provider abstraction. We patch
``app.providers.aws.AWSCloudProvider`` (the class the registered
factory instantiates) to drive the route without touching AWS.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.api.routes.aws import aws_cost_aggregator_dependency, aws_provider_dependency
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
from app.services.cost_aggregator import CostAggregatorService


def _build_mock_provider() -> MagicMock:
    """Build a mock ``CloudProvider`` whose ``get_costs`` returns a ``CostResponse``."""
    mock_provider = MagicMock()
    mock_provider.provider_name.return_value = "aws"
    return mock_provider


def _override_provider(mock_provider: MagicMock) -> None:
    """Override the AWS provider and aggregation dependencies for the route."""

    async def _provider() -> MagicMock:
        return mock_provider

    async def _aggregator() -> CostAggregatorService:
        return CostAggregatorService("aws", mock_provider, cache=None)

    app.dependency_overrides[aws_provider_dependency] = _provider
    app.dependency_overrides[aws_cost_aggregator_dependency] = _aggregator


@pytest_asyncio.fixture
async def auth_client() -> AsyncClient:
    """Authenticated client with a benign AWS provider override."""

    async def _current_user() -> User:
        return User(
            id=uuid4(),
            email="aws-route-test@example.com",
            full_name="AWS Route Test",
            password_hash="unused",
            is_active=True,
        )

    app.dependency_overrides[get_current_active_user] = _current_user
    default_provider = _build_mock_provider()
    default_provider.get_costs = AsyncMock(
        return_value=CostResponse(
            provider="aws",
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


class TestAWSEndpoint:
    """Test suite for the /api/v1/aws/costs endpoint."""

    @pytest.mark.asyncio
    async def test_get_costs_success(self, auth_client: AsyncClient) -> None:
        """Successful authenticated request returns normalized costs."""
        cost_response = CostResponse(
            provider="aws",
            currency="USD",
            total_cost=150.75,
            date_range={
                "start": "2024-01-01",
                "end": "2024-01-02",
                "granularity": "DAILY",
            },
            services=[
                ServiceCost(service_name="AmazonEC2", cost=100.50),
                ServiceCost(service_name="AmazonS3", cost=50.25),
            ],
        )
        mock_provider = _build_mock_provider()
        mock_provider.get_costs = AsyncMock(return_value=cost_response)
        _override_provider(mock_provider)

        response = await auth_client.get(
            "/api/v1/aws/costs",
            params={
                "start_date": "2024-01-01",
                "end_date": "2024-01-02",
                "granularity": "DAILY",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["provider"] == "aws"
        assert data["total_cost"] == 150.75
        assert len(data["services"]) == 2
        assert data["services"][0]["service_name"] == "AmazonEC2"
        assert data["services"][0]["cost"] == 100.50
        assert data["date_range"]["granularity"] == "DAILY"

    @pytest.mark.asyncio
    async def test_get_costs_unauthorized(self, client: AsyncClient) -> None:
        """Missing auth returns 401."""
        response = await client.get(
            "/api/v1/aws/costs",
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
            "/api/v1/aws/costs",
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
            "/api/v1/aws/costs",
            params={
                "start_date": "2024-01-31",
                "end_date": "2024-01-01",
            },
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_get_costs_aws_credentials_error(
        self, auth_client: AsyncClient
    ) -> None:
        """Provider credentials error returns 500."""
        mock_provider = _build_mock_provider()
        mock_provider.get_costs = AsyncMock(
            side_effect=ProviderCredentialsError("No credentials")
        )
        _override_provider(mock_provider)

        response = await auth_client.get(
            "/api/v1/aws/costs",
            params={
                "start_date": "2024-01-01",
                "end_date": "2024-01-02",
            },
        )
        assert response.status_code == 500

    @pytest.mark.asyncio
    async def test_get_costs_aws_throttling(self, auth_client: AsyncClient) -> None:
        """Provider throttling error returns 429."""
        mock_provider = _build_mock_provider()
        mock_provider.get_costs = AsyncMock(
            side_effect=ProviderThrottlingError("Rate limited")
        )
        _override_provider(mock_provider)

        response = await auth_client.get(
            "/api/v1/aws/costs",
            params={
                "start_date": "2024-01-01",
                "end_date": "2024-01-02",
            },
        )
        assert response.status_code == 429

    @pytest.mark.asyncio
    async def test_get_costs_aws_permissions(self, auth_client: AsyncClient) -> None:
        """Provider permissions error returns 403."""
        mock_provider = _build_mock_provider()
        mock_provider.get_costs = AsyncMock(
            side_effect=ProviderPermissionsError("Access denied")
        )
        _override_provider(mock_provider)

        response = await auth_client.get(
            "/api/v1/aws/costs",
            params={
                "start_date": "2024-01-01",
                "end_date": "2024-01-02",
            },
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_get_costs_invalid_date_range(self, auth_client: AsyncClient) -> None:
        """Provider invalid date range error returns 400."""
        mock_provider = _build_mock_provider()
        mock_provider.get_costs = AsyncMock(
            side_effect=ProviderInvalidDateRangeError("Bad range")
        )
        _override_provider(mock_provider)

        response = await auth_client.get(
            "/api/v1/aws/costs",
            params={
                "start_date": "2024-01-01",
                "end_date": "2024-01-02",
            },
        )
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_get_costs_aws_service_error(self, auth_client: AsyncClient) -> None:
        """Provider service error returns 502."""
        mock_provider = _build_mock_provider()
        mock_provider.get_costs = AsyncMock(
            side_effect=ProviderServiceError("Service error")
        )
        _override_provider(mock_provider)

        response = await auth_client.get(
            "/api/v1/aws/costs",
            params={
                "start_date": "2024-01-01",
                "end_date": "2024-01-02",
            },
        )
        assert response.status_code == 502
