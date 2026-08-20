"""AWS Cost Explorer specific exceptions."""

from __future__ import annotations


class AWSCostExplorerError(Exception):
    """Base exception for AWS Cost Explorer errors."""

    def __init__(self, message: str, error_code: str = "AWS_COST_EXPLORER_ERROR") -> None:
        self.message = message
        self.error_code = error_code
        super().__init__(message)


class AWSCredentialsError(AWSCostExplorerError):
    """Raised when AWS credentials are missing or invalid."""

    def __init__(self, message: str = "AWS credentials not found or invalid") -> None:
        super().__init__(message, error_code="AWS_CREDENTIALS_ERROR")


class AWSThrottlingError(AWSCostExplorerError):
    """Raised when AWS API throttles the request."""

    def __init__(self, message: str = "AWS API request throttled") -> None:
        super().__init__(message, error_code="AWS_THROTTLING_ERROR")


class AWSPermissionsError(AWSCostExplorerError):
    """Raised when AWS credentials lack required permissions."""

    def __init__(self, message: str = "Insufficient AWS permissions for Cost Explorer") -> None:
        super().__init__(message, error_code="AWS_PERMISSIONS_ERROR")


class AWSInvalidDateRangeError(AWSCostExplorerError):
    """Raised when date range is invalid for Cost Explorer API."""

    def __init__(self, message: str = "Invalid date range for Cost Explorer query") -> None:
        super().__init__(message, error_code="AWS_INVALID_DATE_RANGE")


class AWSServiceError(AWSCostExplorerError):
    """Raised for unexpected AWS service errors."""

    def __init__(self, message: str = "AWS Cost Explorer service error") -> None:
        super().__init__(message, error_code="AWS_SERVICE_ERROR")
