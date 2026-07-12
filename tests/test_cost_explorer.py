from datetime import date
from unittest.mock import patch

import pytest

from app.core.config import Settings
from app.services.aws.cost_explorer import CostExplorerService
from app.services.aws.exceptions import (
    AWSCredentialsError,
    AWSInvalidDateRangeError,
    AWSPermissionsError,
    AWSThrottlingError,
)


@pytest.fixture
def mock_settings():
    return Settings(
        JWT_SECRET_KEY="test-secret",
        AWS_DEFAULT_REGION="us-east-1",
        AWS_COST_EXPLORER_ENABLED=True,
    )


@pytest.fixture
def service(mock_settings):
    return CostExplorerService(mock_settings)


class TestCostExplorerService:
    @pytest.mark.asyncio
    async def test_get_costs_success(self, service):
        """Successful cost retrieval returns normalized data."""
        mock_response = {
            "ResultsByTime": [
                {
                    "TimePeriod": {"Start": "2024-01-01", "End": "2024-01-02"},
                    "Groups": [
                        {
                            "Keys": ["AmazonEC2"],
                            "Metrics": {
                                "UnblendedCost": {"Amount": "100.50", "Unit": "USD"}
                            },
                        },
                        {
                            "Keys": ["AmazonS3"],
                            "Metrics": {
                                "UnblendedCost": {"Amount": "50.25", "Unit": "USD"}
                            },
                        },
                    ],
                    "Total": {"UnblendedCost": {"Amount": "150.75", "Unit": "USD"}},
                }
            ]
        }
        with patch.object(service, "_client") as mock_client:
            mock_client.get_cost_and_usage.return_value = mock_response
            result = await service.get_costs(
                start_date=date(2024, 1, 1),
                end_date=date(2024, 1, 2),
                granularity="DAILY",
            )
            assert result["provider"] == "aws"
            assert result["currency"] == "USD"
            assert result["total_cost"] == 150.75
            assert len(result["services"]) == 2
            assert result["services"][0]["service_name"] == "AmazonEC2"
            assert result["services"][0]["cost"] == 100.50

    @pytest.mark.asyncio
    async def test_get_costs_credentials_error(self, service):
        """Missing credentials raises AWSCredentialsError."""
        from botocore.exceptions import NoCredentialsError

        with patch.object(service, "_client") as mock_client:
            mock_client.get_cost_and_usage.side_effect = NoCredentialsError()
            with pytest.raises(AWSCredentialsError):
                await service.get_costs(
                    start_date=date(2024, 1, 1),
                    end_date=date(2024, 1, 2),
                    granularity="DAILY",
                )

    @pytest.mark.asyncio
    async def test_get_costs_throttling_error(self, service):
        """Throttling raises AWSThrottlingError."""
        from botocore.exceptions import ClientError

        error = ClientError(
            {"Error": {"Code": "ThrottlingException", "Message": "Rate exceeded"}},
            "GetCostAndUsage",
        )
        with patch.object(service, "_client") as mock_client:
            mock_client.get_cost_and_usage.side_effect = error
            with pytest.raises(AWSThrottlingError):
                await service.get_costs(
                    start_date=date(2024, 1, 1),
                    end_date=date(2024, 1, 2),
                    granularity="DAILY",
                )

    @pytest.mark.asyncio
    async def test_get_costs_permissions_error(self, service):
        """Missing permissions raises AWSPermissionsError."""
        from botocore.exceptions import ClientError

        error = ClientError(
            {"Error": {"Code": "AccessDeniedException", "Message": "Access denied"}},
            "GetCostAndUsage",
        )
        with patch.object(service, "_client") as mock_client:
            mock_client.get_cost_and_usage.side_effect = error
            with pytest.raises(AWSPermissionsError):
                await service.get_costs(
                    start_date=date(2024, 1, 1),
                    end_date=date(2024, 1, 2),
                    granularity="DAILY",
                )

    @pytest.mark.asyncio
    async def test_get_costs_invalid_date_range(self, service):
        """Invalid date range raises AWSInvalidDateRangeError."""
        with pytest.raises(AWSInvalidDateRangeError):
            await service.get_costs(
                start_date=date(2024, 1, 2),
                end_date=date(2024, 1, 1),
                granularity="DAILY",
            )

    @pytest.mark.asyncio
    async def test_get_costs_disabled(self, mock_settings):
        """Cost Explorer disabled returns empty result."""
        mock_settings.aws_cost_explorer_enabled = False
        service = CostExplorerService(mock_settings)
        result = await service.get_costs(
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 2),
            granularity="DAILY",
        )
        assert result["services"] == []
        assert result["total_cost"] == 0.0

    @pytest.mark.asyncio
    async def test_get_costs_pagination(self, service):
        """NextPageToken triggers additional requests and aggregates results."""
        page1 = {
            "ResultsByTime": [
                {
                    "TimePeriod": {"Start": "2024-01-01", "End": "2024-01-02"},
                    "Groups": [
                        {
                            "Keys": ["AmazonEC2"],
                            "Metrics": {
                                "UnblendedCost": {"Amount": "100.00", "Unit": "USD"}
                            },
                        },
                    ],
                }
            ],
            "NextPageToken": "token-2",
        }
        page2 = {
            "ResultsByTime": [
                {
                    "TimePeriod": {"Start": "2024-01-02", "End": "2024-01-03"},
                    "Groups": [
                        {
                            "Keys": ["AmazonS3"],
                            "Metrics": {
                                "UnblendedCost": {"Amount": "50.00", "Unit": "USD"}
                            },
                        },
                    ],
                }
            ],
        }
        with patch.object(service, "_client") as mock_client:
            mock_client.get_cost_and_usage.side_effect = [page1, page2]
            result = await service.get_costs(
                start_date=date(2024, 1, 1),
                end_date=date(2024, 1, 2),
                granularity="DAILY",
            )
            assert result["total_cost"] == 150.00
            assert len(result["services"]) == 2
            assert mock_client.get_cost_and_usage.call_count == 2
            second_call_kwargs = mock_client.get_cost_and_usage.call_args_list[1].kwargs
            assert second_call_kwargs["NextPageToken"] == "token-2"

    @pytest.mark.asyncio
    async def test_get_costs_empty_response(self, service):
        """Empty AWS response returns zero total and empty services."""
        with patch.object(service, "_client") as mock_client:
            mock_client.get_cost_and_usage.return_value = {"ResultsByTime": []}
            result = await service.get_costs(
                start_date=date(2024, 1, 1),
                end_date=date(2024, 1, 2),
                granularity="DAILY",
            )
            assert result["provider"] == "aws"
            assert result["total_cost"] == 0.0
            assert result["services"] == []
            assert result["date_range"]["granularity"] == "DAILY"

    @pytest.mark.asyncio
    async def test_get_costs_unknown_service_key(self, service):
        """Group with missing Keys falls back to Unknown service name."""
        mock_response = {
            "ResultsByTime": [
                {
                    "TimePeriod": {"Start": "2024-01-01", "End": "2024-01-02"},
                    "Groups": [
                        {
                            "Keys": [],
                            "Metrics": {
                                "UnblendedCost": {"Amount": "10.00", "Unit": "USD"}
                            },
                        },
                    ],
                }
            ]
        }
        with patch.object(service, "_client") as mock_client:
            mock_client.get_cost_and_usage.return_value = mock_response
            result = await service.get_costs(
                start_date=date(2024, 1, 1),
                end_date=date(2024, 1, 2),
                granularity="DAILY",
            )
            assert len(result["services"]) == 1
            assert result["services"][0]["service_name"] == "Unknown"
            assert result["services"][0]["cost"] == 10.00

    @pytest.mark.asyncio
    async def test_get_costs_ignores_zero_cost_services(self, service):
        """Services with zero cost are not included in normalized output."""
        mock_response = {
            "ResultsByTime": [
                {
                    "TimePeriod": {"Start": "2024-01-01", "End": "2024-01-02"},
                    "Groups": [
                        {
                            "Keys": ["AmazonEC2"],
                            "Metrics": {
                                "UnblendedCost": {"Amount": "0.00", "Unit": "USD"}
                            },
                        },
                        {
                            "Keys": ["AmazonS3"],
                            "Metrics": {
                                "UnblendedCost": {"Amount": "25.00", "Unit": "USD"}
                            },
                        },
                    ],
                }
            ]
        }
        with patch.object(service, "_client") as mock_client:
            mock_client.get_cost_and_usage.return_value = mock_response
            result = await service.get_costs(
                start_date=date(2024, 1, 1),
                end_date=date(2024, 1, 2),
                granularity="DAILY",
            )
            assert len(result["services"]) == 1
            assert result["services"][0]["service_name"] == "AmazonS3"
            assert result["total_cost"] == 25.00
