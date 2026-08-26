"""Focused tests for deterministic cost events and Gemini insight validation."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.providers.base import CloudProvider
from app.providers.schemas import CostResponse, DailyCost, ServiceCost
from app.schemas.analytics import AnalyticsQuery, CostDriver
from app.schemas.cost_events import CostEvent, CostEventType
from app.schemas.dashboard import DashboardOverview, DashboardSummary
from app.schemas.insights import AIInsightStatus, InsightSeverity
from app.services.ai.context import SYSTEM_PROMPT, build_ai_context, build_user_prompt
from app.services.ai.events import is_significant_change, select_cost_events
from app.services.ai.exceptions import (
    GeminiInvalidResponseError,
    GeminiQuotaError,
    GeminiTimeoutError,
    GeminiUnavailableError,
)
from app.services.ai.gemini import parse_model_json
from app.services.ai.insights import AIInsightService, validate_ai_insight
from app.services.analytics.service import AnalyticsService
from app.services.dashboard import DashboardService


class _FakeGemini:
    def __init__(self, payload: str | Exception) -> None:
        self.payload = payload
        self.calls = 0
        self.prompts: list[tuple[str, str]] = []

    async def generate_json(self, system_prompt: str, user_prompt: str) -> str:
        self.calls += 1
        self.prompts.append((system_prompt, user_prompt))
        if isinstance(self.payload, Exception):
            raise self.payload
        return self.payload


class _FakeCache:
    def __init__(self) -> None:
        self.values: dict[str, dict] = {}
        self.reads = 0
        self.writes = 0

    async def get_json(self, key: str):  # noqa: ANN001
        self.reads += 1
        return self.values.get(key)

    async def set_json(
        self, key: str, value, ttl_seconds: int | None = None
    ):  # noqa: ANN001
        self.values[key] = value.model_dump(mode="json")
        self.writes += 1


def _event() -> CostEvent:
    return CostEvent(
        event_type=CostEventType.COST_INCREASE,
        provider="aws",
        service="EC2",
        current_cost=Decimal("842.50"),
        previous_cost=Decimal("620.20"),
        absolute_change=Decimal("222.30"),
        percentage_change=Decimal("35.84"),
        currency="USD",
        period_start=date(2026, 8, 1),
        period_end=date(2026, 8, 22),
    )


def _dashboard(
    *, absolute: str = "222.30", percentage: str = "35.84"
) -> DashboardSummary:
    change = Decimal(absolute)
    current = Decimal("842.50")
    previous = current - change
    return DashboardSummary(
        overview=DashboardOverview(
            total_cost=current,
            currency="USD",
            period_start=date(2026, 8, 1),
            period_end=date(2026, 8, 22),
            previous_period_cost=previous,
            absolute_change=change,
            percentage_change=Decimal(percentage),
        ),
        providers=[],
        services=[],
        trend=[],
        drivers=[
            CostDriver(
                category="service",
                name="EC2",
                provider="aws",
                current_cost=current,
                previous_cost=previous,
                absolute_change=change,
                percentage_change=Decimal(percentage),
            )
        ],
    )


def _settings(**overrides: object) -> Settings:
    values = {
        "JWT_SECRET_KEY": "test-secret",
        "AI_INSIGHT_ENABLED": True,
        "GEMINI_API_KEY": "test-key",
        "AI_INSIGHT_PERCENTAGE_THRESHOLD": "10.00",
        "AI_INSIGHT_ABSOLUTE_THRESHOLD": "50.00",
        "AI_INSIGHT_MAX_EVENTS": 3,
    }
    values.update(overrides)
    return Settings(**values)


def _query() -> AnalyticsQuery:
    return AnalyticsQuery(start_date=date(2026, 8, 1), end_date=date(2026, 8, 22))


VALID_MODEL_JSON = (
    '{"title": "EC2 spending increased significantly",'
    ' "summary": "ignored fabricated $999 savings",'
    ' "severity": "medium",'
    ' "likely_cause": "The available billing data confirms the increase'
    ' but does not identify the underlying resource-level cause.",'
    ' "recommended_action": "Review EC2 usage and resource-level'
    ' billing for the affected period."}'
)


def test_cost_event_uses_typed_model() -> None:
    event = _event()
    assert event.event_type is CostEventType.COST_INCREASE
    assert event.service == "EC2"
    with pytest.raises(ValidationError):
        CostEvent.model_validate({**event.model_dump(), "extra": "nope"})


def test_threshold_filtering_requires_percentage_or_absolute_change() -> None:
    assert is_significant_change(
        Decimal("222.30"),
        Decimal("35.84"),
        percentage_threshold=Decimal("10"),
        absolute_threshold=Decimal("50"),
    )
    assert not is_significant_change(
        Decimal("5.00"),
        Decimal("2.00"),
        percentage_threshold=Decimal("10"),
        absolute_threshold=Decimal("50"),
    )
    assert is_significant_change(
        Decimal("80.00"),
        Decimal("2.00"),
        percentage_threshold=Decimal("10"),
        absolute_threshold=Decimal("50"),
    )


def test_select_cost_events_keeps_only_meaningful_drivers() -> None:
    dashboard = _dashboard(absolute="5.00", percentage="2.00")
    events = select_cost_events(
        dashboard,
        percentage_threshold=Decimal("10"),
        absolute_threshold=Decimal("50"),
        max_events=3,
    )
    assert events == []

    events = select_cost_events(
        _dashboard(),
        percentage_threshold=Decimal("10"),
        absolute_threshold=Decimal("50"),
        max_events=3,
    )
    assert len(events) == 1
    assert events[0].service == "EC2"
    assert events[0].absolute_change == Decimal("222.30")


def test_ai_context_contains_facts_only() -> None:
    context = build_ai_context(_event())
    payload = context.model_dump()
    assert payload["service"] == "EC2"
    assert payload["cause_is_unknown"] is True
    dumped = build_user_prompt(context)
    assert "AWS_SECRET" not in dumped
    assert "token" not in dumped.lower()
    assert SYSTEM_PROMPT.startswith("You explain one deterministic")


def test_structured_response_uses_event_numbers_not_model_summary() -> None:
    insight = validate_ai_insight(_event(), VALID_MODEL_JSON)
    assert insight.absolute_change == Decimal("222.30")
    assert insight.percentage_change == Decimal("35.84")
    assert "999" not in insight.summary
    assert "222.30" in insight.summary
    assert insight.severity is InsightSeverity.MEDIUM


def test_malformed_ai_response_is_rejected() -> None:
    with pytest.raises(GeminiInvalidResponseError):
        parse_model_json("not-json")
    with pytest.raises(GeminiInvalidResponseError):
        validate_ai_insight(_event(), '{"title": "x"}')
    with pytest.raises(GeminiInvalidResponseError):
        validate_ai_insight(
            _event(),
            '{"title": "x", "summary": "y", "severity": "critical", '
            '"likely_cause": "z", "recommended_action": "w"}',
        )


@pytest.mark.asyncio
async def test_ai_disabled_skips_gemini() -> None:
    client = _FakeGemini(VALID_MODEL_JSON)
    service = AIInsightService(
        settings=_settings(AI_INSIGHT_ENABLED=False),
        client=client,
        enabled=False,
    )
    bundle = await service.generate(_query(), _dashboard())
    assert bundle.status is AIInsightStatus.DISABLED
    assert bundle.insights == []
    assert client.calls == 0


@pytest.mark.asyncio
async def test_gemini_failure_does_not_raise() -> None:
    service = AIInsightService(
        settings=_settings(),
        client=_FakeGemini(GeminiUnavailableError()),
        enabled=True,
    )
    bundle = await service.generate(_query(), _dashboard())
    assert bundle.status is AIInsightStatus.UNAVAILABLE
    assert bundle.insights == []
    assert "temporarily unavailable" in (bundle.message or "")


@pytest.mark.asyncio
async def test_gemini_timeout_and_quota_map_to_safe_status() -> None:
    timeout_service = AIInsightService(
        settings=_settings(),
        client=_FakeGemini(GeminiTimeoutError()),
        enabled=True,
    )
    quota_service = AIInsightService(
        settings=_settings(),
        client=_FakeGemini(GeminiQuotaError()),
        enabled=True,
    )
    timeout = await timeout_service.generate(_query(), _dashboard())
    quota = await quota_service.generate(_query(), _dashboard())
    assert timeout.status is AIInsightStatus.TIMEOUT
    assert quota.status is AIInsightStatus.QUOTA_EXCEEDED


@pytest.mark.asyncio
async def test_invalid_gemini_output_fails_gracefully() -> None:
    service = AIInsightService(
        settings=_settings(),
        client=_FakeGemini("<<<"),
        enabled=True,
    )
    bundle = await service.generate(_query(), _dashboard())
    assert bundle.status is AIInsightStatus.INVALID


@pytest.mark.asyncio
async def test_redis_cache_hit_skips_second_gemini_call() -> None:
    cache = _FakeCache()
    client = _FakeGemini(VALID_MODEL_JSON)
    service = AIInsightService(
        cache=cache,
        user_scope="user-1",
        settings=_settings(),
        client=client,
        enabled=True,
    )
    first = await service.generate(_query(), _dashboard())
    second = await service.generate(_query(), _dashboard())
    assert client.calls == 1
    assert cache.writes == 1
    assert first.insights[0].service == second.insights[0].service == "EC2"


@pytest.mark.asyncio
async def test_cache_miss_calls_gemini() -> None:
    client = _FakeGemini(VALID_MODEL_JSON)
    service = AIInsightService(
        cache=_FakeCache(),
        settings=_settings(),
        client=client,
        enabled=True,
    )
    bundle = await service.generate(_query(), _dashboard())
    assert client.calls == 1
    assert bundle.status is AIInsightStatus.READY
    assert bundle.insights[0].current_cost == Decimal("842.50")
    assert SYSTEM_PROMPT in client.prompts[0][0]
    assert (
        '"service":"EC2"' in client.prompts[0][1].replace(" ", "")
        or "EC2" in client.prompts[0][1]
    )


@pytest.mark.asyncio
async def test_include_ai_false_returns_pending_without_calling_gemini() -> None:
    client = _FakeGemini(VALID_MODEL_JSON)
    service = AIInsightService(
        settings=_settings(),
        client=client,
        enabled=True,
    )
    bundle = await service.generate(_query(), _dashboard(), include_ai=False)
    assert bundle.status is AIInsightStatus.PENDING
    assert bundle.insights == []
    assert client.calls == 0


@pytest.mark.asyncio
async def test_dashboard_keeps_deterministic_insights_when_ai_fails() -> None:
    class _Provider(CloudProvider):
        def __init__(self, name: str = "aws") -> None:
            self._name = name

        def provider_name(self) -> str:
            return self._name

        def authenticate(self) -> None:
            return None

        def validate_credentials(self) -> bool:
            return True

        async def get_costs(
            self, start_date: date, end_date: date, granularity: str
        ) -> CostResponse:
            previous = start_date < date(2026, 8, 1)
            total = 620 if previous else 842
            service_cost = 620 if previous else 842
            return CostResponse(
                provider=self._name,
                currency="USD",
                total_cost=total,
                date_range={
                    "start": start_date.isoformat(),
                    "end": end_date.isoformat(),
                    "granularity": granularity,
                },
                services=[ServiceCost(service_name="EC2", cost=service_cost)],
                daily_costs=[DailyCost(date=start_date, cost=total)],
            )

    analytics = AnalyticsService(provider_factory=lambda name: _Provider(name))
    service = DashboardService(
        analytics=analytics,
        ai_service=AIInsightService(
            settings=_settings(),
            client=_FakeGemini(GeminiUnavailableError()),
            enabled=True,
        ),
    )
    result = await service.insights(_query())
    assert result.insights
    assert result.insights[0].type.value == "cost_increase"
    assert result.ai_insights == []
    assert result.ai_status is AIInsightStatus.UNAVAILABLE
