"""On-demand, evidence-constrained AI explanations for FinOps recommendations."""

from __future__ import annotations

import hashlib
import re
from datetime import UTC, datetime

from pydantic import ValidationError

from app.core.cache import RedisCache
from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.schemas.anomaly import AnomalyQuery
from app.schemas.forecast import ForecastDimension, ForecastQuery, ForecastStatus
from app.schemas.optimization import OptimizationQuery
from app.schemas.optimization_advisor import (
    AdvisorConfidence,
    AdvisorStatus,
    OptimizationAdvisorContext,
    OptimizationAdvisorDraft,
    OptimizationAdvisorRequest,
    OptimizationAdvisorResponse,
)
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
from app.services.ai.optimization_advisor_context import (
    build_optimization_advisor_context,
)
from app.services.anomaly import AnomalyDetectionService
from app.services.explorer.service import CostExplorerService
from app.services.forecasting import ForecastingService
from app.services.optimization import OptimizationService

logger = get_logger(__name__)
PROMPT_VERSION = "1.0"
FALLBACK_MESSAGE = (
    "AI advice is currently unavailable. Review the deterministic recommendation, "
    "verified evidence, and Cost Explorer data before taking action."
)

SYSTEM_PROMPT = f"""You are an AI FinOps advisor for a cost optimization dashboard.
Prompt version: {PROMPT_VERSION}.

The user message is JSON containing one deterministic recommendation and verified
application-owned context. That context is authoritative. Explain only the supplied
recommendation; never create another recommendation or change its priority, status,
savings, confidence, or evidence. Do not invent facts, resources, utilization,
pricing, provider data, or numerical values. Never claim remediation was executed.
Clearly distinguish verified evidence from interpretation and suggested investigation.
State uncertainty and missing data when present. Discuss trade-offs cautiously and
do not present destructive actions as approved.

Return JSON only with exactly these keys:
summary, why_it_matters, evidence_summary, tradeoffs, suggested_next_steps,
expected_impact, confidence, limitations.
"""


def _numeric_claims(value: str) -> set[str]:
    return set(re.findall(r"(?<![A-Za-z])\d+(?:\.\d+)?(?:%|x)?", value))


def _draft_text(draft: OptimizationAdvisorDraft) -> list[str]:
    return [
        draft.summary,
        draft.why_it_matters,
        draft.evidence_summary,
        draft.expected_impact,
        *draft.tradeoffs,
        *draft.suggested_next_steps,
        *draft.limitations,
    ]


def validate_optimization_advisor(
    context: OptimizationAdvisorContext, raw_text: str
) -> OptimizationAdvisorDraft:
    """Validate schema, numerical claims, and prohibited execution claims."""
    try:
        draft = OptimizationAdvisorDraft.model_validate(parse_model_json(raw_text))
    except (ValidationError, GeminiInvalidResponseError) as error:
        raise GeminiInvalidResponseError(
            "FinOps advisor response failed schema validation"
        ) from error

    context_json = context.model_dump_json()
    allowed = _numeric_claims(context_json)
    unsupported = (
        set().union(*(_numeric_claims(value) for value in _draft_text(draft))) - allowed
    )
    unsupported -= {str(number) for number in range(1, 9)}
    if unsupported:
        raise GeminiInvalidResponseError(
            "FinOps advisor contained unsupported numerical claims"
        )

    combined = " ".join(_draft_text(draft)).lower()
    forbidden = (
        "was executed",
        "has been executed",
        "was implemented",
        "has been implemented",
        "we deleted",
        "we stopped",
        "we resized",
    )
    if any(phrase in combined for phrase in forbidden):
        raise GeminiInvalidResponseError(
            "FinOps advisor claimed remediation was executed"
        )
    return draft


class RecommendationNotFoundError(Exception):
    """Raised when a recommendation cannot be resolved for the supplied period."""


class OptimizationAdvisorService:
    """Build deterministic context, call Gemini on demand, and return safe output."""

    def __init__(
        self,
        cache: RedisCache | None = None,
        user_scope: str = "shared",
        *,
        settings: Settings | None = None,
        client: InsightGenerator | None = None,
        optimization: OptimizationService | None = None,
        explorer: CostExplorerService | None = None,
        detector: AnomalyDetectionService | None = None,
        forecasting: ForecastingService | None = None,
        enabled: bool | None = None,
    ) -> None:
        self._cache = cache
        self._user_scope = user_scope
        self._settings = settings
        self._client = client
        self._optimization = optimization or OptimizationService(
            cache=cache, user_scope=user_scope
        )
        self._explorer = explorer or CostExplorerService(
            cache=cache, user_scope=user_scope
        )
        self._detector = detector or AnomalyDetectionService(
            cache=cache, user_scope=user_scope
        )
        self._forecasting = forecasting or ForecastingService(
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

    def _cache_key(self, context: OptimizationAdvisorContext, model: str) -> str:
        payload = (
            f"{self._user_scope}|{context.model_dump_json()}|{PROMPT_VERSION}|{model}"
        )
        digest = hashlib.sha256(payload.encode()).hexdigest()[:20]
        return f"ai-optimization-advisor:{self._user_scope}:{digest}"

    async def _context(
        self, recommendation_id: str, request: OptimizationAdvisorRequest
    ) -> OptimizationAdvisorContext:
        query = OptimizationQuery(
            start_date=request.start_date,
            end_date=request.end_date,
            limit=100,
        )
        recommendation = await self._optimization.get_recommendation(
            recommendation_id, query
        )
        if recommendation is None:
            raise RecommendationNotFoundError(
                "Recommendation not found for the supplied period"
            )

        records = await self._explorer.get_cost_records(
            request.start_date, request.end_date, recommendation.provider
        )
        anomaly_result = await self._detector.detect(
            AnomalyQuery(
                start_date=request.start_date,
                end_date=request.end_date,
                provider=recommendation.provider,
                account_id=recommendation.account_id,
                service=recommendation.service,
                region=recommendation.region,
                limit=100,
            )
        )
        forecast_result = await self._forecasting.forecast(
            ForecastQuery(
                start_date=request.start_date,
                end_date=request.end_date,
                horizon_days=7,
                provider=recommendation.provider,
                account_id=recommendation.account_id,
                service=recommendation.service,
                region=recommendation.region,
                dimension=ForecastDimension.SERVICE,
            )
        )
        forecast = (
            forecast_result.forecasts[0]
            if forecast_result.status is ForecastStatus.READY
            and forecast_result.forecasts
            else None
        )
        return build_optimization_advisor_context(
            recommendation,
            records,
            anomaly_result.anomalies,
            forecast,
        )

    async def explain(
        self, recommendation_id: str, request: OptimizationAdvisorRequest
    ) -> OptimizationAdvisorResponse:
        context = await self._context(recommendation_id, request)
        config = self._active_settings()
        model = config.ai_insight_model
        cache_key = self._cache_key(context, model)
        if self._cache is not None:
            cached = await self._cache.get_json(cache_key)
            if cached is not None:
                try:
                    return OptimizationAdvisorResponse.model_validate(cached)
                except ValidationError:
                    logger.warning("optimization_advisor_cache_invalid")

        if context.missing_data and not context.cost_trend:
            return self._fallback(context, AdvisorStatus.INSUFFICIENT_DATA, config)
        if not self.enabled:
            return self._fallback(context, AdvisorStatus.DISABLED, config)

        try:
            raw = await self._generator().generate_json(
                SYSTEM_PROMPT, context.model_dump_json()
            )
            draft = validate_optimization_advisor(context, raw)
            response = OptimizationAdvisorResponse(
                recommendation=context.recommendation,
                context=context,
                status=AdvisorStatus.READY,
                summary=draft.summary,
                why_it_matters=draft.why_it_matters,
                evidence_summary=draft.evidence_summary,
                tradeoffs=draft.tradeoffs,
                suggested_next_steps=draft.suggested_next_steps,
                expected_impact=draft.expected_impact,
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
            current_status = AdvisorStatus.TIMEOUT
        except GeminiInvalidResponseError:
            current_status = AdvisorStatus.INVALID
        except (GeminiQuotaError, GeminiUnavailableError):
            current_status = AdvisorStatus.UNAVAILABLE
        except Exception:
            logger.exception("optimization_advisor_unexpected_failure")
            current_status = AdvisorStatus.UNAVAILABLE
        return self._fallback(context, current_status, config)

    @staticmethod
    def _fallback(
        context: OptimizationAdvisorContext,
        status: AdvisorStatus,
        config: Settings,
    ) -> OptimizationAdvisorResponse:
        recommendation = context.recommendation
        savings = recommendation.savings_explanation
        missing = (
            " ".join(context.missing_data) if context.missing_data else "None reported."
        )
        return OptimizationAdvisorResponse(
            recommendation=recommendation,
            context=context,
            status=status,
            summary=recommendation.description,
            why_it_matters=recommendation.rationale,
            evidence_summary="; ".join(
                f"{item.label}: {item.value}" for item in recommendation.evidence
            ),
            tradeoffs=[
                "Review usage and architecture context before changing resources.",
                "A cost reduction may trade off performance, resilience, or delivery speed.",
            ],
            suggested_next_steps=[
                "Review the linked evidence in Cost Explorer.",
                "Confirm ownership and usage with the responsible engineering team.",
            ],
            expected_impact=savings,
            confidence=AdvisorConfidence.MEDIUM,
            limitations=[missing],
            model=config.ai_insight_model,
            prompt_version=PROMPT_VERSION,
            fallback_message=FALLBACK_MESSAGE,
        )
