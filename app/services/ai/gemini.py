"""Small Gemini client for structured cost-insight generation."""

from __future__ import annotations

import asyncio
import json
from typing import Any, Protocol

from app.core.logging import get_logger
from app.services.ai.exceptions import (
    GeminiInvalidResponseError,
    GeminiQuotaError,
    GeminiTimeoutError,
    GeminiUnavailableError,
)

logger = get_logger(__name__)

try:  # pragma: no cover - import exercised when the optional SDK is installed
    from google import genai
    from google.genai import types as genai_types
except ImportError:  # pragma: no cover - tests inject a fake client
    genai = None  # type: ignore[assignment]
    genai_types = None  # type: ignore[assignment]


class InsightGenerator(Protocol):
    """Test seam for Gemini JSON generation."""

    async def generate_json(self, system_prompt: str, user_prompt: str) -> str:
        """Return a JSON object string describing the supplied cost event."""
        ...


def parse_model_json(text: str) -> dict[str, Any]:
    """Parse a JSON object from model text, ignoring optional markdown fences."""
    payload = text.strip()
    if payload.startswith("```"):
        lines = payload.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        payload = "\n".join(lines).strip()
        if payload.lower().startswith("json"):
            payload = payload[4:].strip()
    try:
        parsed = json.loads(payload)
    except json.JSONDecodeError as error:
        raise GeminiInvalidResponseError(
            "Gemini response was not valid JSON"
        ) from error
    if not isinstance(parsed, dict):
        raise GeminiInvalidResponseError("Gemini response was not a JSON object")
    return parsed


class GeminiInsightClient:
    """Call Gemini once per cost event and return raw JSON text."""

    def __init__(
        self,
        api_key: str,
        model: str,
        timeout_seconds: int,
        max_output_tokens: int,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._timeout_seconds = timeout_seconds
        self._max_output_tokens = max_output_tokens

    async def generate_json(self, system_prompt: str, user_prompt: str) -> str:
        if not self._api_key:
            raise GeminiUnavailableError("Gemini API key is not configured")
        if genai is None or genai_types is None:
            raise GeminiUnavailableError("Gemini SDK is not installed")

        client = genai.Client(
            api_key=self._api_key,
            http_options=genai_types.HttpOptions(timeout=self._timeout_seconds * 1000),
        )
        config = genai_types.GenerateContentConfig(
            system_instruction=system_prompt,
            response_mime_type="application/json",
            max_output_tokens=self._max_output_tokens,
            temperature=0.2,
        )
        try:
            response = await asyncio.wait_for(
                client.aio.models.generate_content(
                    model=self._model,
                    contents=user_prompt,
                    config=config,
                ),
                timeout=self._timeout_seconds,
            )
        except TimeoutError as error:
            raise GeminiTimeoutError() from error
        except Exception as error:
            raise _map_gemini_error(error) from error

        text = getattr(response, "text", None)
        if not isinstance(text, str) or not text.strip():
            raise GeminiInvalidResponseError("Gemini returned an empty response")
        return text


def _map_gemini_error(error: Exception) -> Exception:
    """Translate SDK failures into dashboard-safe domain errors without leaking details."""
    raw = str(error).lower()
    status = getattr(error, "status_code", None) or getattr(error, "code", None)
    if status in {401, 403} or "api key" in raw or "permission" in raw:
        logger.warning("gemini_auth_failed")
        return GeminiUnavailableError()
    if (
        status == 429
        or "resource_exhausted" in raw
        or "quota" in raw
        or "rate limit" in raw
    ):
        logger.warning("gemini_quota_exceeded")
        return GeminiQuotaError()
    if status in {408, 504} or "timeout" in raw or "timed out" in raw:
        logger.warning("gemini_timeout")
        return GeminiTimeoutError()
    logger.warning("gemini_request_failed")
    return GeminiUnavailableError()
