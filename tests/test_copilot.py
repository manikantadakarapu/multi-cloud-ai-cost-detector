from __future__ import annotations

import json
from datetime import date

import pytest
from httpx import AsyncClient

from app.core.cache import RedisCache
from app.schemas.copilot import (
    CopilotContext,
    CopilotIntent,
    CopilotStatus,
    CopilotTimeRange,
)
from app.services.ai.copilot import CopilotService, validate_copilot_response
from app.services.ai.copilot_context import classify_question
from app.services.ai.exceptions import (
    GeminiInvalidResponseError,
    GeminiUnavailableError,
)


class FakeGenerator:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.calls = 0
        self.prompts = []

    async def generate_json(self, system_prompt: str, user_prompt: str) -> str:
        self.calls += 1
        self.prompts.append((system_prompt, user_prompt))
        if self.error:
            raise self.error
        return self.response


class FakeContextService:
    def __init__(self, context: CopilotContext):
        self.context = context

    async def build(self, question: str) -> CopilotContext:
        return self.context.model_copy(update={"question": question})


class FakeCache(RedisCache):
    def __init__(self):
        super().__init__(redis_url="redis://unused")
        self.values = {}
        self.writes = 0

    async def get_json(self, key):
        return self.values.get(key)

    async def set_json(self, key, value, ttl_seconds=None):
        self.values[key] = value.model_dump(mode="json")
        self.writes += 1


def context(intent: CopilotIntent = CopilotIntent.COST) -> CopilotContext:
    return CopilotContext(
        context_version="test-v1",
        question="How much did I spend?",
        intent=intent,
        time_range=CopilotTimeRange(
            label="Current month to date",
            start_date=date(2026, 9, 1),
            end_date=date(2026, 9, 7),
        ),
        limitations=[],
    )


VALID_RESPONSE = json.dumps(
    {
        "answer": "Verified cost data is available for review.",
        "key_findings": ["The current period data was retrieved from the application."],
        "evidence": [],
        "recommended_next_steps": ["Review Cost Explorer for the detailed breakdown."],
        "limitations": [],
        "confidence": "medium",
        "anomaly_ids": [],
        "recommendation_ids": [],
        "budget_ids": [],
    }
)


@pytest.mark.parametrize(
    ("question", "expected"),
    [
        ("How much did I spend this month?", CopilotIntent.COST),
        ("What anomalies should I investigate?", CopilotIntent.ANOMALY),
        ("What is my forecasted spend?", CopilotIntent.FORECAST),
        ("What are my optimization opportunities?", CopilotIntent.OPTIMIZATION),
        ("Which budgets are at risk?", CopilotIntent.BUDGET),
        (
            "Why is AWS over budget and which anomaly contributed?",
            CopilotIntent.CROSS_DOMAIN,
        ),
        ("What is the weather today?", CopilotIntent.UNSUPPORTED),
    ],
)
def test_question_classifier_is_bounded(question, expected):
    assert classify_question(question) is expected


@pytest.mark.asyncio
async def test_copilot_returns_structured_ai_response_and_scoped_cache():
    cache = FakeCache()
    generator = FakeGenerator(VALID_RESPONSE)
    service = CopilotService(
        context_service=FakeContextService(context()),
        cache=cache,
        user_scope="user-1",
        client=generator,
        enabled=True,
    )
    first = await service.answer("How much did I spend?")
    second = await service.answer("How much did I spend?")
    assert first.status is CopilotStatus.READY
    assert first.intent is CopilotIntent.COST
    assert second.answer == first.answer
    assert generator.calls == 1
    assert cache.writes == 1
    assert "Do not invent" in generator.prompts[0][0]


@pytest.mark.asyncio
async def test_unsupported_question_never_calls_ai():
    generator = FakeGenerator(VALID_RESPONSE)
    service = CopilotService(
        context_service=FakeContextService(context(CopilotIntent.UNSUPPORTED)),
        client=generator,
        enabled=True,
    )
    response = await service.answer("What is the weather today?")
    assert response.status is CopilotStatus.UNSUPPORTED
    assert response.fallback_message is None
    assert generator.calls == 0


@pytest.mark.asyncio
async def test_gemini_failure_returns_verified_fallback():
    service = CopilotService(
        context_service=FakeContextService(context()),
        client=FakeGenerator(error=GeminiUnavailableError()),
        enabled=True,
    )
    response = await service.answer("How much did I spend?")
    assert response.status is CopilotStatus.UNAVAILABLE
    assert response.fallback_message
    assert response.key_findings


def test_numeric_guardrail_rejects_hallucinated_numbers():
    with pytest.raises(GeminiInvalidResponseError):
        validate_copilot_response(
            context(),
            VALID_RESPONSE.replace(
                "Verified cost data is available",
                "Verified cost data increased by 9999%",
            ),
        )


def test_reference_guardrail_rejects_unknown_ids():
    invalid = json.loads(VALID_RESPONSE)
    invalid["anomaly_ids"] = ["not-authorized"]
    with pytest.raises(GeminiInvalidResponseError):
        validate_copilot_response(context(), json.dumps(invalid))


@pytest.mark.asyncio
async def test_copilot_api_requires_authentication(client: AsyncClient):
    response = await client.post(
        "/api/v1/copilot/query", json={"question": "How much did I spend?"}
    )
    assert response.status_code == 401
