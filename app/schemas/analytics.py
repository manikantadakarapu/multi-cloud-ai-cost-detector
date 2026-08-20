"""Request and response schemas for deterministic cost analytics."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.cost import SupportedProvider


class AnalyticsQuery(BaseModel):
    """Common query parameters for a single analytics period."""

    model_config = ConfigDict(extra="forbid")

    start_date: date = Field(..., description="Period start date, inclusive.")
    end_date: date = Field(..., description="Period end date, inclusive.")
    provider: SupportedProvider | None = Field(
        default=None,
        description="Optional provider filter. Omit to query all providers.",
    )
    currency: str | None = Field(
        default=None,
        min_length=3,
        max_length=3,
        description="Optional ISO currency filter, such as USD.",
    )
    top_n: int = Field(default=5, ge=1, le=100)

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str | None) -> str | None:
        return value.upper() if value else value

    @model_validator(mode="after")
    def validate_period(self) -> AnalyticsQuery:
        if self.end_date < self.start_date:
            raise ValueError("end_date must be on or after start_date")
        return self


class ComparisonQuery(BaseModel):
    """Query parameters for comparing two explicit periods."""

    model_config = ConfigDict(extra="forbid")

    current_start_date: date
    current_end_date: date
    previous_start_date: date
    previous_end_date: date
    provider: SupportedProvider | None = None
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    top_n: int = Field(default=5, ge=1, le=100)

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str | None) -> str | None:
        return value.upper() if value else value

    @model_validator(mode="after")
    def validate_periods(self) -> ComparisonQuery:
        if self.current_end_date < self.current_start_date:
            raise ValueError("current_end_date must be on or after current_start_date")
        if self.previous_end_date < self.previous_start_date:
            raise ValueError(
                "previous_end_date must be on or after previous_start_date"
            )
        return self


class AnalyticsPeriod(BaseModel):
    """Inclusive period represented by an analytics response."""

    model_config = ConfigDict(extra="forbid")

    start: date
    end: date


class ProviderAnalytics(BaseModel):
    """Cost and share for one provider."""

    model_config = ConfigDict(extra="forbid")

    provider: str
    cost: Decimal = Field(ge=0)
    percentage: Decimal = Field(ge=0, le=100)


class ServiceAnalytics(BaseModel):
    """Cost and share for one provider/service pair."""

    model_config = ConfigDict(extra="forbid")

    provider: str
    service_name: str
    cost: Decimal = Field(ge=0)
    percentage: Decimal = Field(ge=0, le=100)


class DailyAnalytics(BaseModel):
    """Total cost for one day."""

    model_config = ConfigDict(extra="forbid")

    date: date
    cost: Decimal = Field(ge=0)


class AnalyticsSummary(BaseModel):
    """Summary metrics for a requested period."""

    model_config = ConfigDict(extra="forbid")

    period: AnalyticsPeriod
    currency: str
    total_cost: Decimal = Field(ge=0)
    provider_count: int = Field(ge=0)
    service_count: int = Field(ge=0)
    providers: list[ProviderAnalytics]
    top_services: list[ServiceAnalytics]


class CostComparison(BaseModel):
    """Comparison metrics between current and previous periods."""

    model_config = ConfigDict(extra="forbid")

    currency: str
    current_period: AnalyticsPeriod
    previous_period: AnalyticsPeriod
    current_period_cost: Decimal
    previous_period_cost: Decimal
    absolute_change: Decimal
    percentage_change: Decimal | None


class CostDriver(BaseModel):
    """A provider, service, or period-over-period cost driver."""

    model_config = ConfigDict(extra="forbid")

    category: Literal["provider", "service"]
    name: str
    provider: str | None = None
    current_cost: Decimal
    previous_cost: Decimal
    absolute_change: Decimal
    percentage_change: Decimal | None


class CostDriversResponse(BaseModel):
    """Top deterministic cost drivers for a period comparison."""

    model_config = ConfigDict(extra="forbid")

    comparison: CostComparison
    drivers: list[CostDriver]
