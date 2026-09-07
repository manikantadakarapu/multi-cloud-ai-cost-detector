"""CRUD and deterministic evaluation for user-scoped cost alerts."""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

from app.alerts.models import Alert
from app.alerts.notifications import NotificationError, NotificationSender
from app.alerts.repository import AlertRepository
from app.core.logging import get_logger
from app.schemas.alerts import (
    AlertCreate,
    AlertEvaluationResult,
    AlertType,
    AlertUpdate,
)
from app.schemas.anomaly import AnomalyQuery
from app.schemas.forecast import ForecastDimension, ForecastQuery, ForecastStatus
from app.services.anomaly import AnomalyDetectionService
from app.services.explorer.service import CostExplorerService
from app.services.forecasting import ForecastingService

logger = get_logger(__name__)
ZERO = Decimal("0")


class AlertNotFoundError(Exception):
    """Raised when a user-scoped alert does not exist."""


class AlertService:
    def __init__(self, repo: AlertRepository) -> None:
        self._repo = repo

    async def list(self, user_id) -> list[Alert]:
        return await self._repo.list_for_user(user_id)

    async def get(self, alert_id, user_id) -> Alert:
        alert = await self._repo.get_for_user(alert_id, user_id)
        if alert is None:
            raise AlertNotFoundError("Alert not found")
        return alert

    async def create(self, payload: AlertCreate, user_id) -> Alert:
        alert = Alert(user_id=user_id, **payload.model_dump())
        return await self._repo.create(alert)

    async def update(self, alert_id, payload: AlertUpdate, user_id) -> Alert:
        alert = await self.get(alert_id, user_id)
        values = payload.model_dump(exclude_unset=True)
        merged = {
            "name": alert.name,
            "alert_type": alert.alert_type,
            "provider": alert.provider,
            "account_id": alert.account_id,
            "service": alert.service,
            "region": alert.region,
            "threshold": alert.threshold,
            "percentage": alert.percentage,
            "severity": alert.severity,
            "enabled": alert.enabled,
            "cooldown_minutes": alert.cooldown_minutes,
            **values,
        }
        AlertCreate.model_validate(merged)
        for field, value in values.items():
            setattr(alert, field, value)
        return await self._repo.save(alert)

    async def delete(self, alert_id, user_id) -> None:
        await self._repo.delete(await self.get(alert_id, user_id))


class AlertEvaluationService:
    """Evaluate configured alerts using existing deterministic services."""

    def __init__(
        self,
        repo: AlertRepository,
        explorer: CostExplorerService,
        detector: AnomalyDetectionService,
        forecasting: ForecastingService,
        notifier: NotificationSender,
        now: Any = datetime.now,
    ) -> None:
        self._repo = repo
        self._explorer = explorer
        self._detector = detector
        self._forecasting = forecasting
        self._notifier = notifier
        self._now = now

    async def evaluate(
        self, user_id, recipient: str, start_date: date, end_date: date
    ) -> list[AlertEvaluationResult]:
        results = []
        for alert in await self._repo.list_for_user(user_id):
            results.append(
                await self._evaluate_one(alert, recipient, start_date, end_date)
            )
        return results

    async def _evaluate_one(
        self, alert: Alert, recipient: str, start_date: date, end_date: date
    ) -> AlertEvaluationResult:
        if not alert.enabled:
            return AlertEvaluationResult(
                alert_id=alert.id, status="disabled", reason="Alert is disabled"
            )
        try:
            outcome = await self._condition(alert, start_date, end_date)
        except (ValueError, TypeError, ArithmeticError) as error:
            logger.warning(
                "alert_configuration_invalid", extra={"alert_id": str(alert.id)}
            )
            return AlertEvaluationResult(
                alert_id=alert.id,
                status="invalid_configuration",
                reason=str(error),
            )
        except Exception:
            logger.exception(
                "alert_data_evaluation_failed", extra={"alert_id": str(alert.id)}
            )
            return AlertEvaluationResult(
                alert_id=alert.id,
                status="evaluation_failed",
                reason="Alert data evaluation failed; no notification was sent",
            )
        if not outcome["triggered"]:
            return AlertEvaluationResult(
                alert_id=alert.id,
                status="not_triggered",
                reason=outcome["reason"],
                current_value=outcome.get("current_value"),
                threshold=outcome.get("threshold"),
            )
        now = self._now(UTC)
        if alert.last_triggered_at and now - alert.last_triggered_at < timedelta(
            minutes=alert.cooldown_minutes
        ):
            return AlertEvaluationResult(
                alert_id=alert.id,
                status="cooldown",
                reason=f"Trigger suppressed until cooldown expires; {outcome['reason']}",
                current_value=outcome.get("current_value"),
                threshold=outcome.get("threshold"),
            )
        try:
            await self._notifier.send(
                recipient,
                alert,
                str(outcome.get("subject_value", outcome.get("current_value"))),
                outcome["reason"],
                now.isoformat(),
            )
        except NotificationError as error:
            logger.warning(
                "alert_notification_failed", extra={"alert_id": str(alert.id)}
            )
            return AlertEvaluationResult(
                alert_id=alert.id,
                status="notification_failed",
                reason=outcome["reason"],
                notification_error=str(error),
                current_value=outcome.get("current_value"),
                threshold=outcome.get("threshold"),
            )
        alert.last_triggered_at = now
        await self._repo.save(alert)
        return AlertEvaluationResult(
            alert_id=alert.id,
            status="triggered",
            reason=outcome["reason"],
            notification_sent=True,
            current_value=outcome.get("current_value"),
            threshold=outcome.get("threshold"),
        )

    async def _condition(
        self, alert: Alert, start_date: date, end_date: date
    ) -> dict[str, Any]:
        alert_type = AlertType(alert.alert_type)
        if alert_type in {AlertType.COST_THRESHOLD, AlertType.COST_INCREASE}:
            records = await self._explorer.get_cost_records(
                start_date, end_date, alert.provider
            )
            records = [record for record in records if self._matches(record, alert)]
            daily: defaultdict[date, Decimal] = defaultdict(lambda: ZERO)
            for record in records:
                if record.cost >= ZERO:
                    daily[record.date] += record.cost
            if not daily:
                return {
                    "triggered": False,
                    "reason": "No matching cost data was available",
                }
            if alert_type is AlertType.COST_THRESHOLD:
                current_date = max(daily)
                current = daily[current_date]
                threshold = Decimal(alert.threshold)
                return {
                    "triggered": current > threshold,
                    "current_value": current,
                    "threshold": threshold,
                    "subject_value": f"{current} {records[0].currency} on {current_date}",
                    "reason": (
                        f"Daily cost exceeded configured threshold by {current - threshold} "
                        f"{records[0].currency}"
                    ),
                }
            values = [daily[day] for day in sorted(daily)]
            midpoint = len(values) // 2
            if midpoint == 0:
                return {
                    "triggered": False,
                    "reason": "Insufficient comparison-period cost data",
                }
            baseline = sum(values[:midpoint], ZERO) / Decimal(midpoint)
            current = sum(values[midpoint:], ZERO) / Decimal(len(values) - midpoint)
            increase = (
                (current - baseline) / baseline * Decimal("100")
                if baseline > ZERO
                else ZERO
            )
            percentage = Decimal(alert.percentage)
            return {
                "triggered": baseline > ZERO and increase > percentage,
                "current_value": increase,
                "threshold": percentage,
                "subject_value": f"{increase:.2f}% increase",
                "reason": (
                    f"Cost increased by {increase:.2f}%, above configured "
                    f"{percentage:.2f}% threshold"
                ),
            }
        if alert_type is AlertType.ANOMALY:
            result = await self._detector.detect(
                AnomalyQuery(
                    start_date=start_date,
                    end_date=end_date,
                    provider=alert.provider,
                    account_id=alert.account_id,
                    service=alert.service,
                    region=alert.region,
                    limit=100,
                )
            )
            if not result.anomalies:
                return {
                    "triggered": False,
                    "reason": "No qualifying deterministic anomaly was found",
                }
            anomaly = result.anomalies[0]
            return {
                "triggered": True,
                "current_value": anomaly.actual_cost,
                "subject_value": (
                    f"actual {anomaly.actual_cost} {anomaly.currency}, "
                    f"expected {anomaly.expected_cost} {anomaly.currency}"
                ),
                "reason": (
                    f"Deterministic {anomaly.severity.value} anomaly detected with "
                    f"score {anomaly.anomaly_score}"
                ),
            }
        forecast = await self._forecasting.forecast(
            ForecastQuery(
                start_date=start_date,
                end_date=end_date,
                horizon_days=7,
                provider=alert.provider,
                account_id=alert.account_id,
                service=alert.service,
                region=alert.region,
                dimension=(
                    ForecastDimension.SERVICE
                    if alert.service
                    else ForecastDimension.TOTAL
                ),
            )
        )
        if forecast.status is not ForecastStatus.READY or not forecast.forecasts:
            return {
                "triggered": False,
                "reason": "No usable deterministic forecast was available",
            }
        value = forecast.forecasts[0].projected_cost
        threshold = Decimal(alert.threshold)
        return {
            "triggered": value > threshold,
            "current_value": value,
            "threshold": threshold,
            "subject_value": f"forecast {value} {forecast.forecasts[0].currency}",
            "reason": (
                f"Forecasted cost exceeded configured threshold by {value - threshold} "
                f"{forecast.forecasts[0].currency}"
            ),
        }

    @staticmethod
    def _matches(record, alert: Alert) -> bool:
        return (
            (not alert.provider or record.provider.lower() == alert.provider.lower())
            and (
                not alert.account_id
                or (
                    record.account_id
                    and alert.account_id.lower() in record.account_id.lower()
                )
            )
            and (not alert.service or alert.service.lower() in record.service.lower())
            and (
                not alert.region
                or (record.region and alert.region.lower() in record.region.lower())
            )
        )
