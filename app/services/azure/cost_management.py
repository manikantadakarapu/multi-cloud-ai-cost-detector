"""Azure Cost Management service for retrieving and normalizing cost data."""

from __future__ import annotations

import logging
from datetime import date
from typing import Any

from azure.core.exceptions import (
    AzureError,
    ClientAuthenticationError,
    HttpResponseError,
    ServiceRequestError,
)

from app.core.config import Settings
from app.services.azure.exceptions import (
    AzureCredentialsError,
    AzureInvalidSubscriptionError,
    AzurePermissionsError,
    AzureServiceError,
    AzureThrottlingError,
)
from azure.identity import ClientSecretCredential, DefaultAzureCredential
from azure.mgmt.costmanagement import CostManagementClient
from azure.mgmt.subscription import SubscriptionClient

logger = logging.getLogger(__name__)


class AzureCostManagementService:
    """Service for retrieving Azure cost data via the Cost Management Query API.

    Uses ``DefaultAzureCredential`` by default and falls back to
    ``ClientSecretCredential`` when ``AZURE_TENANT_ID``, ``AZURE_CLIENT_ID``
    and ``AZURE_CLIENT_SECRET`` are all provided.
    """

    GRANULARITY_DAILY = "DAILY"
    GRANULARITY_MONTHLY = "MONTHLY"
    SUPPORTED_GRANULARITIES = (GRANULARITY_DAILY, GRANULARITY_MONTHLY)

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._timeout: int | None = settings.azure_request_timeout
        self._credential: Any | None = None
        self._cost_client: CostManagementClient | None = None
        self._subscription_client: SubscriptionClient | None = None

    def _ensure_credential(self) -> Any:
        """Lazy-initialize and cache an Azure credential."""
        if self._credential is not None:
            return self._credential

        tenant_id = self._settings.azure_tenant_id
        client_id = self._settings.azure_client_id
        client_secret = self._settings.azure_client_secret

        try:
            if tenant_id and client_id and client_secret:
                self._credential = ClientSecretCredential(
                    tenant_id=tenant_id,
                    client_id=client_id,
                    client_secret=client_secret,
                )
            else:
                self._credential = DefaultAzureCredential()
        except AzureError as e:
            logger.error("azure_credential_failed", extra={"error": str(e)})
            raise AzureCredentialsError(f"Failed to create Azure credential: {e}") from e

        return self._credential

    def _resolve_subscription_id(self) -> str:
        """Return the configured subscription ID or the first enabled one."""
        configured = self._settings.azure_subscription_id
        if configured:
            return configured

        try:
            credential = self._ensure_credential()
            if self._subscription_client is None:
                self._subscription_client = SubscriptionClient(credential)
            for subscription in self._subscription_client.subscriptions.list(timeout=self._timeout):
                if getattr(subscription, "state", None) == "Enabled":
                    return str(subscription.subscription_id)
        except ClientAuthenticationError as e:
            logger.error("azure_subscription_auth_failed", extra={"error": str(e)})
            raise AzureCredentialsError("Azure credentials not found or invalid") from e
        except HttpResponseError as e:
            status_code = getattr(e, "status_code", None)
            logger.error(
                "azure_subscription_list_failed",
                extra={"error": str(e), "status_code": status_code},
            )
            if status_code in (401, 403):
                raise AzurePermissionsError(
                    "Insufficient Azure permissions to list subscriptions"
                ) from e
            raise AzureServiceError(f"Failed to list Azure subscriptions: {e}") from e
        except AzureError as e:
            logger.error("azure_subscription_list_failed", extra={"error": str(e)})
            raise AzureServiceError(f"Failed to resolve Azure subscription: {e}") from e

        raise AzureInvalidSubscriptionError(
            "No enabled Azure subscription found for the current credential"
        )

    def _build_query(
        self,
        start_date: date,
        end_date: date,
        granularity: str,
    ) -> dict[str, Any]:
        """Build an Azure Cost Management query payload."""
        return {
            "type": "Usage",
            "timeframe": "Custom",
            "time_period": {
                "from": start_date.isoformat(),
                "to": end_date.isoformat(),
            },
            "dataset": {
                "granularity": granularity.capitalize(),
                "aggregation": {
                    "totalCost": {"name": "Cost", "function": "Sum"},
                },
                "grouping": [
                    {"type": "Dimension", "name": "ServiceName"},
                ],
            },
        }

    async def get_costs(
        self,
        start_date: date,
        end_date: date,
        granularity: str,
    ) -> dict[str, Any]:
        """Retrieve and normalize Azure costs for the given date range.

        Args:
            start_date: Start date (inclusive).
            end_date: End date (inclusive).
            granularity: "DAILY" or "MONTHLY".

        Returns:
            Normalized cost data with keys ``provider``, ``currency``,
            ``total_cost``, ``date_range``, and ``services``.

        Raises:
            AzureCredentialsError: If Azure credentials are missing or invalid.
            AzureThrottlingError: If the Azure API throttles the request.
            AzurePermissionsError: If credentials lack required permissions.
            AzureInvalidSubscriptionError: For invalid input or unresolvable subscription.
            AzureServiceError: For other Azure service errors.
        """
        if not self._settings.azure_cost_management_enabled:
            logger.info("azure_cost_management_disabled")
            return {
                "provider": "azure",
                "currency": "USD",
                "total_cost": 0.0,
                "date_range": {
                    "start": start_date.isoformat(),
                    "end": end_date.isoformat(),
                    "granularity": granularity,
                },
                "services": [],
            }

        if granularity not in self.SUPPORTED_GRANULARITIES:
            raise AzureInvalidSubscriptionError(f"Invalid granularity: {granularity}")

        subscription_id = self._resolve_subscription_id()
        scope = f"/subscriptions/{subscription_id}"
        query = self._build_query(start_date, end_date, granularity)

        logger.info(
            "azure_cost_management_request",
            extra={
                "subscription_id": subscription_id,
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "granularity": granularity,
            },
        )

        try:
            credential = self._ensure_credential()
            if self._cost_client is None:
                self._cost_client = CostManagementClient(credential)
            result = self._cost_client.query.usage(scope, query, timeout=self._timeout)
        except ClientAuthenticationError as e:
            logger.error("azure_credentials_missing", extra={"error": str(e)})
            raise AzureCredentialsError("Azure credentials not found or invalid") from e
        except HttpResponseError as e:
            status_code = getattr(e, "status_code", None)
            logger.error(
                "azure_cost_management_http_error",
                extra={"error": str(e), "status_code": status_code},
            )
            if status_code == 429:
                raise AzureThrottlingError("Azure API request throttled") from e
            if status_code in (401, 403):
                raise AzurePermissionsError(
                    "Insufficient Azure permissions for Cost Management"
                ) from e
            if status_code == 400:
                raise AzureInvalidSubscriptionError(f"Invalid Azure request: {e}") from e
            raise AzureServiceError(f"Azure Cost Management error: {e}") from e
        except ServiceRequestError as e:
            logger.error("azure_service_request_failed", extra={"error": str(e)})
            raise AzureServiceError(f"Azure service request failed: {e}") from e
        except AzureError as e:
            logger.error("azure_cost_management_unexpected", extra={"error": str(e)})
            raise AzureServiceError(f"Unexpected Azure Cost Management error: {e}") from e

        return self._normalize_response(result, start_date, end_date, granularity)

    def _normalize_response(
        self,
        result: Any,
        start_date: date,
        end_date: date,
        granularity: str,
    ) -> dict[str, Any]:
        """Normalize an Azure ``QueryResult`` to the unified schema."""
        columns = list(getattr(result, "columns", []) or [])
        rows = list(getattr(result, "rows", []) or [])

        service_idx: int | None = None
        cost_idx: int | None = None
        currency_idx: int | None = None

        for index, column in enumerate(columns):
            name = (getattr(column, "name", "") or "").lower()
            if name == "servicename" and service_idx is None:
                service_idx = index
            elif name == "cost" and cost_idx is None:
                cost_idx = index
            elif name == "currency" and currency_idx is None:
                currency_idx = index

        services: dict[str, float] = {}
        total_cost = 0.0
        currency = "USD"

        for row in rows:
            service_name = (
                str(row[service_idx])
                if service_idx is not None and service_idx < len(row)
                else "Unknown"
            )
            try:
                cost = float(row[cost_idx]) if cost_idx is not None and cost_idx < len(row) else 0.0
            except (TypeError, ValueError):
                cost = 0.0

            if currency_idx is not None and currency_idx < len(row) and row[currency_idx]:
                currency = str(row[currency_idx])

            if cost > 0:
                services[service_name] = services.get(service_name, 0.0) + cost
                total_cost += cost

        sorted_services = sorted(services.items(), key=lambda item: item[1], reverse=True)

        return {
            "provider": "azure",
            "currency": currency,
            "total_cost": round(total_cost, 2),
            "date_range": {
                "start": start_date.isoformat(),
                "end": end_date.isoformat(),
                "granularity": granularity,
            },
            "services": [
                {"service_name": name, "cost": round(cost, 2)} for name, cost in sorted_services
            ],
        }
