"""Contracts for authenticated budgets and deterministic guardrails."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.cost import SupportedProvider


class BudgetScope(StrEnum):
    TOTAL = "total"
    PROVIDER = "provider"
    ACCOUNT = "account"
    SERVICE = "service"
    REGION = "region"


class BudgetPeriod(StrEnum):
    MONTHLY = "monthly"


class BudgetStatus(StrEnum):
    HEALTHY = "healthy"
    WARNING = "warning"
    CRITICAL = "critical"
    EXCEEDED = "exceeded"
    UNAVAILABLE = "unavailable"
    DISABLED = "disabled"


class BudgetCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=160)
    scope: BudgetScope = BudgetScope.TOTAL
    provider: SupportedProvider | None = None
    account_id: str | None = None
    service: str | None = None
    region: str | None = None
    period: BudgetPeriod = BudgetPeriod.MONTHLY
    amount: Decimal = Field(gt=0)
    currency: str = Field(default="USD", min_length=3, max_length=3)
    warning_threshold: Decimal = Field(default=Decimal("80"), ge=0, le=100)
    critical_threshold: Decimal = Field(default=Decimal("90"), gt=0, le=100)
    enabled: bool = True

    @field_validator("name", "account_id", "service", "region")
    @classmethod
    def strip_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        value = value.strip().upper()
        if len(value) != 3 or not value.isalpha():
            raise ValueError("currency must be a three-letter code")
        return value

    @model_validator(mode="after")
    def validate_thresholds(self) -> BudgetCreate:
        if self.critical_threshold <= self.warning_threshold:
            raise ValueError(
                "critical_threshold must be greater than warning_threshold"
            )
        return self


class BudgetUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=160)
    scope: BudgetScope | None = None
    provider: SupportedProvider | None = None
    account_id: str | None = None
    service: str | None = None
    region: str | None = None
    period: BudgetPeriod | None = None
    amount: Decimal | None = Field(default=None, gt=0)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    warning_threshold: Decimal | None = Field(default=None, ge=0, le=100)
    critical_threshold: Decimal | None = Field(default=None, gt=0, le=100)
    enabled: bool | None = None

    @field_validator("name", "account_id", "service", "region")
    @classmethod
    def strip_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip().upper()
        if len(value) != 3 or not value.isalpha():
            raise ValueError("currency must be a three-letter code")
        return value


class BudgetResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    name: str
    scope: BudgetScope
    provider: str | None
    account_id: str | None
    service: str | None
    region: str | None
    period: BudgetPeriod
    amount: Decimal
    currency: str
    warning_threshold: Decimal
    critical_threshold: Decimal
    enabled: bool
    created_at: datetime
    updated_at: datetime


class BudgetEvaluation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    budget_id: uuid.UUID
    actual_spend: Decimal = Field(ge=0)
    budget_amount: Decimal = Field(gt=0)
    actual_utilization: Decimal = Field(ge=0)
    actual_remaining: Decimal
    actual_status: BudgetStatus
    forecast_spend: Decimal | None = Field(default=None, ge=0)
    forecast_variance: Decimal | None = None
    forecast_status: BudgetStatus
    evaluation_period: str
    currency: str
    scope: str
    reason: str
    data_available: bool
    forecast_available: bool
    evaluated_at: datetime


class BudgetEvaluationError(Exception):
    """Raised when verified budget input data cannot be evaluated safely."""


def validate_budget_update(values: dict[str, object]) -> None:
    BudgetCreate.model_validate(values)
