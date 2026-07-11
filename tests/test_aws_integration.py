"""Integration tests for the AWS Cost Explorer endpoint.

These tests exercise the full HTTP flow (auth + validation + provider
call + response shaping) using the real FastAPI app via httpx, with
the cloud-provider layer mocked so no AWS credentials are required.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import AsyncClient

from app.api.routes.aws import aws_provider_dependency
from app.core.config import settings
from app.main import app
from app.providers import CostResponse, ServiceCost


def _build_mock_provider(get_costs: AsyncMock) -> MagicMock:
    mock_provider = MagicMock()
    mock_provider.provider_name.return_value = "aws"
    mock_provider.get_costs = get_costs
    return mock_provider


def _override_provider(mock_provider: MagicMock) -> None:
    async def _provider() -> MagicMock:
        return mock_provider

    app.dependency_overrides[aws_provider_dependency] = _provider


class TestAWSIntegration:
    """Full-flow integration tests for /api/v1/aws/costs."""

    @pytest.mark.asyncio
    async def test_full_flow_daily(self, auth_client: AsyncClient) -> None:
        """Daily granularity full flow returns normalized costs."""
        cost_response = CostResponse(
            provider="aws",
            currency="USD",
            total_cost=1234.56,
            date_range={
                "start": "2024-01-01",
                "end": "2024-01-02",
                "granularity": "DAILY",
            },
            services=[ServiceCost(service_name="AmazonEC2", cost=1234.56)],
        )
        mock_provider = _build_mock_provider(AsyncMock(return_value=cost_response))
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
        assert data["currency"] == "USD"
        assert data["total_cost"] == 1234.56
        assert data["date_range"]["granularity"] == "DAILY"
        assert data["date_range"]["start"] == "2024-01-01"
        assert data["date_range"]["end"] == "2024-01-02"
        assert len(data["services"]) == 1
        assert data["services"][0]["service_name"] == "AmazonEC2"
        assert data["services"][0]["cost"] == 1234.56
        mock_provider.get_costs.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_full_flow_monthly(self, auth_client: AsyncClient) -> None:
        """Monthly granularity full flow returns normalized costs."""
        cost_response = CostResponse(
            provider="aws",
            currency="USD",
            total_cost=5000.00,
            date_range={
                "start": "2024-01-01",
                "end": "2024-01-31",
                "granularity": "MONTHLY",
            },
            services=[ServiceCost(service_name="AmazonRDS", cost=5000.00)],
        )
        mock_provider = _build_mock_provider(AsyncMock(return_value=cost_response))
        _override_provider(mock_provider)

        response = await auth_client.get(
            "/api/v1/aws/costs",
            params={
                "start_date": "2024-01-01",
                "end_date": "2024-01-31",
                "granularity": "MONTHLY",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["provider"] == "aws"
        assert data["total_cost"] == 5000.00
        assert data["date_range"]["granularity"] == "MONTHLY"
        assert len(data["services"]) == 1
        assert data["services"][0]["service_name"] == "AmazonRDS"
        mock_provider.get_costs.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_empty_response(self, auth_client: AsyncClient) -> None:
        """Empty cost data returns empty services list and zero total."""
        cost_response = CostResponse(
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
        mock_provider = _build_mock_provider(AsyncMock(return_value=cost_response))
        _override_provider(mock_provider)

        response = await auth_client.get(
            "/api/v1/aws/costs",
            params={
                "start_date": "2024-01-01",
                "end_date": "2024-01-02",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["services"] == []
        assert data["total_cost"] == 0.0
        assert data["provider"] == "aws"
        assert data["currency"] == "USD"

    @pytest.mark.asyncio
    async def test_cost_explorer_disabled(self, auth_client: AsyncClient) -> None:
        """When Cost Explorer is disabled, the endpoint returns an empty 200 result."""
        cost_response = CostResponse(
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
        mock_provider = _build_mock_provider(AsyncMock(return_value=cost_response))

        original = settings.aws_cost_explorer_enabled
        settings.aws_cost_explorer_enabled = False
        try:
            _override_provider(mock_provider)
            response = await auth_client.get(
                "/api/v1/aws/costs",
                params={
                    "start_date": "2024-01-01",
                    "end_date": "2024-01-02",
                },
            )
            assert response.status_code == 200
            data = response.json()
            assert data["services"] == []
            assert data["total_cost"] == 0.0
            assert data["provider"] == "aws"
            assert data["date_range"]["granularity"] == "DAILY"
        finally:
            settings.aws_cost_explorer_enabled = original
