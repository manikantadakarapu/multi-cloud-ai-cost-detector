"""AWS Cost Explorer SDK tests using mocked boto3 clients."""

from datetime import date
from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError

from app.core.config import Settings
from app.services.aws.cost_explorer import CostExplorerService
from app.services.aws.exceptions import AWSPermissionsError


def _settings(**overrides) -> Settings:
    values = {
        "aws_cost_explorer_enabled": True,
        "aws_use_mock_data": False,
        "aws_access_key_id": "access-key",
        "aws_secret_access_key": "secret-key",
    }
    values.update(overrides)
    mock_data = values.pop("aws_use_mock_data")
    settings = Settings(**values)
    settings.aws_use_mock_data = mock_data
    return settings


def _aws_response(amount="12.34", service="AmazonEC2"):
    return {
        "ResultsByTime": [
            {
                "TimePeriod": {"Start": "2026-08-01", "End": "2026-08-02"},
                "Groups": [
                    {
                        "Keys": [service],
                        "Metrics": {"UnblendedCost": {"Amount": amount, "Unit": "USD"}},
                    }
                ],
            }
        ]
    }


@pytest.mark.asyncio
async def test_real_mode_calls_cost_explorer_and_normalizes_pages():
    client = MagicMock()
    first = _aws_response()
    first["NextPageToken"] = "next-page"
    client.get_cost_and_usage.side_effect = [first, {"ResultsByTime": []}]
    session = MagicMock()
    session.client.return_value = client
    with patch("app.services.aws.cost_explorer.boto3.Session", return_value=session):
        response = await CostExplorerService(_settings()).get_costs(
            date(2026, 8, 1), date(2026, 8, 2)
        )
    assert response["provider"] == "aws"
    assert response["total_cost"] == 12.34
    assert response["services"] == [{"service_name": "AmazonEC2", "cost": 12.34}]
    assert client.get_cost_and_usage.call_count == 2


@pytest.mark.asyncio
async def test_mock_mode_does_not_create_an_aws_client():
    with patch("app.services.aws.cost_explorer.boto3.Session") as session:
        response = await CostExplorerService(
            _settings(aws_use_mock_data=True)
        ).get_costs(date(2026, 8, 1), date(2026, 8, 2))
    session.assert_not_called()
    assert response["provider"] == "aws"
    assert response["total_cost"] > 0


@pytest.mark.asyncio
async def test_access_denied_is_mapped_without_returning_sdk_message():
    client = MagicMock()
    client.get_cost_and_usage.side_effect = ClientError(
        {"Error": {"Code": "AccessDeniedException", "Message": "credential detail"}},
        "GetCostAndUsage",
    )
    session = MagicMock()
    session.client.return_value = client
    with patch("app.services.aws.cost_explorer.boto3.Session", return_value=session):
        with pytest.raises(AWSPermissionsError, match="Insufficient AWS permissions"):
            await CostExplorerService(_settings()).get_costs(
                date(2026, 8, 1), date(2026, 8, 2)
            )


def test_health_check_uses_real_cost_explorer_when_enabled():
    client = MagicMock()
    client.get_cost_and_usage.return_value = {"ResultsByTime": []}
    session = MagicMock()
    session.client.return_value = client
    with patch("app.services.aws.cost_explorer.boto3.Session", return_value=session):
        assert CostExplorerService(_settings()).health_check() is True
    client.get_cost_and_usage.assert_called_once()


def test_health_check_is_true_for_mock_mode():
    assert CostExplorerService(_settings(aws_use_mock_data=True)).health_check() is True
