"""Focused tests for evidence-constrained AI FinOps recommendation advice."""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest
from httpx import AsyncClient

from app.api.routes.optimization import get_optimization_advisor_service
from app.core.config import Settings
from app.main import app
from app.schemas.anomaly import Anomaly, AnomalySeverity, DetectionMethod
from app.schemas.explorer import CostRecord
from app.schemas.optimization import (
    Recommendation,
    RecommendationCategory,
    RecommendationConfidence,
    RecommendationEvidence,
    RecommendationPriority,
    RecommendationStatus,
)
from app.schemas.optimization_advisor import (
    AdvisorStatus,
    OptimizationAdvisorRequest,
)
from app.services.ai.exceptions import GeminiInvalidResponseError
from app.services.ai.optimization_advisor import (
    OptimizationAdvisorService,
    validate_optimization_advisor,
)
from app.services.ai.optimization_advisor_context import (
    build_optimization_advisor_context,
)


class FakeClient:
    def __init__(self, payload: str):
        self.payload = payload
        self.calls = 0

    async def generate_json(self, system_prompt: str, user_prompt: str) -> str:
        self.calls += 1
        assert "do not invent" in system_prompt.lower()
        assert "account-1" in user_prompt
        return self.payload


class FakeCache:
    def __init__(self):
        self.values = {}
        self.writes = 0

    async def get_json(self, key):
        return self.values.get(key)

    async def set_json(self, key, value, ttl_seconds=None):
        self.writes += 1
        self.values[key] = value.model_dump(mode="json")


class FakeExplorer:
    def __init__(self, records):
        self.records = records

    async def get_cost_records(self, start_date, end_date, provider=None):
        return self.records


class FakeOptimization:
    def __init__(self, recommendation):
        self.recommendation = recommendation

    async def get_recommendation(self, recommendation_id, query):
        return (
            self.recommendation
            if recommendation_id == self.recommendation.recommendation_id
            else None
        )


class FakeDetector:
    def __init__(self, anomaly):
        self.anomaly = anomaly

    async def detect(self, query):
        return SimpleNamespace(anomalies=[self.anomaly])


class FakeForecasting:
    async def forecast(self, query):
        return SimpleNamespace(status="insufficient_data", forecasts=[])


def recommendation() -> Recommendation:
    return Recommendation(
        recommendation_id="recommendation-1",
        provider="aws",
        account_id="account-1",
        service="Compute",
        region="us-east-1",
        category=RecommendationCategory.COST_GROWTH,
        title="Investigate sustained Compute cost growth",
        description="Review the sustained cost growth pattern in Cost Explorer.",
        rationale="Recent cost is above the earlier comparable period.",
        evidence=[
            RecommendationEvidence(
                label="Recent daily average",
                value="25.00 USD",
                source="normalized Cost Explorer records",
            ),
            RecommendationEvidence(
                label="Sustained change",
                value="150.00%",
                source="deterministic comparison",
            ),
        ],
        priority=RecommendationPriority.HIGH,
        current_cost=Decimal("750.00"),
        estimated_monthly_savings=Decimal("450.00"),
        estimated_annual_savings=Decimal("5400.00"),
        savings_currency="USD",
        savings_explanation=(
            "Scenario estimate: 225.00–450.00 USD/month if spend returns toward baseline."
        ),
        confidence=RecommendationConfidence.HIGH,
        status=RecommendationStatus.NEW,
        detection_method="sustained_cost_growth",
        rule_version="optimization-rules-v1",
        created_at=datetime.now(UTC),
    )


def anomaly() -> Anomaly:
    return Anomaly(
        id="anomaly-1",
        provider="aws",
        account_id="account-1",
        account_name="Production",
        service="Compute",
        region="us-east-1",
        date=date(2026, 8, 30),
        actual_cost=Decimal("40.00"),
        expected_cost=Decimal("10.00"),
        deviation_amount=Decimal("30.00"),
        deviation_percentage=Decimal("300.00"),
        anomaly_score=Decimal("6.00"),
        severity=AnomalySeverity.CRITICAL,
        detection_method=DetectionMethod.MEDIAN_MAD,
        baseline_period="2026-08-20:2026-08-29",
        currency="USD",
        created_at=datetime.now(UTC),
    )


def records():
    return [
        CostRecord(
            date=date(2026, 8, 1) + timedelta(days=index),
            provider="aws",
            account_id="account-1",
            service="Compute",
            region="us-east-1",
            cost=Decimal("25.00"),
            currency="USD",
        )
        for index in range(30)
    ]


def request() -> OptimizationAdvisorRequest:
    return OptimizationAdvisorRequest(
        start_date=date(2026, 8, 1), end_date=date(2026, 8, 30)
    )


def valid_json() -> str:
    return (
        '{"summary":"Compute costs are above the earlier baseline.",'
        '"why_it_matters":"The verified recommendation identifies sustained growth.",'
        '"evidence_summary":"The supplied evidence reports 25.00 USD daily average '
        'and 150.00% change.",'
        '"tradeoffs":["Review performance and resilience before changes."],'
        '"suggested_next_steps":["Review the service in Cost Explorer."],'
        '"expected_impact":"The deterministic scenario estimate remains authoritative.",'
        '"confidence":"high",'
        '"limitations":["Utilization telemetry is not available."]}'
    )


def service(client=None, cache=None, enabled=True):
    return OptimizationAdvisorService(
        cache=cache,
        settings=Settings(ai_insight_enabled=True, gemini_api_key="test"),
        client=client or FakeClient(valid_json()),
        optimization=FakeOptimization(recommendation()),
        explorer=FakeExplorer(records()),
        detector=FakeDetector(anomaly()),
        forecasting=FakeForecasting(),
        enabled=enabled,
    )


def test_context_contains_recommendation_and_verified_cost_data():
    context = build_optimization_advisor_context(
        recommendation(), records(), [anomaly()]
    )
    assert context.recommendation.recommendation_id == "recommendation-1"
    assert context.historical_cost == Decimal("750.00")
    assert context.cost_trend[-1].cost == Decimal("25.00")
    assert context.related_anomalies[0].id == "anomaly-1"
    assert "credentials" not in context.model_dump_json().lower()


def test_numeric_guardrail_rejects_unsupported_claims():
    context = build_optimization_advisor_context(
        recommendation(), records(), [anomaly()]
    )
    with pytest.raises(GeminiInvalidResponseError):
        validate_optimization_advisor(context, valid_json().replace("25.00", "999.00"))


def test_execution_claim_guardrail_rejects_completed_action_language():
    context = build_optimization_advisor_context(
        recommendation(), records(), [anomaly()]
    )
    with pytest.raises(GeminiInvalidResponseError):
        validate_optimization_advisor(
            context,
            valid_json().replace(
                "The deterministic scenario estimate remains authoritative.",
                "The resize was executed successfully.",
            ),
        )


@pytest.mark.asyncio
async def test_advisor_calls_ai_once_and_uses_versioned_cache():
    client = FakeClient(valid_json())
    cache = FakeCache()
    advisor = service(client=client, cache=cache)
    first = await advisor.explain("recommendation-1", request())
    second = await advisor.explain("recommendation-1", request())
    assert first.status is AdvisorStatus.READY
    assert second.status is AdvisorStatus.READY
    assert client.calls == 1
    assert cache.writes == 1
    assert any("ai-optimization-advisor" in key for key in cache.values)


@pytest.mark.asyncio
async def test_invalid_ai_response_returns_deterministic_fallback():
    result = await service(client=FakeClient("not-json")).explain(
        "recommendation-1", request()
    )
    assert result.status is AdvisorStatus.INVALID
    assert result.recommendation.estimated_monthly_savings == Decimal("450.00")
    assert result.fallback_message


@pytest.mark.asyncio
async def test_disabled_advisor_preserves_deterministic_recommendation():
    result = await service(enabled=False).explain("recommendation-1", request())
    assert result.status is AdvisorStatus.DISABLED
    assert result.recommendation.priority is RecommendationPriority.HIGH


@pytest.mark.asyncio
async def test_missing_cost_data_returns_safe_insufficient_data_fallback():
    advisor = OptimizationAdvisorService(
        settings=Settings(ai_insight_enabled=True, gemini_api_key="test"),
        client=FakeClient(valid_json()),
        optimization=FakeOptimization(recommendation()),
        explorer=FakeExplorer([]),
        detector=FakeDetector(anomaly()),
        forecasting=FakeForecasting(),
        enabled=True,
    )
    result = await advisor.explain("recommendation-1", request())
    assert result.status is AdvisorStatus.INSUFFICIENT_DATA
    assert result.recommendation.recommendation_id == "recommendation-1"


@pytest.mark.asyncio
async def test_advisor_endpoint_requires_authentication(client: AsyncClient):
    response = await client.post(
        "/api/v1/optimization/recommendations/recommendation-1/advisor",
        json={"start_date": "2026-08-01", "end_date": "2026-08-30"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_advisor_endpoint_returns_structured_response(auth_client: AsyncClient):
    advisor = service()
    app.dependency_overrides[get_optimization_advisor_service] = lambda: advisor
    try:
        response = await auth_client.post(
            "/api/v1/optimization/recommendations/recommendation-1/advisor",
            json={"start_date": "2026-08-01", "end_date": "2026-08-30"},
        )
    finally:
        app.dependency_overrides.pop(get_optimization_advisor_service, None)
    assert response.status_code == 200
    assert response.json()["recommendation"]["recommendation_id"] == "recommendation-1"
    assert response.json()["status"] == "ready"
