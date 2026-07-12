from __future__ import annotations

import pytest

from app.services.gcp.exceptions import (
    GCPBigQueryError,
    GCPBillingAccountNotFoundError,
    GCPBillingError,
    GCPCredentialsError,
    GCPQuotaExceededError,
)


@pytest.mark.parametrize(
    "exc_class",
    [
        GCPCredentialsError,
        GCPBigQueryError,
        GCPQuotaExceededError,
        GCPBillingAccountNotFoundError,
    ],
)
def test_gcp_exception_stores_message(exc_class: type[GCPBillingError]) -> None:
    """Each GCP exception stores the provided message and defaults original_error."""
    exc = exc_class("Something went wrong")
    assert exc.message == "Something went wrong"
    assert str(exc) == "Something went wrong"
    assert isinstance(exc, Exception)
    assert isinstance(exc, GCPBillingError)


@pytest.mark.parametrize(
    "exc_class, default_code",
    [
        (GCPCredentialsError, "GCP_CREDENTIALS_ERROR"),
        (GCPBigQueryError, "GCP_BIGQUERY_ERROR"),
        (GCPQuotaExceededError, "GCP_QUOTA_EXCEEDED"),
        (GCPBillingAccountNotFoundError, "GCP_BILLING_ACCOUNT_NOT_FOUND"),
    ],
)
def test_gcp_exception_default_error_code(
    exc_class: type[GCPBillingError], default_code: str
) -> None:
    """Each GCP exception has a stable default error_code matching AWS/Azure pattern."""
    exc = exc_class()
    assert exc.error_code == default_code
    assert isinstance(exc.message, str)


def test_gcp_base_exception_accepts_custom_error_code() -> None:
    """Base GCPBillingError allows overriding error_code."""
    exc = GCPBillingError("custom", error_code="CUSTOM_CODE")
    assert exc.message == "custom"
    assert exc.error_code == "CUSTOM_CODE"
