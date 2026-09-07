"""Contracts for authenticated cost alerts and deterministic evaluations."""

from __future__ import annotations

import uuid
from datetime import date as date_type
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.cost import SupportedProvider


class AlertType(StrEnum):
    COST_THRESHOLD = "cost_threshold"
    COST_INCREASE = "cost_increase"
    ANOMALY = "anomaly"
    FORECAST_THRESHOLD = "forecast_threshold"


class AlertSeverity(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class AlertCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=160)
    alert_type: AlertType
    provider: SupportedProvider | None = None
    account_id: str | None = None
    service: str | None = None
    region: str | None = None
    threshold: Decimal | None = Field(default=None, gt=0)
    percentage: Decimal | None = Field(default=None, gt=0, le=10000)
    severity: AlertSeverity = AlertSeverity.MEDIUM
    enabled: bool = True
    cooldown_minutes: int = Field(default=360, ge=0, le=43200)

    @field_validator("name", "account_id", "service", "region")
    @classmethod
    def strip_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None

    @model_validator(mode="after")
    def validate_condition(self) -> AlertCreate:
        threshold_type = self.alert_type in {
            AlertType.COST_THRESHOLD,
            AlertType.FORECAST_THRESHOLD,
        }
        if threshold_type and self.threshold is None:
            raise ValueError("threshold is required for this alert type")
        if not threshold_type and self.threshold is not None:
            raise ValueError("threshold is only valid for threshold alert types")
        if self.alert_type is AlertType.COST_INCREASE and self.percentage is None:
            raise ValueError("percentage is required for cost increase alerts")
        if (
            self.alert_type is not AlertType.COST_INCREASE
            and self.percentage is not None
        ):
            raise ValueError("percentage is only valid for cost increase alerts")
        return self


class AlertUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=160)
    alert_type: AlertType | None = None
    provider: SupportedProvider | None = None
    account_id: str | None = None
    service: str | None = None
    region: str | None = None
    threshold: Decimal | None = Field(default=None, gt=0)
    percentage: Decimal | None = Field(default=None, gt=0, le=10000)
    severity: AlertSeverity | None = None
    enabled: bool | None = None
    cooldown_minutes: int | None = Field(default=None, ge=0, le=43200)

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str | None) -> str | None:
        return value.strip() if value is not None else None


class AlertResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    name: str
    alert_type: AlertType
    provider: str | None
    account_id: str | None
    service: str | None
    region: str | None
    threshold: Decimal | None
    percentage: Decimal | None
    severity: AlertSeverity
    enabled: bool
    cooldown_minutes: int
    last_triggered_at: datetime | None
    created_at: datetime
    updated_at: datetime


class AlertEvaluationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    start_date: date_type
    end_date: date_type

    @model_validator(mode="after")
    def validate_period(self) -> AlertEvaluationRequest:
        if self.end_date < self.start_date:
            raise ValueError("end_date must be on or after start_date")
        return self


class AlertEvaluationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    alert_id: uuid.UUID
    status: str
    reason: str
    notification_sent: bool = False
    notification_error: str | None = None
    current_value: Decimal | None = None
    threshold: Decimal | None = None
