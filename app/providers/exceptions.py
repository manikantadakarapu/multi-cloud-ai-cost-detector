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


class ProviderNotSupportedException(ProviderError):
    """Raised when a requested cloud provider is not registered.

    This is a more specific subclass of :class:`ProviderError` used by
    the resolver for the case where the provider name itself is
    unrecognised (as opposed to a runtime error from a registered
    provider). The unified cost API surfaces this via a
    ``400 Bad Request`` response. Existing code that catches the
    broader :class:`ProviderError` continues to work unchanged.
    """

    def __init__(
        self,
        message: str = "Cloud provider not supported",
        name: str | None = None,
    ) -> None:
        if name is not None and message == "Cloud provider not supported":
            message = f"Cloud provider '{name}' is not supported"
        super().__init__(message, error_code="PROVIDER_NOT_SUPPORTED")
        self.name = name
