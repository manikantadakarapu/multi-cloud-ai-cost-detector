"""Provider-independent contracts for cost intelligence."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.cost_events import CostEventType


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


class AIInsightStatus(StrEnum):
    """Safe, frontend-facing AI generation states. Never a raw provider error."""

    READY = "ready"
    PENDING = "pending"
    DISABLED = "disabled"
    EMPTY = "empty"
    UNAVAILABLE = "unavailable"
    QUOTA_EXCEEDED = "quota_exceeded"
    TIMEOUT = "timeout"
    INVALID = "invalid"


class GeminiInsightDraft(BaseModel):
    """Validated LLM fields. Monetary values are attached from CostEvent, not this draft."""

    model_config = ConfigDict(extra="ignore")

    title: str = Field(min_length=1, max_length=120)
    summary: str = Field(min_length=1, max_length=400)
    severity: InsightSeverity
    likely_cause: str = Field(min_length=1, max_length=400)
    recommended_action: str = Field(min_length=1, max_length=400)


class AIInsight(BaseModel):
    """Gemini explanation of a deterministic cost event, with measured numbers attached."""

    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    severity: InsightSeverity
    likely_cause: str = Field(min_length=1)
    recommended_action: str = Field(min_length=1)
    event_type: CostEventType
    provider: str | None = None
    service: str | None = None
    current_cost: Decimal
    previous_cost: Decimal
    absolute_change: Decimal
    percentage_change: Decimal | None = None
    currency: str
    period_start: date
    period_end: date
    source: str = "gemini"


class CostInsight(BaseModel):
    """A deterministic insight that intelligence services can explain."""

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
    """Frontend-oriented collection of deterministic insights plus optional AI explanations."""

    model_config = ConfigDict(extra="forbid")

    insights: list[CostInsight]
    ai_insights: list[AIInsight] = Field(default_factory=list)
    ai_status: AIInsightStatus = AIInsightStatus.DISABLED
    ai_message: str | None = None
