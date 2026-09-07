"""Provider-independent contracts for deterministic cost forecasting."""

from __future__ import annotations

from datetime import date as date_type
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.cost import SupportedProvider


class ForecastStatus(StrEnum):
    READY = "ready"
    INSUFFICIENT_DATA = "insufficient_data"
    EMPTY = "empty"


class ForecastDimension(StrEnum):
    TOTAL = "total"
    PROVIDER = "provider"
    SERVICE = "service"
    ACCOUNT = "account"
    REGION = "region"


class ForecastQuery(BaseModel):
    """Validated historical period and forecast parameters."""

    model_config = ConfigDict(extra="forbid")

    start_date: date_type
    end_date: date_type
    horizon_days: int = Field(default=7, ge=7, le=30)
    provider: SupportedProvider | None = None
    account_id: str | None = None
    service: str | None = None
    region: str | None = None
    currency: str | None = None
    dimension: ForecastDimension = ForecastDimension.TOTAL

    @field_validator("account_id", "service", "region", "currency")
    @classmethod
    def strip_filters(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None

    @field_validator("horizon_days")
    @classmethod
    def supported_horizon(cls, value: int) -> int:
        if value not in {7, 14, 30}:
            raise ValueError("horizon_days must be one of 7, 14, or 30")
        return value

    @model_validator(mode="after")
    def validate_period(self) -> ForecastQuery:
        if self.end_date < self.start_date:
            raise ValueError("end_date must be on or after start_date")
        return self


class DailyForecast(BaseModel):
    model_config = ConfigDict(extra="forbid")

    date: date_type
    actual_cost: Decimal | None = Field(default=None, ge=0)
    forecast_cost: Decimal = Field(ge=0)
    lower_bound: Decimal = Field(ge=0)
    upper_bound: Decimal = Field(ge=0)

    @model_validator(mode="after")
    def validate_bounds(self) -> DailyForecast:
        if (
            self.lower_bound > self.forecast_cost
            or self.forecast_cost > self.upper_bound
        ):
            raise ValueError("forecast bounds must contain the forecast cost")
        return self


class DailyActual(BaseModel):
    model_config = ConfigDict(extra="forbid")

    date: date_type
    cost: Decimal = Field(ge=0)


class ForecastAccuracy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    observations: int = Field(ge=0)
    mean_absolute_error: Decimal = Field(ge=0)
    mean_absolute_percentage_error: Decimal | None = Field(default=None, ge=0)


class ForecastResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    forecast_id: str
    dimension: ForecastDimension
    dimension_value: str
    provider: str | None = None
    account_id: str | None = None
    service: str | None = None
    region: str | None = None
    forecast_start: date_type
    forecast_end: date_type
    horizon_days: int = Field(ge=1, le=30)
    currency: str
    historical_cost: Decimal = Field(ge=0)
    projected_cost: Decimal = Field(ge=0)
    daily_forecast: list[DailyForecast]
    historical_daily: list[DailyActual] = Field(default_factory=list)
    lower_bound: Decimal = Field(ge=0)
    upper_bound: Decimal = Field(ge=0)
    methodology: str
    confidence: Literal["low", "medium", "high"]
    data_points_used: int = Field(ge=0)
    generated_at: datetime
    excluded_anomaly_dates: list[date_type] = Field(default_factory=list)
    missing_dates: list[date_type] = Field(default_factory=list)
    accuracy: ForecastAccuracy | None = None

    @model_validator(mode="after")
    def validate_total_bounds(self) -> ForecastResult:
        if (
            self.lower_bound > self.projected_cost
            or self.projected_cost > self.upper_bound
        ):
            raise ValueError("forecast bounds must contain the projected cost")
        return self


class ForecastSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    current_spend: Decimal = Field(ge=0)
    projected_spend: Decimal = Field(ge=0)
    projected_change_percentage: Decimal | None = None
    average_historical_daily_cost: Decimal = Field(ge=0)
    projected_daily_average: Decimal = Field(ge=0)
    confidence: Literal["low", "medium", "high"] | None = None
    data_points_used: int = Field(ge=0)


class ForecastDataQuality(BaseModel):
    model_config = ConfigDict(extra="forbid")

    available_observations: int = Field(ge=0)
    required_observations: int = Field(ge=1)
    missing_dates: list[date_type] = Field(default_factory=list)
    duplicate_records_removed: int = Field(ge=0)
    excluded_anomaly_dates: list[date_type] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class ForecastResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: ForecastStatus
    query: ForecastQuery
    summary: ForecastSummary
    forecasts: list[ForecastResult] = Field(default_factory=list)
    data_quality: ForecastDataQuality
    methodology_version: str
    message: str | None = None
