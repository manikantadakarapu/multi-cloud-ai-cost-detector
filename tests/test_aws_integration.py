"""Integration tests for the AWS Cost Explorer endpoint.

These tests exercise the full HTTP flow (auth + validation + service call
+ response shaping) using the real FastAPI app via httpx, with the
``CostExplorerService.get_costs`` boundary mocked so no AWS credentials are
required.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

from app.core.config import settings


class TestAWSIntegration:
    """Full-flow integration tests for /api/v1/aws/costs."""

    @pytest.mark.asyncio
    async def test_full_flow_daily(self, auth_client: AsyncClient) -> None:
        """Daily granularity full flow returns normalized costs."""
        mock_response = {
            "provider": "aws",
            "currency": "USD",
            "total_cost": 1234.56,
            "date_range": {
                "start": "2024-01-01",
                "end": "2024-01-02",
                "granularity": "DAILY",
            },
            "services": [{"service_name": "AmazonEC2", "cost": 1234.56}],
        }
        with patch(
            "app.api.routes.aws.CostExplorerService.get_costs",
            new_callable=AsyncMock,
        ) as mock_get:
            mock_get.return_value = mock_response
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
            mock_get.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_full_flow_monthly(self, auth_client: AsyncClient) -> None:
        """Monthly granularity full flow returns normalized costs."""
        mock_response = {
            "provider": "aws",
            "currency": "USD",
            "total_cost": 5000.00,
            "date_range": {
                "start": "2024-01-01",
                "end": "2024-01-31",
                "granularity": "MONTHLY",
            },
            "services": [{"service_name": "AmazonRDS", "cost": 5000.00}],
        }
        with patch(
            "app.api.routes.aws.CostExplorerService.get_costs",
            new_callable=AsyncMock,
        ) as mock_get:
            mock_get.return_value = mock_response
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
            mock_get.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_empty_response(self, auth_client: AsyncClient) -> None:
        """Empty cost data returns empty services list and zero total."""
        mock_response = {
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
        with patch(
            "app.api.routes.aws.CostExplorerService.get_costs",
            new_callable=AsyncMock,
        ) as mock_get:
            mock_get.return_value = mock_response
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
        original = settings.aws_cost_explorer_enabled
        settings.aws_cost_explorer_enabled = False
        try:
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
