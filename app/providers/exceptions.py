"""Provider-agnostic exception hierarchy.

These exceptions mirror the AWS-specific ones in
``app.services.aws.exceptions`` but are not tied to any vendor. Every
concrete provider implementation should translate its vendor-specific
errors into one of these types so route handlers can map them to HTTP
responses without knowing which cloud they came from.
"""

from __future__ import annotations


class ProviderError(Exception):
    """Base exception for all cloud provider errors."""

    def __init__(self, message: str, error_code: str = "PROVIDER_ERROR") -> None:
        self.message = message
        self.error_code = error_code
        super().__init__(message)


class ProviderCredentialsError(ProviderError):
    """Raised when cloud provider credentials are missing or invalid."""

    def __init__(
        self, message: str = "Cloud provider credentials not found or invalid"
    ) -> None:
        super().__init__(message, error_code="PROVIDER_CREDENTIALS_ERROR")


class ProviderThrottlingError(ProviderError):
    """Raised when the cloud provider API throttles the request."""

    def __init__(self, message: str = "Cloud provider API request throttled") -> None:
        super().__init__(message, error_code="PROVIDER_THROTTLING_ERROR")


class ProviderPermissionsError(ProviderError):
    """Raised when credentials lack required permissions for the API."""

    def __init__(
        self, message: str = "Insufficient cloud provider permissions"
    ) -> None:
        super().__init__(message, error_code="PROVIDER_PERMISSIONS_ERROR")


class ProviderInvalidDateRangeError(ProviderError):
    """Raised when the requested date range is invalid."""

    def __init__(self, message: str = "Invalid date range for provider query") -> None:
        super().__init__(message, error_code="PROVIDER_INVALID_DATE_RANGE")


class ProviderServiceError(ProviderError):
    """Raised for unexpected cloud provider service errors."""

    def __init__(self, message: str = "Cloud provider service error") -> None:
        super().__init__(message, error_code="PROVIDER_SERVICE_ERROR")
