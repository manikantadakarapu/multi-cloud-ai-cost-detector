"""Domain exceptions raised by the analytics layer."""

from __future__ import annotations


class AnalyticsError(Exception):
    """Base exception for deterministic analytics failures."""

    def __init__(self, message: str, error_code: str = "ANALYTICS_ERROR") -> None:
        self.message = message
        self.error_code = error_code
        super().__init__(message)


class AnalyticsInvalidPeriodError(AnalyticsError):
    """Raised when an analytics period is invalid."""

    def __init__(self, message: str = "Invalid analytics period") -> None:
        super().__init__(message, "ANALYTICS_INVALID_PERIOD")


class AnalyticsCurrencyError(AnalyticsError):
    """Raised when a calculation would mix incompatible currencies."""

    def __init__(self, message: str = "Incompatible currencies") -> None:
        super().__init__(message, "ANALYTICS_CURRENCY_MISMATCH")


class AnalyticsNoDataError(AnalyticsError):
    """Raised when a requested analytics result has no cost data."""

    def __init__(self, message: str = "No cost data available") -> None:
        super().__init__(message, "ANALYTICS_NO_DATA")
