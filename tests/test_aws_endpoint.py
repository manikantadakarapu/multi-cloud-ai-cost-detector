"""Tests for AWS Cost Explorer API endpoint."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient


class TestAWSEndpoint:
    """Test suite for the /api/v1/aws/costs endpoint."""

    @pytest.mark.asyncio
    async def test_get_costs_success(self, auth_client: AsyncClient) -> None:
        """Successful authenticated request returns normalized costs."""
        mock_response = {
            "provider": "aws",
            "currency": "USD",
            "total_cost": 150.75,
            "date_range": {
                "start": "2024-01-01",
                "end": "2024-01-02",
                "granularity": "DAILY",
            },
            "services": [
                {"service_name": "AmazonEC2", "cost": 100.50},
                {"service_name": "AmazonS3", "cost": 50.25},
            ],
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
        """AWS credentials error returns 500."""
        from app.services.aws.exceptions import AWSCredentialsError

        with patch(
            "app.api.routes.aws.CostExplorerService.get_costs",
            new_callable=AsyncMock,
        ) as mock_get:
            mock_get.side_effect = AWSCredentialsError("No credentials")
            response = await auth_client.get(
                "/api/v1/aws/costs",
                params={
                    "start_date": "2024-01-01",
                    "end_date": "2024-01-02",
                },
            )
            assert response.status_code == 500

    @pytest.mark.asyncio
    async def test_get_costs_aws_throttling(
        self, auth_client: AsyncClient
    ) -> None:
        """AWS throttling returns 429."""
        from app.services.aws.exceptions import AWSThrottlingError

        with patch(
            "app.api.routes.aws.CostExplorerService.get_costs",
            new_callable=AsyncMock,
        ) as mock_get:
            mock_get.side_effect = AWSThrottlingError("Rate limited")
            response = await auth_client.get(
                "/api/v1/aws/costs",
                params={
                    "start_date": "2024-01-01",
                    "end_date": "2024-01-02",
                },
            )
            assert response.status_code == 429

    @pytest.mark.asyncio
    async def test_get_costs_aws_permissions(
        self, auth_client: AsyncClient
    ) -> None:
        """AWS permissions error returns 403."""
        from app.services.aws.exceptions import AWSPermissionsError

        with patch(
            "app.api.routes.aws.CostExplorerService.get_costs",
            new_callable=AsyncMock,
        ) as mock_get:
            mock_get.side_effect = AWSPermissionsError("Access denied")
            response = await auth_client.get(
                "/api/v1/aws/costs",
                params={
                    "start_date": "2024-01-01",
                    "end_date": "2024-01-02",
                },
            )
            assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_get_costs_aws_service_error(
        self, auth_client: AsyncClient
    ) -> None:
        """AWS service error returns 502."""
        from app.services.aws.exceptions import AWSServiceError

        with patch(
            "app.api.routes.aws.CostExplorerService.get_costs",
            new_callable=AsyncMock,
        ) as mock_get:
            mock_get.side_effect = AWSServiceError("Service error")
            response = await auth_client.get(
                "/api/v1/aws/costs",
                params={
                    "start_date": "2024-01-01",
                    "end_date": "2024-01-02",
                },
            )
            assert response.status_code == 502