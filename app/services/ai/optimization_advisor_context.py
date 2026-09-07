"""Build deterministic, provider-neutral context for the FinOps advisor."""

from __future__ import annotations

from collections import defaultdict
from decimal import ROUND_HALF_UP, Decimal

from app.schemas.anomaly import Anomaly
from app.schemas.explorer import CostRecord
from app.schemas.forecast import ForecastResult
from app.schemas.optimization import Recommendation
from app.schemas.optimization_advisor import (
    AdvisorDailyCost,
    AdvisorExplorerContext,
    OptimizationAdvisorContext,
)

CONTEXT_VERSION = "optimization-advisor-context-v1"
CENT = Decimal("0.01")
ZERO = Decimal("0")


def _money(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def _matches(record: CostRecord, recommendation: Recommendation) -> bool:
    return (
        record.provider.lower() == recommendation.provider.lower()
        and record.account_id == recommendation.account_id
        and record.service == recommendation.service
        and record.region == recommendation.region
    )


def build_optimization_advisor_context(
    recommendation: Recommendation,
    records: list[CostRecord],
    anomalies: list[Anomaly] | None = None,
    forecast: ForecastResult | None = None,
) -> OptimizationAdvisorContext:
    """Assemble only verified recommendation and deterministic supporting facts."""
    matched = [record for record in records if _matches(record, recommendation)]
    daily: defaultdict = defaultdict(lambda: ZERO)
    for record in matched:
        if record.cost >= ZERO:
            daily[record.date] += record.cost
    trend = [
        AdvisorDailyCost(date=day, cost=_money(cost))
        for day, cost in sorted(daily.items())
    ]
    missing_data: list[str] = []
    if not matched:
        missing_data.append(
            "No matching normalized Cost Explorer records were available."
        )
    if not anomalies:
        missing_data.append(
            "No related deterministic anomalies were found in this period."
        )
    if forecast is None:
        missing_data.append("No relevant deterministic forecast was available.")
    currency = matched[0].currency if matched else recommendation.savings_currency
    explorer = AdvisorExplorerContext(
        record_count=len(matched),
        total_cost=_money(sum((record.cost for record in matched), ZERO)),
        currency=currency if matched else None,
        daily_costs=trend,
    )
    return OptimizationAdvisorContext(
        context_version=CONTEXT_VERSION,
        recommendation=recommendation,
        historical_cost=explorer.total_cost if matched else None,
        cost_trend=trend,
        related_anomalies=anomalies or [],
        forecast=forecast,
        explorer=explorer if matched else None,
        data_freshness=max((record.date for record in matched), default=None),
        missing_data=missing_data,
    )
