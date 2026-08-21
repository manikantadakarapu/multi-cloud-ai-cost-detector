"""Provider-independent contracts for future cost intelligence."""

from __future__ import annotations

from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class InsightType(StrEnum):
    """Controlled insight categories exposed to clients."""

    COST_INCREASE = "cost_increase"
    COST_DECREASE = "cost_decrease"
    TOP_COST_DRIVER = "top_cost_driver"


class InsightSeverity(StrEnum):
    """Stable severity levels for UI presentation and future AI enrichment."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class CostInsight(BaseModel):
    """A deterministic insight that future intelligence services can enrich."""

    model_config = ConfigDict(extra="forbid")

    type: InsightType
    severity: InsightSeverity
    title: str = Field(min_length=1)
    description: str = Field(min_length=1)
    provider: str | None = None
    service: str | None = None
    impact: Decimal
    currency: str


class DashboardInsights(BaseModel):
    """Frontend-oriented collection of deterministic insights."""

    model_config = ConfigDict(extra="forbid")

    insights: list[CostInsight]
