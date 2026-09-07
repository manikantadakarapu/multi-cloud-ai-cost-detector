"""Bounded FinOps Copilot orchestration over verified application context."""

from __future__ import annotations

import hashlib
import re
from datetime import UTC, datetime

from pydantic import ValidationError

from app.core.cache import RedisCache
from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.schemas.copilot import (
    CopilotConfidence,
    CopilotContext,
    CopilotDraft,
    CopilotIntent,
    CopilotResponse,
    CopilotStatus,
)
from app.services.ai.copilot_context import CopilotContextService
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

logger = get_logger(__name__)
PROMPT_VERSION = "1.0"
FALLBACK_MESSAGE = (
    "I couldn't generate an AI explanation right now. The findings below are "
    "deterministic and verified by the application."
)
SUPPORTED_MESSAGE = (
    "I can help with cloud costs, anomalies, forecasts, optimization "
    "recommendations, budgets, and related FinOps analysis."
)

SYSTEM_PROMPT = f"""You are a bounded FinOps Copilot for a cloud cost dashboard.
Prompt version: {PROMPT_VERSION}.

The user message is JSON containing one question and only verified,
application-owned FinOps context. The context is authoritative. Answer the
question using only supplied context. Do not invent cost, savings, utilization,
forecast, anomaly, budget, provider, or recommendation values. Do not change
priorities, scores, statuses, forecasts, or budget values. Never claim that a
cloud resource, recommendation, alert, or budget action was executed. Clearly
separate verified facts, interpretation, and suggested investigation. State
missing data and uncertainty. Reference only supplied anomaly, recommendation,
and budget IDs.

Return JSON only with exactly these keys:
answer, key_findings, evidence, recommended_next_steps, limitations, confidence,
anomaly_ids, recommendation_ids, budget_ids.
"""


def _numeric_claims(value: str) -> set[str]:
    return set(re.findall(r"(?<![A-Za-z])\d+(?:\.\d+)?(?:%|x)?", value))


def _draft_text(draft: CopilotDraft) -> list[str]:
    return [
        draft.answer,
        *draft.key_findings,
        *draft.evidence,
        *draft.recommended_next_steps,
        *draft.limitations,
    ]


def validate_copilot_response(context: CopilotContext, raw_text: str) -> CopilotDraft:
    """Validate schema, references, numeric claims, and execution claims."""
    try:
        draft = CopilotDraft.model_validate(parse_model_json(raw_text))
    except (ValidationError, GeminiInvalidResponseError) as error:
        raise GeminiInvalidResponseError(
            "Copilot response failed schema validation"
        ) from error

    allowed = _numeric_claims(context.model_dump_json())
    unsupported = (
        set().union(*(_numeric_claims(value) for value in _draft_text(draft))) - allowed
    )
    unsupported -= {str(number) for number in range(1, 9)}
    if unsupported:
        raise GeminiInvalidResponseError(
            "Copilot response contained unsupported numerical claims"
        )

    anomaly_ids = {item.id for item in context.anomaly_context}
    recommendation_ids = {
        item.recommendation_id for item in context.optimization_context
    }
    budget_ids = {item.budget_id for item in context.budget_context}
    if not set(draft.anomaly_ids).issubset(anomaly_ids):
        raise GeminiInvalidResponseError("Copilot referenced an unavailable anomaly")
    if not set(draft.recommendation_ids).issubset(recommendation_ids):
        raise GeminiInvalidResponseError(
            "Copilot referenced an unavailable recommendation"
        )
    if not set(draft.budget_ids).issubset(budget_ids):
        raise GeminiInvalidResponseError("Copilot referenced an unavailable budget")

    combined = " ".join(_draft_text(draft)).lower()
    forbidden = (
        "was executed",
        "has been executed",
        "was implemented",
        "has been implemented",
        "we deleted",
        "we stopped",
        "we resized",
        "resources were changed",
    )
    if any(phrase in combined for phrase in forbidden):
        raise GeminiInvalidResponseError("Copilot claimed remediation was executed")
    return draft


class CopilotService:
    """Classify, retrieve, validate, and safely answer one user question."""

    def __init__(
        self,
        *,
        context_service: CopilotContextService,
        cache: RedisCache | None = None,
        user_scope: str = "shared",
        settings: Settings | None = None,
        client: InsightGenerator | None = None,
        enabled: bool | None = None,
    ) -> None:
        self._context_service = context_service
        self._cache = cache
        self._user_scope = user_scope
        self._settings = settings
        self._client = client
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

    def _cache_key(self, context: CopilotContext, model: str) -> str:
        payload = (
            f"{self._user_scope}|{context.model_dump_json()}|{PROMPT_VERSION}|{model}"
        )
        digest = hashlib.sha256(payload.encode()).hexdigest()[:20]
        return f"ai-finops-copilot:{self._user_scope}:{digest}"

    async def answer(self, question: str) -> CopilotResponse:
        context = await self._context_service.build(question)
        config = self._active_settings()
        model = config.ai_insight_model
        cache_key = self._cache_key(context, model)
        if self._cache is not None:
            cached = await self._cache.get_json(cache_key)
            if cached is not None:
                try:
                    return CopilotResponse.model_validate(cached)
                except ValidationError:
                    logger.warning("copilot_cache_invalid")

        if context.intent is CopilotIntent.UNSUPPORTED:
            return self._fallback(context, CopilotStatus.UNSUPPORTED, config)
        if not self.enabled:
            return self._fallback(context, CopilotStatus.DISABLED, config)

        try:
            raw = await self._generator().generate_json(
                SYSTEM_PROMPT, context.model_dump_json()
            )
            draft = validate_copilot_response(context, raw)
            response = CopilotResponse(
                **draft.model_dump(),
                status=CopilotStatus.READY,
                intent=context.intent,
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
            status = CopilotStatus.UNAVAILABLE
        except GeminiInvalidResponseError:
            status = CopilotStatus.INVALID
        except (GeminiQuotaError, GeminiUnavailableError):
            status = CopilotStatus.UNAVAILABLE
        except Exception:
            logger.exception("copilot_unexpected_failure")
            status = CopilotStatus.UNAVAILABLE
        return self._fallback(context, status, config)

    @staticmethod
    def _findings(context: CopilotContext) -> list[str]:
        findings: list[str] = []
        if context.cost_context is not None:
            cost = context.cost_context
            currency = cost.currency or "the available currency"
            findings.append(f"Current-period spend is {cost.total_cost} {currency}.")
            if cost.providers:
                provider = cost.providers[0]
                findings.append(
                    f"Largest provider contributor is {provider.provider} at "
                    f"{provider.cost} {provider.currency}."
                )
            if cost.change_percentage is not None:
                findings.append(
                    f"Spend changed by {cost.change_percentage}% versus the "
                    "available comparison period."
                )
        if context.anomaly_context:
            anomaly = context.anomaly_context[0]
            findings.append(
                f"Top deterministic anomaly is {anomaly.id} for {anomaly.service} "
                f"with {anomaly.severity.value} severity."
            )
        if context.forecast_context is not None:
            forecast = context.forecast_context
            if forecast.forecasts:
                findings.append(
                    f"Projected spend is {forecast.projected_spend} "
                    f"{forecast.currency or ''} for the available forecast horizon."
                )
            elif forecast.message:
                findings.append(forecast.message)
        if context.optimization_context:
            recommendation = context.optimization_context[0]
            findings.append(
                f"Highest-ranked recommendation is {recommendation.recommendation_id} "
                f"with {recommendation.priority.value} priority."
            )
        if context.budget_context:
            at_risk = [
                item
                for item in context.budget_context
                if item.actual_status.value in {"warning", "critical", "exceeded"}
                or item.forecast_status.value in {"warning", "critical", "exceeded"}
            ]
            findings.append(
                f"{len(at_risk)} of {len(context.budget_context)} configured budgets "
                "have a warning, critical, or exceeded status."
            )
        return findings or ["No verified findings were available for this question."]

    @classmethod
    def _fallback(
        cls, context: CopilotContext, status: CopilotStatus, config: Settings
    ) -> CopilotResponse:
        unsupported = context.intent is CopilotIntent.UNSUPPORTED
        findings = [SUPPORTED_MESSAGE] if unsupported else cls._findings(context)
        answer = SUPPORTED_MESSAGE if unsupported else FALLBACK_MESSAGE
        return CopilotResponse(
            answer=answer,
            key_findings=findings,
            evidence=[],
            recommended_next_steps=(
                []
                if unsupported
                else [
                    "Review the linked deterministic data in the relevant dashboard section."
                ]
            ),
            limitations=context.limitations,
            confidence=(
                CopilotConfidence.LOW if unsupported else CopilotConfidence.MEDIUM
            ),
            anomaly_ids=[item.id for item in context.anomaly_context],
            recommendation_ids=[
                item.recommendation_id for item in context.optimization_context
            ],
            budget_ids=[item.budget_id for item in context.budget_context],
            status=status,
            intent=context.intent,
            model=config.ai_insight_model,
            prompt_version=PROMPT_VERSION,
            fallback_message=None if unsupported else FALLBACK_MESSAGE,
        )
