"""Provider-independent deterministic cost-change events."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class CostEventType(StrEnum):
    """Meaningful period-over-period cost movements selected without an LLM."""

    COST_INCREASE = "cost_increase"
    COST_DECREASE = "cost_decrease"


class CostEvent(BaseModel):
    """A typed cost change derived from analytics, never from raw provider SDKs."""

    model_config = ConfigDict(extra="forbid")

    event_type: CostEventType
    provider: str | None = None
    service: str | None = None
    current_cost: Decimal
    previous_cost: Decimal = Field(ge=0)
    absolute_change: Decimal
    percentage_change: Decimal | None = None
    currency: str
    period_start: date
    period_end: date
