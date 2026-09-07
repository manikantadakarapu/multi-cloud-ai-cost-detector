"""Contracts for evidence-constrained AI explanations of recommendations."""

from __future__ import annotations

from datetime import date as date_type
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.anomaly import Anomaly
from app.schemas.forecast import ForecastResult
from app.schemas.optimization import Recommendation


class AdvisorStatus(StrEnum):
    READY = "ready"
    DISABLED = "disabled"
    UNAVAILABLE = "unavailable"
    TIMEOUT = "timeout"
    INVALID = "invalid"
    INSUFFICIENT_DATA = "insufficient_data"


class AdvisorConfidence(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class AdvisorDailyCost(BaseModel):
    model_config = ConfigDict(extra="forbid")

    date: date_type
    cost: Decimal = Field(ge=0)


class AdvisorExplorerContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    record_count: int = Field(ge=0)
    total_cost: Decimal = Field(ge=0)
    currency: str | None = None
    daily_costs: list[AdvisorDailyCost] = Field(default_factory=list)


class OptimizationAdvisorContext(BaseModel):
    """Facts-only context assembled from application-owned deterministic data."""

    model_config = ConfigDict(extra="forbid")

    context_version: str
    recommendation: Recommendation
    historical_cost: Decimal | None = Field(default=None, ge=0)
    cost_trend: list[AdvisorDailyCost] = Field(default_factory=list)
    related_anomalies: list[Anomaly] = Field(default_factory=list)
    forecast: ForecastResult | None = None
    explorer: AdvisorExplorerContext | None = None
    data_freshness: date_type | None = None
    missing_data: list[str] = Field(default_factory=list)


class OptimizationAdvisorRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    start_date: date_type
    end_date: date_type

    @model_validator(mode="after")
    def validate_period(self) -> OptimizationAdvisorRequest:
        if self.end_date < self.start_date:
            raise ValueError("end_date must be on or after start_date")
        return self


class OptimizationAdvisorDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary: str = Field(min_length=1, max_length=600)
    why_it_matters: str = Field(min_length=1, max_length=800)
    evidence_summary: str = Field(min_length=1, max_length=800)
    tradeoffs: list[str] = Field(min_length=1, max_length=8)
    suggested_next_steps: list[str] = Field(min_length=1, max_length=8)
    expected_impact: str = Field(min_length=1, max_length=600)
    confidence: AdvisorConfidence
    limitations: list[str] = Field(default_factory=list, max_length=8)


class OptimizationAdvisorResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    recommendation: Recommendation
    context: OptimizationAdvisorContext
    status: AdvisorStatus
    summary: str | None = None
    why_it_matters: str | None = None
    evidence_summary: str | None = None
    tradeoffs: list[str] = Field(default_factory=list)
    suggested_next_steps: list[str] = Field(default_factory=list)
    expected_impact: str | None = None
    confidence: AdvisorConfidence | None = None
    limitations: list[str] = Field(default_factory=list)
    generated_at: datetime | None = None
    model: str | None = None
    prompt_version: str
    fallback_message: str | None = None
