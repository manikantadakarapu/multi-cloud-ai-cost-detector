"""Stable frontend-oriented dashboard response contracts."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.analytics import (
    CostDriver,
    DailyAnalytics,
    ProviderAnalytics,
    ServiceAnalytics,
)


class DashboardOverview(BaseModel):
    """Headline values required by the dashboard overview cards."""

    model_config = ConfigDict(extra="forbid")

    total_cost: Decimal = Field(ge=0)
    currency: str
    period_start: date
    period_end: date
    previous_period_cost: Decimal = Field(ge=0)
    absolute_change: Decimal
    percentage_change: Decimal | None


class DashboardSummary(BaseModel):
    """Single payload for the initial dashboard view."""

    model_config = ConfigDict(extra="forbid")

    overview: DashboardOverview
    providers: list[ProviderAnalytics]
    services: list[ServiceAnalytics]
    trend: list[DailyAnalytics]
    drivers: list[CostDriver]
