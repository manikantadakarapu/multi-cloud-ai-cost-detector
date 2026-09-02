"""Typed contracts for deterministic cloud cost anomaly detection."""

from __future__ import annotations

from datetime import date as date_type
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.cost import SupportedProvider


class AnomalySeverity(StrEnum):
    NORMAL = "normal"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class DetectionMethod(StrEnum):
    MEDIAN_MAD = "median_mad"
    ZERO_BASELINE = "zero_baseline"


class Anomaly(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    provider: str
    account_id: str | None = None
    account_name: str | None = None
    service: str
    region: str | None = None
    date: date_type
    actual_cost: Decimal = Field(..., ge=0)
    expected_cost: Decimal = Field(..., ge=0)
    deviation_amount: Decimal
    deviation_percentage: Decimal | None = None
    anomaly_score: Decimal = Field(..., ge=0)
    severity: AnomalySeverity
    detection_method: DetectionMethod
    baseline_period: str
    currency: str = "USD"
    created_at: datetime


class AnomalyQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")

    start_date: date_type
    end_date: date_type
    provider: SupportedProvider | None = None
    account_id: str | None = None
    service: str | None = None
    region: str | None = None
    severity: AnomalySeverity | None = None
    sort_by: Annotated[
        str,
        Field(pattern="^(anomaly_score|deviation_percentage|deviation_amount|date)$"),
    ] = "anomaly_score"
    sort_order: Annotated[str, Field(pattern="^(asc|desc)$")] = "desc"

    @field_validator("account_id", "service", "region")
    @classmethod
    def clean_filter(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None

    @model_validator(mode="after")
    def validate_period(self) -> AnomalyQuery:
        if self.end_date < self.start_date:
            raise ValueError("end_date must be on or after start_date")
        return self


class AnomalySummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    total: int = Field(..., ge=0)
    high_or_critical: int = Field(..., ge=0)
    by_severity: dict[AnomalySeverity, int]


class AnomalyTrendPoint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    date: date_type
    count: int = Field(..., ge=0)


class AnomalyResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    anomalies: list[Anomaly]
    summary: AnomalySummary
    trend: list[AnomalyTrendPoint]
    start_date: date_type
    end_date: date_type
    baseline_lookback_days: int = Field(..., ge=1)
    detector_version: str
