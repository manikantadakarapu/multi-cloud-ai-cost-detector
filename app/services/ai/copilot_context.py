"""Deterministic classification and verified context retrieval for Copilot."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from app.budgets.service import BudgetEvaluationService
from app.schemas.anomaly import AnomalyQuery
from app.schemas.budgets import BudgetEvaluation
from app.schemas.copilot import (
    CopilotBudgetContext,
    CopilotContext,
    CopilotCostContext,
    CopilotDailyCost,
    CopilotForecastContext,
    CopilotForecastItem,
    CopilotIntent,
    CopilotProviderCost,
    CopilotServiceCost,
    CopilotTimeRange,
)
from app.schemas.explorer import ExplorerQuery
from app.schemas.forecast import ForecastDimension, ForecastQuery
from app.schemas.optimization import OptimizationQuery
from app.services.anomaly import AnomalyDetectionService
from app.services.explorer.service import CostExplorerService
from app.services.forecasting import ForecastingService
from app.services.optimization import OptimizationService

CONTEXT_VERSION = "finops-copilot-context-v1"
CENT = Decimal("0.01")
ZERO = Decimal("0")

_DOMAIN_TERMS = {
    CopilotIntent.COST: ("cost", "spend", "increase", "provider", "service", "most"),
    CopilotIntent.ANOMALY: ("anomal", "spike", "unexpected", "investigate"),
    CopilotIntent.FORECAST: ("forecast", "project", "expected", "likely", "grow"),
    CopilotIntent.OPTIMIZATION: ("optim", "recommendation", "saving", "opportunit"),
    CopilotIntent.BUDGET: ("budget", "remaining", "exceed", "at risk", "utilization"),
}


def _money(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def classify_question(question: str) -> CopilotIntent:
    """Classify a question without sending it to an LLM."""
    lowered = question.lower()
    has_forecast = any(
        term in lowered for term in _DOMAIN_TERMS[CopilotIntent.FORECAST]
    )
    has_budget = any(term in lowered for term in _DOMAIN_TERMS[CopilotIntent.BUDGET])
    has_anomaly = any(term in lowered for term in _DOMAIN_TERMS[CopilotIntent.ANOMALY])
    has_optimization = any(
        term in lowered for term in _DOMAIN_TERMS[CopilotIntent.OPTIMIZATION]
    )
    if has_forecast and not (has_budget or has_anomaly or has_optimization):
        return CopilotIntent.FORECAST
    matched = {
        intent
        for intent, terms in _DOMAIN_TERMS.items()
        if any(term in lowered for term in terms)
    }
    if not matched:
        return CopilotIntent.UNSUPPORTED
    if len(matched) > 1:
        return CopilotIntent.CROSS_DOMAIN
    return next(iter(matched))


def _period(today: date) -> tuple[date, date, date, date]:
    start = today.replace(day=1)
    previous_end = start - timedelta(days=1)
    previous_start = previous_end.replace(day=1)
    return start, today, previous_start, previous_end


def _domains(intent: CopilotIntent, question: str) -> set[CopilotIntent]:
    if intent is not CopilotIntent.CROSS_DOMAIN:
        return {intent} if intent is not CopilotIntent.UNSUPPORTED else set()
    lowered = question.lower()
    return {
        domain
        for domain, terms in _DOMAIN_TERMS.items()
        if any(term in lowered for term in terms)
    }


def _cost_context(current: Any, previous: Any) -> CopilotCostContext:
    currency = current.overview.currency if current.records else None
    total = _money(current.overview.total_cost)
    previous_total = _money(previous.overview.total_cost) if previous.records else None
    change = _money(total - previous_total) if previous_total is not None else None
    change_percentage = (
        _money(change / previous_total * Decimal("100"))
        if change is not None and previous_total
        else None
    )
    return CopilotCostContext(
        total_cost=total,
        previous_total_cost=previous_total,
        change_amount=change,
        change_percentage=change_percentage,
        currency=currency,
        providers=[
            CopilotProviderCost(
                provider=item.key,
                cost=item.cost,
                percentage=item.percentage,
                currency=item.currency,
            )
            for item in current.dimension_totals.by_provider[:10]
        ],
        services=[
            CopilotServiceCost(
                provider="all",
                service=item.label,
                cost=item.cost,
                percentage=item.percentage,
                currency=item.currency,
            )
            for item in current.dimension_totals.by_service[:10]
        ],
        daily_costs=[
            CopilotDailyCost(date=item.date, cost=item.cost, currency=item.currency)
            for item in current.dimension_totals.by_date[:62]
        ],
        record_count=current.total_records,
    )


def _forecast_context(response: Any) -> CopilotForecastContext:
    return CopilotForecastContext(
        status=response.status,
        current_spend=response.summary.current_spend,
        projected_spend=response.summary.projected_spend,
        currency=response.forecasts[0].currency if response.forecasts else None,
        confidence=response.summary.confidence,
        forecasts=[
            CopilotForecastItem(
                forecast_id=item.forecast_id,
                provider=item.provider,
                service=item.service,
                projected_cost=item.projected_cost,
                lower_bound=item.lower_bound,
                upper_bound=item.upper_bound,
                currency=item.currency,
                confidence=item.confidence,
                horizon_days=item.horizon_days,
            )
            for item in response.forecasts[:10]
        ],
        message=response.message,
    )


class CopilotContextService:
    """Retrieve only the deterministic domains needed for one user question."""

    def __init__(
        self,
        *,
        explorer: CostExplorerService,
        detector: AnomalyDetectionService,
        forecasting: ForecastingService,
        optimization: OptimizationService,
        budgets: Any | None = None,
        budget_evaluator: BudgetEvaluationService | None = None,
        budget_user_id: Any | None = None,
        today: date | None = None,
    ) -> None:
        self._explorer = explorer
        self._detector = detector
        self._forecasting = forecasting
        self._optimization = optimization
        self._budgets = budgets
        self._budget_evaluator = budget_evaluator
        self._budget_user_id = budget_user_id
        self._today = today

    async def build(self, question: str) -> CopilotContext:
        intent = classify_question(question)
        today = self._today or date.today()
        start, end, previous_start, previous_end = _period(today)
        domains = _domains(intent, question)
        limitations: list[str] = []
        context = CopilotContext(
            context_version=CONTEXT_VERSION,
            question=question,
            intent=intent,
            time_range=CopilotTimeRange(
                label="Current month to date", start_date=start, end_date=end
            ),
        )
        if intent is CopilotIntent.UNSUPPORTED:
            context.limitations.append(
                "Supported topics are cloud costs, anomalies, forecasts, "
                "optimization recommendations, budgets, and related FinOps analysis."
            )
            return context

        if CopilotIntent.COST in domains:
            current = await self._explorer.get_explorer_data(
                ExplorerQuery(start_date=start, end_date=end)
            )
            previous = await self._explorer.get_explorer_data(
                ExplorerQuery(start_date=previous_start, end_date=previous_end)
            )
            context.cost_context = _cost_context(current, previous)
            if not current.records:
                limitations.append(
                    "No normalized cost records were available for the current period."
                )

        if CopilotIntent.ANOMALY in domains:
            result = await self._detector.detect(
                AnomalyQuery(start_date=start, end_date=end, limit=10)
            )
            context.anomaly_context = result.anomalies[:10]
            if not context.anomaly_context:
                limitations.append(
                    "No qualifying deterministic anomalies were found for the current period."
                )

        if CopilotIntent.FORECAST in domains:
            response = await self._forecasting.forecast(
                ForecastQuery(
                    start_date=start,
                    end_date=end,
                    horizon_days=7,
                    dimension=ForecastDimension.TOTAL,
                )
            )
            context.forecast_context = _forecast_context(response)
            if not response.forecasts:
                limitations.append(
                    "A forecast was unavailable because reliable history was insufficient."
                )

        if CopilotIntent.OPTIMIZATION in domains:
            response = await self._optimization.list_recommendations(
                OptimizationQuery(start_date=start, end_date=end, limit=10)
            )
            context.optimization_context = response.recommendations[:10]
            if not context.optimization_context:
                limitations.append(
                    "No evidence-backed optimization recommendations matched "
                    "the current period."
                )

        if CopilotIntent.BUDGET in domains:
            if self._budgets is None or self._budget_evaluator is None:
                limitations.append("Budget context was unavailable.")
            else:
                for budget in await self._budgets.list_for_user(self._budget_user_id):
                    evaluation: BudgetEvaluation = (
                        await self._budget_evaluator.evaluate(budget)
                    )
                    context.budget_context.append(
                        CopilotBudgetContext(
                            budget_id=budget.id,
                            name=budget.name,
                            amount=budget.amount,
                            currency=budget.currency,
                            actual_spend=evaluation.actual_spend,
                            actual_utilization=evaluation.actual_utilization,
                            actual_remaining=evaluation.actual_remaining,
                            actual_status=evaluation.actual_status,
                            forecast_spend=evaluation.forecast_spend,
                            forecast_variance=evaluation.forecast_variance,
                            forecast_status=evaluation.forecast_status,
                            evaluation_period=evaluation.evaluation_period,
                            reason=evaluation.reason,
                        )
                    )
                if not context.budget_context:
                    limitations.append("No budgets are configured for this user.")

        context.limitations.extend(limitations)
        return context
