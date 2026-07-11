"""Azure services package."""

from __future__ import annotations

from app.services.azure.exceptions import (
    AzureCostManagementError,
    AzureCredentialsError,
    AzureInvalidSubscriptionError,
    AzurePermissionsError,
    AzureServiceError,
    AzureThrottlingError,
)

__all__ = [
    "AzureCostManagementError",
    "AzureCredentialsError",
    "AzureInvalidSubscriptionError",
    "AzurePermissionsError",
    "AzureServiceError",
    "AzureThrottlingError",
]
