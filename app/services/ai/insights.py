"""Orchestrate Gemini explanations for selected deterministic cost events."""

from __future__ import annotations

import hashlib

from pydantic import ValidationError

from app.core.cache import RedisCache
from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.schemas.analytics import AnalyticsQuery
from app.schemas.cost_events import CostEvent
from app.schemas.dashboard import DashboardSummary
from app.schemas.insights import (
    AIInsight,
    AIInsightStatus,
    GeminiInsightDraft,
)
from app.services.ai.context import (
    SYSTEM_PROMPT,
    build_ai_context,
    build_user_prompt,
    deterministic_summary,
    deterministic_title,
)
from app.services.ai.events import select_cost_events
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

AI_STATUS_MESSAGES = {
    AIInsightStatus.UNAVAILABLE: (
        "Cost insight available. AI explanation temporarily unavailable."
    ),
    AIInsightStatus.QUOTA_EXCEEDED: (
        "Cost insight available. AI explanation temporarily unavailable."
    ),
    AIInsightStatus.TIMEOUT: (
        "Cost insight available. AI explanation temporarily unavailable."
    ),
    AIInsightStatus.INVALID: (
        "Cost insight available. AI explanation temporarily unavailable."
    ),
}


class AIInsightBundle:
    """Dashboard-safe AI result that never replaces deterministic insights."""

    def __init__(
        self,
        insights: list[AIInsight],
        status: AIInsightStatus,
        message: str | None = None,
    ) -> None:
        self.insights = insights
        self.status = status
        self.message = message


class AIInsightService:
    """Select cost events, call Gemini, validate output, and cache successful insights."""

    def __init__(
        self,
        cache: RedisCache | None = None,
        user_scope: str = "shared",
        *,
        settings: Settings | None = None,
        client: InsightGenerator | None = None,
        enabled: bool | None = None,
    ) -> None:
        self._cache = cache
        self._user_scope = user_scope
        self._settings = settings
        self._client = client
        self._enabled_override = enabled

    def _active_settings(self) -> Settings:
        return self._settings or get_settings()

    @property
    def enabled(self) -> bool:
        if self._enabled_override is not None:
            return self._enabled_override
        config = self._active_settings()
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

    async def generate(
        self,
        query: AnalyticsQuery,
        dashboard: DashboardSummary,
        *,
        include_ai: bool = True,
    ) -> AIInsightBundle:
        """Return Gemini explanations or a safe status. Never raises to callers."""
        config = self._active_settings()
        if not self.enabled:
            if self._enabled_override is False or not config.ai_insight_enabled:
                return AIInsightBundle([], AIInsightStatus.DISABLED)
            return AIInsightBundle(
                [],
                AIInsightStatus.UNAVAILABLE,
                AI_STATUS_MESSAGES[AIInsightStatus.UNAVAILABLE],
            )

        events = select_cost_events(
            dashboard,
            percentage_threshold=config.ai_insight_percentage_threshold,
            absolute_threshold=config.ai_insight_absolute_threshold,
            max_events=config.ai_insight_max_events,
        )
        if not events:
            return AIInsightBundle([], AIInsightStatus.EMPTY)
        if not include_ai:
            return AIInsightBundle([], AIInsightStatus.PENDING)

        insights: list[AIInsight] = []
        for event in events:
            try:
                insight = await self._explain_event(event, config)
            except GeminiQuotaError:
                return self._partial_or_status(insights, AIInsightStatus.QUOTA_EXCEEDED)
            except GeminiTimeoutError:
                return self._partial_or_status(insights, AIInsightStatus.TIMEOUT)
            except GeminiInvalidResponseError:
                return self._partial_or_status(insights, AIInsightStatus.INVALID)
            except GeminiUnavailableError:
                return self._partial_or_status(insights, AIInsightStatus.UNAVAILABLE)
            except Exception:
                logger.exception("ai_insight_unexpected_failure")
                return self._partial_or_status(insights, AIInsightStatus.UNAVAILABLE)
            insights.append(insight)

        return AIInsightBundle(insights, AIInsightStatus.READY)

    def _partial_or_status(
        self, insights: list[AIInsight], status: AIInsightStatus
    ) -> AIInsightBundle:
        if insights:
            return AIInsightBundle(
                insights, AIInsightStatus.READY, AI_STATUS_MESSAGES[status]
            )
        return AIInsightBundle([], status, AI_STATUS_MESSAGES[status])

    async def _explain_event(self, event: CostEvent, config: Settings) -> AIInsight:
        cache_key = self._cache_key(event, config.ai_insight_model)
        cached = await self._get_cached(cache_key)
        if cached is not None:
            return cached

        context = build_ai_context(event)
        raw = await self._generator().generate_json(
            SYSTEM_PROMPT, build_user_prompt(context)
        )
        insight = validate_ai_insight(event, raw)
        if self._cache is not None:
            await self._cache.set_json(
                cache_key,
                insight,
                ttl_seconds=config.ai_insight_cache_ttl_seconds,
            )
        return insight

    def _cache_key(self, event: CostEvent, model: str) -> str:
        payload = event.model_dump_json()
        event_hash = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
        provider = event.provider or "all"
        service = event.service or "total"
        return (
            f"ai-insight:{self._user_scope}:{provider}:{service}:"
            f"{event.period_start}:{event.period_end}:{model}:{event_hash}"
        )

    async def _get_cached(self, key: str) -> AIInsight | None:
        if self._cache is None:
            return None
        payload = await self._cache.get_json(key)
        if payload is None:
            return None
        try:
            return AIInsight.model_validate(payload)
        except ValidationError:
            logger.warning("ai_insight_cache_invalid")
            return None


def validate_ai_insight(event: CostEvent, raw_text: str) -> AIInsight:
    """Validate model JSON and attach measured cost values from the event."""
    payload = parse_model_json(raw_text)
    try:
        draft = GeminiInsightDraft.model_validate(payload)
    except ValidationError as error:
        raise GeminiInvalidResponseError(
            "Gemini response failed schema validation"
        ) from error

    title = draft.title.strip() or deterministic_title(event)
    return AIInsight(
        title=title,
        summary=deterministic_summary(event),
        severity=draft.severity,
        likely_cause=draft.likely_cause.strip(),
        recommended_action=draft.recommended_action.strip(),
        event_type=event.event_type,
        provider=event.provider,
        service=event.service,
        current_cost=event.current_cost,
        previous_cost=event.previous_cost,
        absolute_change=event.absolute_change,
        percentage_change=event.percentage_change,
        currency=event.currency,
        period_start=event.period_start,
        period_end=event.period_end,
        source="gemini",
    )
