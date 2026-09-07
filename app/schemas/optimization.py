"""Provider-independent contracts for deterministic FinOps recommendations."""

from __future__ import annotations

from datetime import date as date_type
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.cost import SupportedProvider


class RecommendationCategory(StrEnum):
    COST_GROWTH = "cost_growth"
    HIGH_COST_SERVICE = "high_cost_service"
    STORAGE = "storage"
    NETWORK = "network"


class RecommendationPriority(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class RecommendationConfidence(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class RecommendationStatus(StrEnum):
    NEW = "new"
    REVIEWED = "reviewed"
    DISMISSED = "dismissed"
    IMPLEMENTED = "implemented"


class RecommendationSort(StrEnum):
    SAVINGS = "savings"
    PRIORITY = "priority"
    CREATED_DATE = "created_date"


class RecommendationEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str = Field(min_length=1, max_length=120)
    value: str = Field(min_length=1, max_length=300)
    source: str = Field(min_length=1, max_length=120)


class OptimizationQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")

    start_date: date_type
    end_date: date_type
    provider: SupportedProvider | None = None
    account_id: str | None = None
    service: str | None = None
    region: str | None = None
    category: RecommendationCategory | None = None
    priority: RecommendationPriority | None = None
    status: RecommendationStatus | None = None
    sort_by: RecommendationSort = RecommendationSort.SAVINGS
    sort_order: str = "desc"
    limit: int = Field(default=50, ge=1, le=100)
    offset: int = Field(default=0, ge=0)

    @field_validator("account_id", "service", "region")
    @classmethod
    def strip_filter(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None

    @field_validator("sort_order")
    @classmethod
    def validate_sort_order(cls, value: str) -> str:
        value = value.lower()
        if value not in {"asc", "desc"}:
            raise ValueError("sort_order must be asc or desc")
        return value

    @model_validator(mode="after")
    def validate_dates(self) -> OptimizationQuery:
        if self.end_date < self.start_date:
            raise ValueError("end_date must be on or after start_date")
        return self


class Recommendation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    recommendation_id: str
    provider: str
    account_id: str | None = None
    service: str | None = None
    region: str | None = None
    resource_identifier: str | None = None
    category: RecommendationCategory
    title: str
    description: str
    rationale: str
    evidence: list[RecommendationEvidence] = Field(min_length=1)
    priority: RecommendationPriority
    current_cost: Decimal = Field(ge=0)
    estimated_monthly_savings: Decimal | None = Field(default=None, ge=0)
    estimated_annual_savings: Decimal | None = Field(default=None, ge=0)
    savings_currency: str
    savings_period: str = "monthly"
    savings_explanation: str
    confidence: RecommendationConfidence
    status: RecommendationStatus = RecommendationStatus.NEW
    detection_method: str
    rule_version: str
    created_at: datetime


class RecommendationStatusUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: RecommendationStatus
    start_date: date_type
    end_date: date_type


class OptimizationSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    total_recommendations: int = Field(ge=0)
    high_or_critical: int = Field(ge=0)
    estimated_monthly_savings: Decimal | None = Field(default=None, ge=0)
    estimated_annual_savings: Decimal | None = Field(default=None, ge=0)
    by_category: dict[str, int]
    by_provider: dict[str, int]


class OptimizationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    recommendations: list[Recommendation]
    total: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)
    summary: OptimizationSummary
    query: OptimizationQuery
    rule_version: str
    insufficient_data: bool = False
    message: str | None = None
