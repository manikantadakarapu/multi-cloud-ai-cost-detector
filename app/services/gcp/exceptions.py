"""GCP Billing service specific exceptions."""

from __future__ import annotations


class GCPBillingError(Exception):
    """Base exception for GCP Billing errors."""

    def __init__(self, message: str, error_code: str = "GCP_BILLING_ERROR") -> None:
        self.message = message
        self.error_code = error_code
        super().__init__(message)


class GCPCredentialsError(GCPBillingError):
    """Raised when GCP ADC or authentication fails."""

    def __init__(self, message: str = "GCP credentials not found or invalid") -> None:
        super().__init__(message, error_code="GCP_CREDENTIALS_ERROR")


class GCPBigQueryError(GCPBillingError):
    """Base or generic exception for BigQuery errors."""

    def __init__(self, message: str = "GCP BigQuery service error") -> None:
        super().__init__(message, error_code="GCP_BIGQUERY_ERROR")


class GCPQuotaExceededError(GCPBillingError):
    """Raised when a BigQuery quota or rate-limit is exceeded."""

    def __init__(self, message: str = "GCP BigQuery quota exceeded") -> None:
        super().__init__(message, error_code="GCP_QUOTA_EXCEEDED")


class GCPBillingAccountNotFoundError(GCPBillingError):
    """Raised when the configured billing account cannot be resolved."""

    def __init__(self, message: str = "GCP billing account not found") -> None:
        super().__init__(message, error_code="GCP_BILLING_ACCOUNT_NOT_FOUND")
