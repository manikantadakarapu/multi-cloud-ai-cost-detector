"""Contracts for the bounded, evidence-constrained FinOps Copilot."""

from __future__ import annotations

import uuid
from datetime import date as date_type
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.anomaly import Anomaly
from app.schemas.budgets import BudgetStatus
from app.schemas.forecast import ForecastStatus
from app.schemas.optimization import Recommendation


class CopilotIntent(StrEnum):
    COST = "cost"
    ANOMALY = "anomaly"
    FORECAST = "forecast"
    OPTIMIZATION = "optimization"
    BUDGET = "budget"
    CROSS_DOMAIN = "cross_domain"
    UNSUPPORTED = "unsupported"


class CopilotStatus(StrEnum):
    READY = "ready"
    DISABLED = "disabled"
    UNAVAILABLE = "unavailable"
    INVALID = "invalid"
    UNSUPPORTED = "unsupported"
    INSUFFICIENT_DATA = "insufficient_data"


class CopilotConfidence(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class CopilotQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=3, max_length=1000)

    @model_validator(mode="after")
    def clean_question(self) -> CopilotQuery:
        self.question = self.question.strip()
        if len(self.question) < 3:
            raise ValueError("question must contain at least three characters")
        return self


class CopilotTimeRange(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str
    start_date: date_type
    end_date: date_type


class CopilotProviderCost(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: str
    cost: Decimal = Field(ge=0)
    percentage: Decimal = Field(ge=0, le=100)
    currency: str


class CopilotServiceCost(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: str
    service: str
    cost: Decimal = Field(ge=0)
    percentage: Decimal = Field(ge=0, le=100)
    currency: str


class CopilotDailyCost(BaseModel):
    model_config = ConfigDict(extra="forbid")

    date: date_type
    cost: Decimal = Field(ge=0)
    currency: str


class CopilotCostContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    total_cost: Decimal = Field(ge=0)
    previous_total_cost: Decimal | None = Field(default=None, ge=0)
    change_amount: Decimal | None = None
    change_percentage: Decimal | None = None
    currency: str | None = None
    providers: list[CopilotProviderCost] = Field(default_factory=list, max_length=10)
    services: list[CopilotServiceCost] = Field(default_factory=list, max_length=10)
    daily_costs: list[CopilotDailyCost] = Field(default_factory=list, max_length=62)
    record_count: int = Field(ge=0)


class CopilotForecastItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    forecast_id: str
    provider: str | None = None
    service: str | None = None
    projected_cost: Decimal = Field(ge=0)
    lower_bound: Decimal = Field(ge=0)
    upper_bound: Decimal = Field(ge=0)
    currency: str
    confidence: str
    horizon_days: int = Field(ge=1, le=30)


class CopilotForecastContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: ForecastStatus
    current_spend: Decimal = Field(ge=0)
    projected_spend: Decimal = Field(ge=0)
    currency: str | None = None
    confidence: str | None = None
    forecasts: list[CopilotForecastItem] = Field(default_factory=list, max_length=10)
    message: str | None = None


class CopilotBudgetContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    budget_id: uuid.UUID
    name: str
    amount: Decimal = Field(gt=0)
    currency: str
    actual_spend: Decimal = Field(ge=0)
    actual_utilization: Decimal = Field(ge=0)
    actual_remaining: Decimal
    actual_status: BudgetStatus
    forecast_spend: Decimal | None = Field(default=None, ge=0)
    forecast_variance: Decimal | None = None
    forecast_status: BudgetStatus
    evaluation_period: str
    reason: str


class CopilotContext(BaseModel):
    """Only verified, user-authorized application data sent to Gemini."""

    model_config = ConfigDict(extra="forbid")

    context_version: str
    question: str
    intent: CopilotIntent
    time_range: CopilotTimeRange
    cost_context: CopilotCostContext | None = None
    anomaly_context: list[Anomaly] = Field(default_factory=list, max_length=10)
    forecast_context: CopilotForecastContext | None = None
    optimization_context: list[Recommendation] = Field(
        default_factory=list, max_length=10
    )
    budget_context: list[CopilotBudgetContext] = Field(
        default_factory=list, max_length=20
    )
    limitations: list[str] = Field(default_factory=list, max_length=12)


class CopilotDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    answer: str = Field(min_length=1, max_length=1200)
    key_findings: list[str] = Field(min_length=1, max_length=10)
    evidence: list[str] = Field(default_factory=list, max_length=12)
    recommended_next_steps: list[str] = Field(default_factory=list, max_length=10)
    limitations: list[str] = Field(default_factory=list, max_length=12)
    confidence: CopilotConfidence
    anomaly_ids: list[str] = Field(default_factory=list, max_length=10)
    recommendation_ids: list[str] = Field(default_factory=list, max_length=10)
    budget_ids: list[uuid.UUID] = Field(default_factory=list, max_length=20)


class CopilotResponse(CopilotDraft):
    status: CopilotStatus
    intent: CopilotIntent
    generated_at: datetime | None = None
    model: str | None = None
    prompt_version: str
    fallback_message: str | None = None
