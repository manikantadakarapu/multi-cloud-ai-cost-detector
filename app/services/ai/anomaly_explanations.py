"""On-demand, evidence-constrained AI explanations for deterministic anomalies."""

from __future__ import annotations

import hashlib
import re
from datetime import UTC, date, datetime

from pydantic import ValidationError

from app.core.cache import RedisCache
from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.schemas.anomaly import Anomaly, AnomalyQuery
from app.schemas.anomaly_explanation import (
    AnomalyExplanationDraft,
    AnomalyExplanationRequest,
    AnomalyExplanationResponse,
    AnomalyInvestigationContext,
    ExplanationStatus,
)
from app.services.ai.anomaly_context import build_anomaly_context
from app.services.ai.exceptions import (
    GeminiInvalidResponseError,
    GeminiQuotaError,
    GeminiTimeoutError,
    GeminiUnavailableError,
)
from app.services.ai.gemini import (
    GeminiInsightClient,
    InsightGenerator,
    parse_model_json,
)
from app.services.anomaly import AnomalyDetectionService
from app.services.explorer.service import CostExplorerService

logger = get_logger(__name__)
PROMPT_VERSION = "1.0"
FALLBACK_MESSAGE = (
    "AI explanation is currently unavailable. Review the anomaly evidence and "
    "Cost Explorer breakdown."
)

SYSTEM_PROMPT = f"""You are an anomaly investigation assistant for a FinOps dashboard.
Prompt version: {PROMPT_VERSION}.

The user message is JSON containing deterministic, labeled evidence for one
already-detected anomaly. Use only that evidence.
Do not detect or score anomalies, change severity, invent metrics, invent
provider activity, or claim certainty without evidence.
Distinguish verified facts from derived values and unknowns. If evidence is
insufficient, state that explicitly.
Return JSON only with exactly these keys:
summary, likely_causes, impact, investigation_steps, confidence, limitations.
Each likely_causes item must contain cause, evidence, and confidence. Do not
include secrets or raw provider payloads.
"""


class AnomalyExplanationNotFoundError(Exception):
    """Raised when an anomaly cannot be re-resolved from deterministic data."""


def _numeric_claims(value: str) -> set[str]:
    return set(re.findall(r"(?<![A-Za-z])\d+(?:\.\d+)?(?:%|x)?", value))


def validate_anomaly_explanation(
    context: AnomalyInvestigationContext, raw_text: str
) -> AnomalyExplanationDraft:
    """Validate the model response and reject unsupported numeric claims."""
    try:
        draft = AnomalyExplanationDraft.model_validate(parse_model_json(raw_text))
    except (ValidationError, GeminiInvalidResponseError) as error:
        raise GeminiInvalidResponseError(
            "Anomaly explanation failed schema validation"
        ) from error

    allowed = _numeric_claims(context.model_dump_json())
    text_values = [
        draft.summary,
        draft.impact,
        *draft.investigation_steps,
        *draft.limitations,
    ]
    text_values.extend(cause.cause for cause in draft.likely_causes)
    text_values.extend(cause.evidence for cause in draft.likely_causes)
    unsupported = (
        set().union(*(_numeric_claims(value) for value in text_values)) - allowed
    )
    unsupported -= {str(number) for number in range(1, 9)}
    if unsupported:
        raise GeminiInvalidResponseError(
            "Anomaly explanation contained unsupported numeric claims"
        )
    return draft


class AnomalyExplanationService:
    """Resolve one verified anomaly, build evidence, and optionally call Gemini."""

    def __init__(
        self,
        cache: RedisCache | None = None,
        user_scope: str = "shared",
        *,
        settings: Settings | None = None,
        client: InsightGenerator | None = None,
        detector: AnomalyDetectionService | None = None,
        explorer: CostExplorerService | None = None,
        enabled: bool | None = None,
    ) -> None:
        self._cache = cache
        self._user_scope = user_scope
        self._settings = settings
        self._client = client
        self._detector = detector or AnomalyDetectionService(
            cache=cache, user_scope=user_scope
        )
        self._explorer = explorer or CostExplorerService(
            cache=cache, user_scope=user_scope
        )
        self._enabled_override = enabled

    def _active_settings(self) -> Settings:
        return self._settings or get_settings()

    @property
    def enabled(self) -> bool:
        config = self._active_settings()
        if self._enabled_override is not None:
            return self._enabled_override
        return bool(
            config.ai_insight_enabled
            and (config.gemini_api_key or self._client is not None)
        )

    def _generator(self) -> InsightGenerator:
        if self._client is not None:
            return self._client
        config = self._active_settings()
        return GeminiInsightClient(
            api_key=config.gemini_api_key or "",
            model=config.ai_insight_model,
            timeout_seconds=config.ai_insight_timeout_seconds,
            max_output_tokens=config.ai_insight_max_output_tokens,
        )

    async def _resolve_anomaly(
        self, anomaly_id: str, request: AnomalyExplanationRequest
    ) -> Anomaly:
        query = AnomalyQuery(
            start_date=request.start_date,
            end_date=request.end_date,
            provider=request.provider,
            account_id=request.account_id,
            service=request.service,
            region=request.region,
            severity=request.severity,
            limit=1000,
        )
        result = await self._detector.detect(query)
        for anomaly in result.anomalies:
            if anomaly.id == anomaly_id:
                return anomaly
        raise AnomalyExplanationNotFoundError(
            "Anomaly was not found for the supplied filters"
        )

    def _cache_key(self, context: AnomalyInvestigationContext, model: str) -> str:
        payload = (
            f"{self._user_scope}|{context.anomaly.id}|{context.context_version}|"
            f"{PROMPT_VERSION}|{model}"
        )
        digest = hashlib.sha256(payload.encode()).hexdigest()[:20]
        return f"ai-anomaly-explanation:{self._user_scope}:{digest}"

    async def explain(
        self, anomaly_id: str, request: AnomalyExplanationRequest
    ) -> AnomalyExplanationResponse:
        anomaly = await self._resolve_anomaly(anomaly_id, request)
        baseline_start = date.fromisoformat(anomaly.baseline_period.split(":", 1)[0])
        records = await self._explorer.get_cost_records(
            baseline_start, anomaly.date, anomaly.provider
        )
        context = build_anomaly_context(anomaly, records)
        config = self._active_settings()
        model = config.ai_insight_model
        cache_key = self._cache_key(context, model)
        if self._cache is not None:
            cached = await self._cache.get_json(cache_key)
            if cached is not None:
                try:
                    return AnomalyExplanationResponse.model_validate(cached)
                except ValidationError:
                    logger.warning("anomaly_explanation_cache_invalid")

        if not self.enabled:
            return self._fallback(anomaly, context, ExplanationStatus.DISABLED, config)

        try:
            raw = await self._generator().generate_json(
                SYSTEM_PROMPT, context.model_dump_json()
            )
            draft = validate_anomaly_explanation(context, raw)
            response = AnomalyExplanationResponse(
                anomaly=anomaly,
                context=context,
                status=ExplanationStatus.READY,
                summary=draft.summary,
                likely_causes=draft.likely_causes,
                impact=draft.impact,
                investigation_steps=draft.investigation_steps,
                confidence=draft.confidence,
                limitations=draft.limitations,
                generated_at=datetime.now(UTC),
                model=model,
                prompt_version=PROMPT_VERSION,
            )
            if self._cache is not None:
                await self._cache.set_json(
                    cache_key, response, config.ai_insight_cache_ttl_seconds
                )
            return response
        except GeminiTimeoutError:
            status = ExplanationStatus.TIMEOUT
        except GeminiInvalidResponseError:
            status = ExplanationStatus.INVALID
        except (GeminiQuotaError, GeminiUnavailableError):
            status = ExplanationStatus.UNAVAILABLE
        except Exception:
            logger.exception("anomaly_explanation_unexpected_failure")
            status = ExplanationStatus.UNAVAILABLE
        return self._fallback(anomaly, context, status, config)

    @staticmethod
    def _fallback(
        anomaly: Anomaly,
        context: AnomalyInvestigationContext,
        status: ExplanationStatus,
        config: Settings,
    ) -> AnomalyExplanationResponse:
        return AnomalyExplanationResponse(
            anomaly=anomaly,
            context=context,
            status=status,
            prompt_version=PROMPT_VERSION,
            model=config.ai_insight_model,
            fallback_message=FALLBACK_MESSAGE,
        )
