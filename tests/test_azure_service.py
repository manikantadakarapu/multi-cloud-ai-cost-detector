from __future__ import annotations

from datetime import date
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from azure.core.exceptions import (
    ClientAuthenticationError,
    HttpResponseError,
    ServiceRequestError,
)

from app.core.config import Settings
from app.services.azure import cost_management as cost_management_module
from app.services.azure.cost_management import AzureCostManagementService
from app.services.azure.exceptions import (
    AzureCredentialsError,
    AzureInvalidSubscriptionError,
    AzurePermissionsError,
    AzureServiceError,
    AzureThrottlingError,
)


def _make_settings(**overrides: Any) -> Settings:
    base = {
        "JWT_SECRET_KEY": "test-secret",
        "AZURE_COST_MANAGEMENT_ENABLED": True,
        "AZURE_SUBSCRIPTION_ID": "00000000-0000-0000-0000-000000000000",
        "AZURE_TENANT_ID": None,
        "AZURE_CLIENT_ID": None,
        "AZURE_CLIENT_SECRET": None,
        "AZURE_REQUEST_TIMEOUT": 30,
    }
    base.update(overrides)
    return Settings(**base)


@pytest.fixture
def service() -> AzureCostManagementService:
    return AzureCostManagementService(_make_settings())


def _query_result(rows: list[list[Any]], columns: list[Any] | None = None) -> MagicMock:
    result = MagicMock()
    result.rows = rows
    if columns is None:
        service_col = MagicMock()
        service_col.name = "ServiceName"
        cost_col = MagicMock()
        cost_col.name = "Cost"
        columns = [service_col, cost_col]
    result.columns = columns
    return result


class TestAzureCostManagementService:
    @pytest.mark.asyncio
    async def test_disabled_returns_empty_response(self) -> None:
        settings = _make_settings(AZURE_COST_MANAGEMENT_ENABLED=False)
        svc = AzureCostManagementService(settings)

        with patch.object(
            cost_management_module, "CostManagementClient"
        ) as mock_client:
            result = await svc.get_costs(
                start_date=date(2024, 1, 1),
                end_date=date(2024, 1, 31),
                granularity="DAILY",
            )

        assert result["provider"] == "azure"
        assert result["currency"] == "USD"
        assert result["total_cost"] == 0.0
        assert result["services"] == []
        assert result["date_range"] == {
            "start": "2024-01-01",
            "end": "2024-01-31",
            "granularity": "DAILY",
        }
        mock_client.assert_not_called()

    @pytest.mark.asyncio
    async def test_invalid_granularity_raises(
        self, service: AzureCostManagementService
    ) -> None:
        with pytest.raises(AzureInvalidSubscriptionError):
            await service.get_costs(
                start_date=date(2024, 1, 1),
                end_date=date(2024, 1, 31),
                granularity="WEEKLY",
            )

    @pytest.mark.asyncio
    async def test_configured_subscription_id_skips_discovery(
        self, service: AzureCostManagementService
    ) -> None:
        settings = _make_settings(
            AZURE_SUBSCRIPTION_ID="11111111-1111-1111-1111-111111111111"
        )
        svc = AzureCostManagementService(settings)

        query_result = _query_result(
            rows=[["Storage", 50.0]],
        )

        with (
            patch.object(
                cost_management_module, "SubscriptionClient"
            ) as mock_sub_client,
            patch.object(
                cost_management_module, "CostManagementClient"
            ) as mock_cost_client,
        ):
            mock_cost_client.return_value.query.usage.return_value = query_result

            result = await svc.get_costs(
                start_date=date(2024, 1, 1),
                end_date=date(2024, 1, 31),
                granularity="DAILY",
            )

        mock_sub_client.assert_not_called()
        assert mock_cost_client.return_value.query.usage.call_count == 1
        call_args = mock_cost_client.return_value.query.usage.call_args
        assert (
            call_args.args[0] == "/subscriptions/11111111-1111-1111-1111-111111111111"
        )
        assert result["provider"] == "azure"
        assert result["total_cost"] == 50.0

    @pytest.mark.asyncio
    async def test_default_subscription_discovery(
        self, service: AzureCostManagementService
    ) -> None:
        svc = AzureCostManagementService(_make_settings(AZURE_SUBSCRIPTION_ID=None))
        query_result = _query_result(rows=[["Compute", 75.0]])

        with (
            patch.object(
                cost_management_module, "SubscriptionClient"
            ) as mock_sub_client,
            patch.object(
                cost_management_module, "CostManagementClient"
            ) as mock_cost_client,
        ):
            disabled = MagicMock()
            disabled.state = "Disabled"
            disabled.subscription_id = "00000000-0000-0000-0000-000000000000"
            enabled = MagicMock()
            enabled.state = "Enabled"
            enabled.subscription_id = "22222222-2222-2222-2222-222222222222"

            mock_sub_client.return_value.subscriptions.list.return_value = [
                disabled,
                enabled,
            ]
            mock_cost_client.return_value.query.usage.return_value = query_result

            result = await svc.get_costs(
                start_date=date(2024, 1, 1),
                end_date=date(2024, 1, 31),
                granularity="DAILY",
            )

        mock_sub_client.assert_called_once()
        assert (
            mock_cost_client.return_value.query.usage.call_args.args[0]
            == "/subscriptions/22222222-2222-2222-2222-222222222222"
        )
        assert result["total_cost"] == 75.0

    @pytest.mark.asyncio
    async def test_credential_error_raises_azure_credentials_error(
        self, service: AzureCostManagementService
    ) -> None:
        from azure.core.exceptions import AzureError

        with patch.object(
            cost_management_module, "DefaultAzureCredential"
        ) as mock_cred:
            mock_cred.side_effect = AzureError("boom")
            with pytest.raises(AzureCredentialsError):
                await service.get_costs(
                    start_date=date(2024, 1, 1),
                    end_date=date(2024, 1, 31),
                    granularity="DAILY",
                )

    @pytest.mark.asyncio
    async def test_runtime_authentication_error_raises_azure_credentials_error(
        self, service: AzureCostManagementService
    ) -> None:
        with (
            patch.object(cost_management_module, "SubscriptionClient"),
            patch.object(
                cost_management_module, "CostManagementClient"
            ) as mock_cost_client,
        ):
            mock_cost_client.return_value.query.usage.side_effect = (
                ClientAuthenticationError("no token")
            )

            with pytest.raises(AzureCredentialsError):
                await service.get_costs(
                    start_date=date(2024, 1, 1),
                    end_date=date(2024, 1, 31),
                    granularity="DAILY",
                )

    @pytest.mark.asyncio
    async def test_permission_error_raises_azure_permissions_error(
        self, service: AzureCostManagementService
    ) -> None:
        response = MagicMock()
        response.status_code = 403
        http_error = HttpResponseError(response=response)

        with patch.object(
            cost_management_module, "CostManagementClient"
        ) as mock_cost_client:
            mock_cost_client.return_value.query.usage.side_effect = http_error

            with pytest.raises(AzurePermissionsError):
                await service.get_costs(
                    start_date=date(2024, 1, 1),
                    end_date=date(2024, 1, 31),
                    granularity="DAILY",
                )

    @pytest.mark.asyncio
    async def test_throttling_raises_azure_throttling_error(
        self, service: AzureCostManagementService
    ) -> None:
        response = MagicMock()
        response.status_code = 429
        http_error = HttpResponseError(response=response)

        with patch.object(
            cost_management_module, "CostManagementClient"
        ) as mock_cost_client:
            mock_cost_client.return_value.query.usage.side_effect = http_error

            with pytest.raises(AzureThrottlingError):
                await service.get_costs(
                    start_date=date(2024, 1, 1),
                    end_date=date(2024, 1, 31),
                    granularity="DAILY",
                )

    @pytest.mark.asyncio
    async def test_service_request_error_raises_azure_service_error(
        self, service: AzureCostManagementService
    ) -> None:
        with patch.object(
            cost_management_module, "CostManagementClient"
        ) as mock_cost_client:
            mock_cost_client.return_value.query.usage.side_effect = ServiceRequestError(
                "transport"
            )

            with pytest.raises(AzureServiceError):
                await service.get_costs(
                    start_date=date(2024, 1, 1),
                    end_date=date(2024, 1, 31),
                    granularity="DAILY",
                )

    @pytest.mark.asyncio
    async def test_generic_http_error_raises_azure_service_error(
        self, service: AzureCostManagementService
    ) -> None:
        response = MagicMock()
        response.status_code = 500
        http_error = HttpResponseError(response=response)

        with patch.object(
            cost_management_module, "CostManagementClient"
        ) as mock_cost_client:
            mock_cost_client.return_value.query.usage.side_effect = http_error

            with pytest.raises(AzureServiceError):
                await service.get_costs(
                    start_date=date(2024, 1, 1),
                    end_date=date(2024, 1, 31),
                    granularity="DAILY",
                )

    @pytest.mark.asyncio
    async def test_subscription_discovery_403_raises_permissions_error(self) -> None:
        svc = AzureCostManagementService(_make_settings(AZURE_SUBSCRIPTION_ID=None))

        response = MagicMock()
        response.status_code = 403
        http_error = HttpResponseError(response=response)

        with patch.object(
            cost_management_module, "SubscriptionClient"
        ) as mock_sub_client:
            mock_sub_client.return_value.subscriptions.list.side_effect = http_error

            with pytest.raises(AzurePermissionsError):
                await svc.get_costs(
                    start_date=date(2024, 1, 1),
                    end_date=date(2024, 1, 31),
                    granularity="DAILY",
                )

    @pytest.mark.asyncio
    async def test_no_enabled_subscription_raises_invalid(self) -> None:
        svc = AzureCostManagementService(_make_settings(AZURE_SUBSCRIPTION_ID=None))

        disabled = MagicMock()
        disabled.state = "Disabled"
        disabled.subscription_id = "00000000-0000-0000-0000-000000000000"

        with patch.object(
            cost_management_module, "SubscriptionClient"
        ) as mock_sub_client:
            mock_sub_client.return_value.subscriptions.list.return_value = [disabled]

            with pytest.raises(AzureInvalidSubscriptionError):
                await svc.get_costs(
                    start_date=date(2024, 1, 1),
                    end_date=date(2024, 1, 31),
                    granularity="DAILY",
                )

    @pytest.mark.asyncio
    async def test_successful_query_returns_normalized_dict(
        self, service: AzureCostManagementService
    ) -> None:
        service_col = MagicMock()
        service_col.name = "ServiceName"
        cost_col = MagicMock()
        cost_col.name = "Cost"
        currency_col = MagicMock()
        currency_col.name = "Currency"
        columns = [service_col, cost_col, currency_col]
        query_result = _query_result(
            rows=[
                ["Storage", 100.50, "USD"],
                ["Compute", 50.25, "USD"],
                ["Storage", 25.25, "USD"],
                ["Network", 0.0, "USD"],
            ],
            columns=columns,
        )

        with patch.object(
            cost_management_module, "CostManagementClient"
        ) as mock_cost_client:
            mock_cost_client.return_value.query.usage.return_value = query_result

            result = await service.get_costs(
                start_date=date(2024, 1, 1),
                end_date=date(2024, 1, 31),
                granularity="DAILY",
            )

        assert result["provider"] == "azure"
        assert result["currency"] == "USD"
        assert result["total_cost"] == 176.0
        assert result["date_range"] == {
            "start": "2024-01-01",
            "end": "2024-01-31",
            "granularity": "DAILY",
        }
        # Services are sorted by descending cost; zero-cost entries dropped
        assert [s["service_name"] for s in result["services"]] == ["Storage", "Compute"]
        assert result["services"][0]["cost"] == 125.75
        assert result["services"][1]["cost"] == 50.25

    @pytest.mark.asyncio
    async def test_query_payload_uses_expected_structure(
        self, service: AzureCostManagementService
    ) -> None:
        query_result = _query_result(rows=[["Storage", 10.0]])

        with patch.object(
            cost_management_module, "CostManagementClient"
        ) as mock_cost_client:
            mock_cost_client.return_value.query.usage.return_value = query_result

            await service.get_costs(
                start_date=date(2024, 1, 1),
                end_date=date(2024, 1, 31),
                granularity="MONTHLY",
            )

        call_args = mock_cost_client.return_value.query.usage.call_args
        scope_arg, query_arg = call_args.args
        assert scope_arg == "/subscriptions/00000000-0000-0000-0000-000000000000"
        assert query_arg["type"] == "Usage"
        assert query_arg["timeframe"] == "Custom"
        assert query_arg["time_period"]["from"] == "2024-01-01"
        assert query_arg["time_period"]["to"] == "2024-01-31"
        assert query_arg["dataset"]["granularity"] == "Monthly"
        assert query_arg["dataset"]["grouping"] == [
            {"type": "Dimension", "name": "ServiceName"}
        ]
        assert query_arg["dataset"]["aggregation"]["totalCost"] == {
            "name": "Cost",
            "function": "Sum",
        }

    @pytest.mark.asyncio
    async def test_client_secret_credential_used_when_all_three_settings_present(
        self,
    ) -> None:
        settings = _make_settings(
            AZURE_TENANT_ID="tenant",
            AZURE_CLIENT_ID="client",
            AZURE_CLIENT_SECRET="secret",
        )
        svc = AzureCostManagementService(settings)

        query_result = _query_result(rows=[["Storage", 10.0]])

        with (
            patch.object(cost_management_module, "ClientSecretCredential") as mock_csc,
            patch.object(cost_management_module, "DefaultAzureCredential") as mock_dac,
            patch.object(
                cost_management_module, "CostManagementClient"
            ) as mock_cost_client,
        ):
            mock_cost_client.return_value.query.usage.return_value = query_result
            await svc.get_costs(
                start_date=date(2024, 1, 1),
                end_date=date(2024, 1, 31),
                granularity="DAILY",
            )

        mock_csc.assert_called_once_with(
            tenant_id="tenant", client_id="client", client_secret="secret"
        )
        mock_dac.assert_not_called()

    @pytest.mark.asyncio
    async def test_default_timeout_passed_to_client_calls(
        self, service: AzureCostManagementService
    ) -> None:
        query_result = _query_result(rows=[["Storage", 10.0]])

        with patch.object(
            cost_management_module, "CostManagementClient"
        ) as mock_cost_client:
            mock_cost_client.return_value.query.usage.return_value = query_result

            await service.get_costs(
                start_date=date(2024, 1, 1),
                end_date=date(2024, 1, 31),
                granularity="DAILY",
            )

        call_kwargs = mock_cost_client.return_value.query.usage.call_args.kwargs
        assert call_kwargs.get("timeout") == 30

    @pytest.mark.asyncio
    async def test_custom_timeout_passed_to_client_calls(
        self,
    ) -> None:
        settings = _make_settings(AZURE_REQUEST_TIMEOUT=60)
        svc = AzureCostManagementService(settings)
        query_result = _query_result(rows=[["Storage", 10.0]])

        with patch.object(
            cost_management_module, "CostManagementClient"
        ) as mock_cost_client:
            mock_cost_client.return_value.query.usage.return_value = query_result

            await svc.get_costs(
                start_date=date(2024, 1, 1),
                end_date=date(2024, 1, 31),
                granularity="DAILY",
            )

        call_kwargs = mock_cost_client.return_value.query.usage.call_args.kwargs
        assert call_kwargs.get("timeout") == 60

    @pytest.mark.asyncio
    async def test_timeout_passed_to_subscription_list(self) -> None:
        settings = _make_settings(AZURE_SUBSCRIPTION_ID=None, AZURE_REQUEST_TIMEOUT=45)
        svc = AzureCostManagementService(settings)
        query_result = _query_result(rows=[["Storage", 10.0]])

        with (
            patch.object(
                cost_management_module, "SubscriptionClient"
            ) as mock_sub_client,
            patch.object(
                cost_management_module, "CostManagementClient"
            ) as mock_cost_client,
        ):
            enabled = MagicMock()
            enabled.state = "Enabled"
            enabled.subscription_id = "22222222-2222-2222-2222-222222222222"
            mock_sub_client.return_value.subscriptions.list.return_value = [enabled]
            mock_cost_client.return_value.query.usage.return_value = query_result

            await svc.get_costs(
                start_date=date(2024, 1, 1),
                end_date=date(2024, 1, 31),
                granularity="DAILY",
            )

        sub_call_kwargs = (
            mock_sub_client.return_value.subscriptions.list.call_args.kwargs
        )
        assert sub_call_kwargs.get("timeout") == 45
        cost_call_kwargs = mock_cost_client.return_value.query.usage.call_args.kwargs
        assert cost_call_kwargs.get("timeout") == 45

    @pytest.mark.asyncio
    async def test_empty_query_result_returns_zero_total(
        self, service: AzureCostManagementService
    ) -> None:
        query_result = _query_result(rows=[])

        with patch.object(
            cost_management_module, "CostManagementClient"
        ) as mock_cost_client:
            mock_cost_client.return_value.query.usage.return_value = query_result

            result = await service.get_costs(
                start_date=date(2024, 1, 1),
                end_date=date(2024, 1, 31),
                granularity="DAILY",
            )

        assert result["provider"] == "azure"
        assert result["total_cost"] == 0.0
        assert result["services"] == []

    @pytest.mark.asyncio
    async def test_invalid_azure_request_returns_invalid_subscription_error(
        self, service: AzureCostManagementService
    ) -> None:
        response = MagicMock()
        response.status_code = 400
        http_error = HttpResponseError(response=response)

        with patch.object(
            cost_management_module, "CostManagementClient"
        ) as mock_cost_client:
            mock_cost_client.return_value.query.usage.side_effect = http_error

            with pytest.raises(AzureInvalidSubscriptionError):
                await service.get_costs(
                    start_date=date(2024, 1, 1),
                    end_date=date(2024, 1, 31),
                    granularity="DAILY",
                )
