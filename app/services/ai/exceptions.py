"""Domain exceptions for the Gemini cost-insight loop."""

from __future__ import annotations


class AIInsightError(Exception):
    """Base exception for AI insight failures that must not break the dashboard."""

    def __init__(self, message: str, error_code: str = "AI_INSIGHT_ERROR") -> None:
        self.message = message
        self.error_code = error_code
        super().__init__(message)


class GeminiUnavailableError(AIInsightError):
    """Raised when Gemini cannot be called."""

    def __init__(self, message: str = "Gemini is unavailable") -> None:
        super().__init__(message, "AI_UNAVAILABLE")


class GeminiTimeoutError(AIInsightError):
    """Raised when a Gemini request exceeds the configured timeout."""

    def __init__(self, message: str = "Gemini request timed out") -> None:
        super().__init__(message, "AI_TIMEOUT")


class GeminiQuotaError(AIInsightError):
    """Raised when Gemini rejects the request because of quota or rate limits."""

    def __init__(self, message: str = "Gemini quota exceeded") -> None:
        super().__init__(message, "AI_QUOTA_EXCEEDED")


class GeminiInvalidResponseError(AIInsightError):
    """Raised when Gemini returns malformed or unusable output."""

    def __init__(self, message: str = "Gemini response was invalid") -> None:
        super().__init__(message, "AI_RESPONSE_INVALID")
