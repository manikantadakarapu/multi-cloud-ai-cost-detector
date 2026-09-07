"""Focused tests for deterministic cost alert configuration and evaluation."""

import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest
from httpx import AsyncClient

from app.alerts.models import Alert
from app.alerts.notifications import NotificationError
from app.alerts.service import AlertEvaluationService
from app.schemas.alerts import AlertCreate, AlertSeverity, AlertType
from app.schemas.anomaly import AnomalyQuery
from app.schemas.explorer import CostRecord
from app.schemas.forecast import ForecastStatus


class FakeRepo:
    def __init__(self, alerts):
        self.alerts = alerts
        self.saved = 0

    async def list_for_user(self, user_id):
        return self.alerts

    async def save(self, alert):
        self.saved += 1
        return alert


class FakeExplorer:
    def __init__(self, records):
        self.records = records

    async def get_cost_records(self, start_date, end_date, provider=None):
        return self.records


class FakeDetector:
    def __init__(self, anomalies):
        self.anomalies = anomalies

    async def detect(self, query: AnomalyQuery):
        return SimpleNamespace(anomalies=self.anomalies)


class FakeForecasting:
    def __init__(self, status=ForecastStatus.INSUFFICIENT_DATA, value=Decimal("0")):
        self.status = status
        self.value = value

    async def forecast(self, query):
        return SimpleNamespace(
            status=self.status,
            forecasts=(
                [SimpleNamespace(projected_cost=self.value, currency="USD")]
                if self.status is ForecastStatus.READY
                else []
            ),
        )


class FakeNotifier:
    def __init__(self, failure=False):
        self.events = []
        self.failure = failure

    async def send(self, recipient, alert, subject_value, reason, details):
        if self.failure:
            raise NotificationError("SMTP unavailable")
        self.events.append((recipient, alert.name, subject_value, reason))


def alert(alert_type=AlertType.COST_THRESHOLD, **overrides):
    values = {
        "id": uuid.uuid4(),
        "user_id": uuid.uuid4(),
        "name": "Daily AWS cost",
        "alert_type": alert_type.value,
        "provider": "aws",
        "account_id": "account-1",
        "service": "Compute",
        "region": "us-east-1",
        "threshold": Decimal("100"),
        "percentage": None,
        "severity": AlertSeverity.HIGH.value,
        "enabled": True,
        "cooldown_minutes": 360,
        "last_triggered_at": None,
        "created_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC),
    }
    values.update(overrides)
    return Alert(**values)


def records(values):
    return [
        CostRecord(
            date=date(2026, 9, 1) + timedelta(days=index),
            provider="aws",
            account_id="account-1",
            service="Compute",
            region="us-east-1",
            cost=Decimal(str(value)),
            currency="USD",
        )
        for index, value in enumerate(values)
    ]


def evaluator(alert_item, records_list, notifier=None, detector=None, forecasting=None):
    return AlertEvaluationService(
        repo=FakeRepo([alert_item]),
        explorer=FakeExplorer(records_list),
        detector=detector or FakeDetector([]),
        forecasting=forecasting or FakeForecasting(),
        notifier=notifier or FakeNotifier(),
        now=lambda tz: datetime(2026, 9, 10, 12, tzinfo=tz),
    )


def test_alert_validation_requires_matching_condition_values():
    with pytest.raises(ValueError):
        AlertCreate(name="bad", alert_type=AlertType.COST_THRESHOLD)
    with pytest.raises(ValueError):
        AlertCreate(name="bad", alert_type=AlertType.ANOMALY, threshold=Decimal("10"))
    increase = AlertCreate(
        name="increase", alert_type=AlertType.COST_INCREASE, percentage=Decimal("20")
    )
    assert increase.percentage == Decimal("20")


@pytest.mark.asyncio
async def test_threshold_alert_triggers_email_and_persists_timestamp():
    alert_item = alert()
    notifier = FakeNotifier()
    service = evaluator(alert_item, records([137]), notifier)
    result = (
        await service.evaluate(
            alert_item.user_id, "user@example.com", date(2026, 9, 1), date(2026, 9, 1)
        )
    )[0]
    assert result.status == "triggered"
    assert result.notification_sent is True
    assert alert_item.last_triggered_at is not None
    assert notifier.events[0][0] == "user@example.com"


@pytest.mark.asyncio
async def test_cooldown_and_disabled_alerts_prevent_duplicate_notifications():
    alert_item = alert(last_triggered_at=datetime(2026, 9, 10, 10, tzinfo=UTC))
    notifier = FakeNotifier()
    service = evaluator(alert_item, records([137]), notifier)
    cooldown = (
        await service.evaluate(
            alert_item.user_id, "user@example.com", date(2026, 9, 1), date(2026, 9, 1)
        )
    )[0]
    assert cooldown.status == "cooldown"
    alert_item.enabled = False
    disabled = (
        await service.evaluate(
            alert_item.user_id, "user@example.com", date(2026, 9, 1), date(2026, 9, 1)
        )
    )[0]
    assert disabled.status == "disabled"
    assert notifier.events == []


@pytest.mark.asyncio
async def test_notification_failure_does_not_update_trigger_state():
    alert_item = alert()
    service = evaluator(alert_item, records([137]), FakeNotifier(failure=True))
    result = (
        await service.evaluate(
            alert_item.user_id, "user@example.com", date(2026, 9, 1), date(2026, 9, 1)
        )
    )[0]
    assert result.status == "notification_failed"
    assert alert_item.last_triggered_at is None


@pytest.mark.asyncio
async def test_percentage_anomaly_and_forecast_conditions_use_existing_services():
    increase = alert(
        AlertType.COST_INCREASE,
        threshold=None,
        percentage=Decimal("20"),
        cooldown_minutes=0,
    )
    increase_result = (
        await evaluator(increase, records([10, 10, 10, 20, 20, 20])).evaluate(
            increase.user_id, "user@example.com", date(2026, 9, 1), date(2026, 9, 6)
        )
    )[0]
    assert increase_result.status == "triggered"

    anomaly_alert = alert(AlertType.ANOMALY, threshold=None, service=None)
    anomaly_result = (
        await evaluator(
            anomaly_alert,
            [],
            detector=FakeDetector(
                [
                    SimpleNamespace(
                        actual_cost=Decimal("40"),
                        expected_cost=Decimal("10"),
                        currency="USD",
                        severity=SimpleNamespace(value="high"),
                        anomaly_score=Decimal("5"),
                    )
                ]
            ),
        ).evaluate(
            anomaly_alert.user_id,
            "user@example.com",
            date(2026, 9, 1),
            date(2026, 9, 1),
        )
    )[0]
    assert anomaly_result.status == "triggered"

    forecast_alert = alert(
        AlertType.FORECAST_THRESHOLD, threshold=Decimal("100"), service=None
    )
    forecast_result = (
        await evaluator(
            forecast_alert,
            [],
            forecasting=FakeForecasting(ForecastStatus.READY, Decimal("125")),
        ).evaluate(
            forecast_alert.user_id,
            "user@example.com",
            date(2026, 9, 1),
            date(2026, 9, 1),
        )
    )[0]
    assert forecast_result.status == "triggered"


@pytest.mark.asyncio
async def test_alert_api_requires_authentication(client: AsyncClient):
    response = await client.get("/api/v1/alerts")
    assert response.status_code == 401
