"""CRUD and deterministic budget guardrail evaluation."""

from __future__ import annotations

import hashlib
from calendar import monthrange
from collections.abc import Callable
from datetime import UTC, date, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from app.budgets.models import Budget
from app.budgets.repository import BudgetRepository
from app.core.cache import RedisCache
from app.core.logging import get_logger
from app.schemas.budgets import (
    BudgetCreate,
    BudgetEvaluation,
    BudgetEvaluationError,
    BudgetPeriod,
    BudgetStatus,
    BudgetUpdate,
    validate_budget_update,
)
from app.schemas.forecast import ForecastDimension, ForecastQuery, ForecastStatus
from app.services.explorer.service import CostExplorerService
from app.services.forecasting import ForecastingService

logger = get_logger(__name__)
ZERO = Decimal("0")
CENT = Decimal("0.01")
EVALUATION_CACHE_TTL = 300


def money(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


class BudgetNotFoundError(Exception):
    """Raised when a user-scoped budget does not exist."""


class BudgetService:
    def __init__(self, repo: BudgetRepository) -> None:
        self._repo = repo

    async def list(self, user_id) -> list[Budget]:
        return await self._repo.list_for_user(user_id)

    async def get(self, budget_id, user_id) -> Budget:
        budget = await self._repo.get_for_user(budget_id, user_id)
        if budget is None:
            raise BudgetNotFoundError("Budget not found")
        return budget

    async def create(self, payload: BudgetCreate, user_id) -> Budget:
        return await self._repo.create(Budget(user_id=user_id, **payload.model_dump()))

    async def update(self, budget_id, payload: BudgetUpdate, user_id) -> Budget:
        budget = await self.get(budget_id, user_id)
        values = payload.model_dump(exclude_unset=True)
        merged = {
            "name": budget.name,
            "scope": budget.scope,
            "provider": budget.provider,
            "account_id": budget.account_id,
            "service": budget.service,
            "region": budget.region,
            "period": budget.period,
            "amount": budget.amount,
            "currency": budget.currency,
            "warning_threshold": budget.warning_threshold,
            "critical_threshold": budget.critical_threshold,
            "enabled": budget.enabled,
            **values,
        }
        validate_budget_update(merged)
        for field, value in values.items():
            setattr(budget, field, value)
        return await self._repo.save(budget)

    async def delete(self, budget_id, user_id) -> None:
        await self._repo.delete(await self.get(budget_id, user_id))


class BudgetEvaluationService:
    """Evaluate monthly budgets using existing Cost Explorer and forecasting services."""

    def __init__(
        self,
        explorer: CostExplorerService,
        forecasting: ForecastingService,
        cache: RedisCache | None = None,
        user_scope: str = "shared",
        now: Callable[..., datetime] = datetime.now,
    ) -> None:
        self._explorer = explorer
        self._forecasting = forecasting
        self._cache = cache
        self._user_scope = user_scope
        self._now = now

    async def evaluate(self, budget: Budget) -> BudgetEvaluation:
        evaluated_at = self._now(UTC)
        period_start, period_end = self._period_bounds(
            budget.period, evaluated_at.date()
        )
        cache_key = self._cache_key(budget, evaluated_at.date())
        if self._cache is not None:
            cached = await self._cache.get_json(cache_key)
            if cached is not None:
                try:
                    return BudgetEvaluation.model_validate(cached)
                except Exception:
                    logger.warning("budget_evaluation_cache_invalid")

        if not budget.enabled:
            result = self._unavailable_result(
                budget,
                period_start,
                evaluated_at,
                BudgetStatus.DISABLED,
                BudgetStatus.DISABLED,
                "Budget evaluation is disabled.",
            )
            return result

        records = await self._explorer.get_cost_records(
            period_start, evaluated_at.date(), budget.provider
        )
        records = [record for record in records if self._matches(record, budget)]
        if not records:
            return self._unavailable_result(
                budget,
                period_start,
                evaluated_at,
                BudgetStatus.UNAVAILABLE,
                BudgetStatus.UNAVAILABLE,
                "Actual cost data was unavailable for the current monthly budget period.",
            )

        currencies = {record.currency.upper() for record in records}
        if currencies != {budget.currency.upper()}:
            raise BudgetEvaluationError(
                f"Currency mismatch: budget uses {budget.currency}, cost data uses "
                f"{', '.join(sorted(currencies))}."
            )
        actual = money(sum((record.cost for record in records), ZERO))
        actual_utilization = money(actual / budget.amount * Decimal("100"))
        actual_remaining = money(budget.amount - actual)
        actual_status = self._status(actual, budget)
        forecast_spend, forecast_status, forecast_variance, forecast_reason = (
            await self._evaluate_forecast(
                budget, period_start, evaluated_at.date(), period_end, actual
            )
        )
        actual_reason = self._status_reason(
            "Actual spend", actual, actual_utilization, budget, actual_status
        )
        reason = (
            f"{actual_reason} {forecast_reason}" if forecast_reason else actual_reason
        )
        result = BudgetEvaluation(
            budget_id=budget.id,
            actual_spend=actual,
            budget_amount=money(budget.amount),
            actual_utilization=actual_utilization,
            actual_remaining=actual_remaining,
            actual_status=actual_status,
            forecast_spend=forecast_spend,
            forecast_variance=forecast_variance,
            forecast_status=forecast_status,
            evaluation_period=f"{period_start:%Y-%m}",
            currency=budget.currency,
            scope=budget.scope,
            reason=reason,
            data_available=True,
            forecast_available=forecast_spend is not None,
            evaluated_at=evaluated_at,
        )
        if self._cache is not None:
            await self._cache.set_json(cache_key, result, EVALUATION_CACHE_TTL)
        return result

    async def _evaluate_forecast(
        self,
        budget: Budget,
        period_start: date,
        today: date,
        period_end: date,
        actual: Decimal,
    ) -> tuple[Decimal | None, BudgetStatus, Decimal | None, str]:
        remaining_days = (period_end - today).days
        if remaining_days <= 0:
            return (
                None,
                BudgetStatus.UNAVAILABLE,
                None,
                "Forecast is unavailable because the budget period has ended.",
            )
        horizon_days = 7 if remaining_days <= 7 else 14 if remaining_days <= 14 else 30
        query = ForecastQuery(
            start_date=period_start,
            end_date=today,
            horizon_days=horizon_days,
            provider=budget.provider,
            account_id=budget.account_id,
            service=budget.service,
            region=budget.region,
            currency=budget.currency,
            dimension=ForecastDimension.TOTAL,
        )
        forecast = await self._forecasting.forecast(query)
        if forecast.status is not ForecastStatus.READY or not forecast.forecasts:
            return (
                None,
                BudgetStatus.UNAVAILABLE,
                None,
                "Forecast is unavailable because there is not enough reliable cost history.",
            )
        result = forecast.forecasts[0]
        if result.currency.upper() != budget.currency.upper():
            raise BudgetEvaluationError(
                f"Currency mismatch: budget uses {budget.currency}, "
                f"forecast uses {result.currency}."
            )
        future = money(
            sum(
                (
                    point.forecast_cost
                    for point in result.daily_forecast
                    if point.date <= period_end
                ),
                ZERO,
            )
        )
        projected = money(actual + future)
        variance = money(projected - budget.amount)
        status = self._status(projected, budget)
        reason = self._status_reason(
            "Forecasted spend",
            projected,
            money(projected / budget.amount * Decimal("100")),
            budget,
            status,
        )
        return projected, status, variance, reason

    @staticmethod
    def _period_bounds(period: str, today: date) -> tuple[date, date]:
        if period != BudgetPeriod.MONTHLY:
            raise BudgetEvaluationError(f"Unsupported budget period: {period}")
        return today.replace(day=1), today.replace(
            day=monthrange(today.year, today.month)[1]
        )

    def _cache_key(self, budget: Budget, today: date) -> str:
        payload = "|".join(
            str(value)
            for value in (
                self._user_scope,
                budget.id,
                budget.updated_at,
                budget.enabled,
                budget.amount,
                budget.currency,
                budget.warning_threshold,
                budget.critical_threshold,
                budget.provider,
                budget.account_id,
                budget.service,
                budget.region,
                budget.period,
                today,
            )
        )
        digest = hashlib.sha256(payload.encode()).hexdigest()[:20]
        return f"budget-evaluation:{self._user_scope}:{digest}"

    @staticmethod
    def _matches(record: Any, budget: Budget) -> bool:
        return (
            (not budget.provider or record.provider.lower() == budget.provider.lower())
            and (
                not budget.account_id
                or (
                    record.account_id
                    and budget.account_id.lower() in record.account_id.lower()
                )
            )
            and (not budget.service or budget.service.lower() in record.service.lower())
            and (
                not budget.region
                or (record.region and budget.region.lower() in record.region.lower())
            )
        )

    @staticmethod
    def _status(spend: Decimal, budget: Budget) -> BudgetStatus:
        if spend > budget.amount:
            return BudgetStatus.EXCEEDED
        utilization = spend / budget.amount * Decimal("100")
        if utilization >= budget.critical_threshold:
            return BudgetStatus.CRITICAL
        if utilization >= budget.warning_threshold:
            return BudgetStatus.WARNING
        return BudgetStatus.HEALTHY

    @staticmethod
    def _status_reason(
        label: str,
        spend: Decimal,
        utilization: Decimal,
        budget: Budget,
        status: BudgetStatus,
    ) -> str:
        prefix = {
            BudgetStatus.HEALTHY: "remains within",
            BudgetStatus.WARNING: "has reached the warning threshold of",
            BudgetStatus.CRITICAL: "has reached the critical threshold of",
            BudgetStatus.EXCEEDED: "has exceeded",
        }.get(status, "has an unavailable status")
        if status is BudgetStatus.EXCEEDED:
            return (
                f"{label} is {spend} {budget.currency} and has exceeded the "
                f"{budget.amount} {budget.currency} monthly budget."
            )
        return (
            f"{label} is {spend} {budget.currency} ({utilization}%) and {prefix} "
            "the monthly budget."
        )

    @staticmethod
    def _unavailable_result(
        budget: Budget,
        period_start: date,
        evaluated_at: datetime,
        actual_status: BudgetStatus,
        forecast_status: BudgetStatus,
        reason: str,
    ) -> BudgetEvaluation:
        return BudgetEvaluation(
            budget_id=budget.id,
            actual_spend=ZERO,
            budget_amount=money(budget.amount),
            actual_utilization=ZERO,
            actual_remaining=money(budget.amount),
            actual_status=actual_status,
            forecast_spend=None,
            forecast_variance=None,
            forecast_status=forecast_status,
            evaluation_period=f"{period_start:%Y-%m}",
            currency=budget.currency,
            scope=budget.scope,
            reason=reason,
            data_available=False,
            forecast_available=False,
            evaluated_at=evaluated_at,
        )
