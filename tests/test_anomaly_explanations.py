"""Tests for deterministic anomaly context and safe AI explanation handling."""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from httpx import AsyncClient

from app.api.routes.anomalies import get_anomaly_explanation_service
from app.core.config import Settings
from app.main import app
from app.schemas.anomaly import (
    Anomaly,
    AnomalyResponse,
    AnomalySeverity,
    DetectionMethod,
)
from app.schemas.anomaly_explanation import (
    AnomalyExplanationRequest,
    ExplanationStatus,
)
from app.schemas.explorer import CostRecord
from app.services.ai.anomaly_context import build_anomaly_context
from app.services.ai.anomaly_explanations import (
    AnomalyExplanationService,
    validate_anomaly_explanation,
)
from app.services.ai.exceptions import GeminiInvalidResponseError


class FakeClient:
    def __init__(self, payload: str):
        self.payload = payload
        self.calls = 0

    async def generate_json(self, system_prompt: str, user_prompt: str) -> str:
        self.calls += 1
        assert "credentials" not in user_prompt.lower()
        assert "1.0" in system_prompt
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


class FakeDetector:
    def __init__(self, anomaly):
        self.anomaly = anomaly

    async def detect(self, query):
        return AnomalyResponse(
            anomalies=[self.anomaly],
            total=1,
            limit=query.limit,
            offset=query.offset,
            summary={
                "total": 1,
                "high_or_critical": 1,
                "by_severity": {
                    level: int(level is AnomalySeverity.CRITICAL)
                    for level in AnomalySeverity
                },
            },
            trend=[],
            start_date=query.start_date,
            end_date=query.end_date,
            baseline_lookback_days=30,
            detector_version="1.0",
        )


def anomaly() -> Anomaly:
    return Anomaly(
        id="anomaly-1",
        provider="aws",
        account_id="account-1",
        account_name="Production",
        service="Compute",
        region="us-east-1",
        date=date(2026, 7, 8),
        actual_cost=Decimal("40.00"),
        expected_cost=Decimal("10.00"),
        deviation_amount=Decimal("30.00"),
        deviation_percentage=Decimal("300.00"),
        anomaly_score=Decimal("6.00"),
        severity=AnomalySeverity.CRITICAL,
        detection_method=DetectionMethod.MEDIAN_MAD,
        baseline_period="2026-07-01:2026-07-07",
        currency="USD",
        created_at=datetime.now(UTC),
    )


def records():
    result = []
    for index in range(7):
        day = date(2026, 7, 1) + timedelta(days=index)
        result.extend(
            [
                CostRecord(
                    date=day,
                    provider="aws",
                    account_id="account-1",
                    service="Compute",
                    region="us-east-1",
                    cost=Decimal("10.00"),
                ),
                CostRecord(
                    date=day,
                    provider="aws",
                    account_id="account-1",
                    service="Storage",
                    region="us-east-1",
                    cost=Decimal("2.00"),
                ),
            ]
        )
    result.extend(
        [
            CostRecord(
                date=date(2026, 7, 8),
                provider="aws",
                account_id="account-1",
                service="Compute",
                region="us-east-1",
                cost=Decimal("40.00"),
            ),
            CostRecord(
                date=date(2026, 7, 8),
                provider="aws",
                account_id="account-1",
                service="Storage",
                region="us-east-1",
                cost=Decimal("2.00"),
            ),
        ]
    )
    return result


def request() -> AnomalyExplanationRequest:
    return AnomalyExplanationRequest(
        start_date=date(2026, 7, 8), end_date=date(2026, 7, 8)
    )


def valid_json() -> str:
    return (
        '{"summary":"Spend increased significantly.",'
        '"likely_causes":[{"cause":"Compute is the primary contributor.",'
        '"evidence":"The verified evidence identifies Compute as the affected service.",'
        '"confidence":"high"}],'
        '"impact":"The anomaly is materially above its verified baseline.",'
        '"investigation_steps":["Review resource activity around the anomaly date."],'
        '"confidence":"high",'
        '"limitations":["Billing data does not identify the underlying resource."]}'
    )


def test_context_contains_verified_and_derived_evidence():
    context = build_anomaly_context(anomaly(), records())
    assert context.evidence[0].status.value == "verified"
    assert any(item.label == "Actual-to-baseline ratio" for item in context.evidence)
    assert context.service_changes[0].value == "Compute"
    assert context.daily_costs[-1].cost == Decimal("40.00")
    assert "credentials" not in context.model_dump_json().lower()


def test_numeric_guardrail_rejects_unsupported_claims():
    context = build_anomaly_context(anomaly(), records())
    with pytest.raises(GeminiInvalidResponseError):
        validate_anomaly_explanation(
            context, valid_json().replace("significantly", "increased by 999%")
        )


@pytest.mark.asyncio
async def test_explanation_calls_ai_on_miss_and_uses_cache_on_hit():
    client = FakeClient(valid_json())
    cache = FakeCache()
    service = AnomalyExplanationService(
        cache=cache,
        settings=Settings(ai_insight_enabled=True, gemini_api_key="test"),
        client=client,
        detector=FakeDetector(anomaly()),
        explorer=FakeExplorer(records()),
        enabled=True,
    )
    first = await service.explain("anomaly-1", request())
    second = await service.explain("anomaly-1", request())
    assert first.status is ExplanationStatus.READY
    assert second.status is ExplanationStatus.READY
    assert client.calls == 1
    assert cache.writes == 1


@pytest.mark.asyncio
async def test_ai_failure_returns_safe_fallback_without_losing_anomaly():
    service = AnomalyExplanationService(
        settings=Settings(ai_insight_enabled=True, gemini_api_key="test"),
        client=FakeClient("not-json"),
        detector=FakeDetector(anomaly()),
        explorer=FakeExplorer(records()),
        enabled=True,
    )
    result = await service.explain("anomaly-1", request())
    assert result.status is ExplanationStatus.INVALID
    assert result.anomaly.id == "anomaly-1"
    assert result.fallback_message


@pytest.mark.asyncio
async def test_explanation_endpoint_requires_authentication(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/anomalies/anomaly-1/explanation",
        json={"start_date": "2026-07-08", "end_date": "2026-07-08"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_explanation_endpoint_returns_verified_context(
    auth_client: AsyncClient,
) -> None:
    service = AnomalyExplanationService(
        settings=Settings(ai_insight_enabled=True, gemini_api_key="test"),
        client=FakeClient(valid_json()),
        detector=FakeDetector(anomaly()),
        explorer=FakeExplorer(records()),
        enabled=True,
    )
    app.dependency_overrides[get_anomaly_explanation_service] = lambda: service
    try:
        response = await auth_client.post(
            "/api/v1/anomalies/anomaly-1/explanation",
            json={"start_date": "2026-07-08", "end_date": "2026-07-08"},
        )
    finally:
        app.dependency_overrides.pop(get_anomaly_explanation_service, None)

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert body["context"]["evidence"]
