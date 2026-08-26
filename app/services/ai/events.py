"""Select meaningful cost events from dashboard analytics without calling an LLM."""

from __future__ import annotations

from decimal import Decimal

from app.schemas.analytics import CostDriver
from app.schemas.cost_events import CostEvent, CostEventType
from app.schemas.dashboard import DashboardSummary

ZERO = Decimal("0.00")


def is_significant_change(
    absolute_change: Decimal,
    percentage_change: Decimal | None,
    *,
    percentage_threshold: Decimal,
    absolute_threshold: Decimal,
) -> bool:
    """Return True when a change crosses the configured percentage or absolute threshold."""
    if absolute_change == ZERO:
        return False
    if abs(absolute_change) >= absolute_threshold:
        return True
    if percentage_change is not None and abs(percentage_change) >= percentage_threshold:
        return True
    return False


def select_cost_events(
    dashboard: DashboardSummary,
    *,
    percentage_threshold: Decimal,
    absolute_threshold: Decimal,
    max_events: int,
) -> list[CostEvent]:
    """Build a small set of provider-independent events from analytics drivers."""
    overview = dashboard.overview
    candidates: list[CostEvent] = []

    for driver in dashboard.drivers:
        if not is_significant_change(
            driver.absolute_change,
            driver.percentage_change,
            percentage_threshold=percentage_threshold,
            absolute_threshold=absolute_threshold,
        ):
            continue
        candidates.append(_event_from_driver(dashboard, driver))

    if not candidates and is_significant_change(
        overview.absolute_change,
        overview.percentage_change,
        percentage_threshold=percentage_threshold,
        absolute_threshold=absolute_threshold,
    ):
        candidates.append(
            CostEvent(
                event_type=_event_type(overview.absolute_change),
                provider=None,
                service=None,
                current_cost=overview.total_cost,
                previous_cost=overview.previous_period_cost,
                absolute_change=overview.absolute_change,
                percentage_change=overview.percentage_change,
                currency=overview.currency,
                period_start=overview.period_start,
                period_end=overview.period_end,
            )
        )

    candidates.sort(key=lambda item: abs(item.absolute_change), reverse=True)
    return candidates[: max(0, max_events)]


def _event_from_driver(dashboard: DashboardSummary, driver: CostDriver) -> CostEvent:
    overview = dashboard.overview
    service = driver.name if driver.category == "service" else None
    provider = driver.provider
    if driver.category == "provider":
        provider = driver.name
    return CostEvent(
        event_type=_event_type(driver.absolute_change),
        provider=provider,
        service=service,
        current_cost=driver.current_cost,
        previous_cost=driver.previous_cost,
        absolute_change=driver.absolute_change,
        percentage_change=driver.percentage_change,
        currency=overview.currency,
        period_start=overview.period_start,
        period_end=overview.period_end,
    )


def _event_type(absolute_change: Decimal) -> CostEventType:
    if absolute_change < ZERO:
        return CostEventType.COST_DECREASE
    return CostEventType.COST_INCREASE
