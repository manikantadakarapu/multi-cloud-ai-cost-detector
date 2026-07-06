"""Azure Cost Management specific exceptions."""

from __future__ import annotations


class AzureCostManagementError(Exception):
    """Base exception for Azure Cost Management errors."""

    def __init__(
        self, message: str, error_code: str = "AZURE_COST_MANAGEMENT_ERROR"
    ) -> None:
        self.message = message
        self.error_code = error_code
        super().__init__(message)


class AzureCredentialsError(AzureCostManagementError):
    """Raised when Azure credentials are missing or invalid."""

    def __init__(self, message: str = "Azure credentials not found or invalid") -> None:
        super().__init__(message, error_code="AZURE_CREDENTIALS_ERROR")


class AzureThrottlingError(AzureCostManagementError):
    """Raised when Azure API throttles the request."""

    def __init__(self, message: str = "Azure API request throttled") -> None:
        super().__init__(message, error_code="AZURE_THROTTLING_ERROR")


class AzurePermissionsError(AzureCostManagementError):
    """Raised when credentials lack required permissions."""

    def __init__(
        self, message: str = "Insufficient Azure permissions for Cost Management"
    ) -> None:
        super().__init__(message, error_code="AZURE_PERMISSIONS_ERROR")


class AzureInvalidSubscriptionError(AzureCostManagementError):
    """Raised when the Azure subscription is invalid or cannot be resolved."""

    def __init__(self, message: str = "Invalid or missing Azure subscription") -> None:
        super().__init__(message, error_code="AZURE_INVALID_SUBSCRIPTION")


class AzureServiceError(AzureCostManagementError):
    """Raised for unexpected Azure service errors."""

    def __init__(self, message: str = "Azure Cost Management service error") -> None:
        super().__init__(message, error_code="AZURE_SERVICE_ERROR")
