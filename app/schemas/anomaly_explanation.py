"""Contracts for deterministic anomaly investigation context and AI explanations."""

from __future__ import annotations

from datetime import date as date_type
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.anomaly import Anomaly, AnomalySeverity
from app.schemas.cost import SupportedProvider


class EvidenceStatus(StrEnum):
    VERIFIED = "verified"
    DERIVED = "derived"
    UNKNOWN = "unknown"


class ExplanationConfidence(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ExplanationStatus(StrEnum):
    READY = "ready"
    DISABLED = "disabled"
    UNAVAILABLE = "unavailable"
    TIMEOUT = "timeout"
    INVALID = "invalid"
    NOT_FOUND = "not_found"


class EvidenceItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str = Field(min_length=1, max_length=120)
    value: str = Field(min_length=1, max_length=400)
    status: EvidenceStatus


class BreakdownEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dimension: str
    value: str
    current_cost: Decimal = Field(ge=0)
    baseline_cost: Decimal = Field(ge=0)
    change_amount: Decimal
    change_percentage: Decimal | None = None
    share_of_increment: Decimal | None = Field(default=None, ge=0, le=100)


class DailyEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    date: date_type
    cost: Decimal


class AnomalyInvestigationContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    context_version: str
    anomaly: Anomaly
    evidence: list[EvidenceItem]
    daily_costs: list[DailyEvidence]
    service_changes: list[BreakdownEvidence] = Field(default_factory=list)
    region_changes: list[BreakdownEvidence] = Field(default_factory=list)
    provider_changes: list[BreakdownEvidence] = Field(default_factory=list)
    unknowns: list[str] = Field(default_factory=list)


class AnomalyExplanationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    start_date: date_type
    end_date: date_type
    provider: SupportedProvider | None = None
    account_id: str | None = None
    service: str | None = None
    region: str | None = None
    severity: AnomalySeverity | None = None

    @field_validator("account_id", "service", "region")
    @classmethod
    def clean_filter(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None

    @model_validator(mode="after")
    def validate_period(self) -> AnomalyExplanationRequest:
        if self.end_date < self.start_date:
            raise ValueError("end_date must be on or after start_date")
        return self


class LikelyCause(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cause: str = Field(min_length=1, max_length=400)
    evidence: str = Field(min_length=1, max_length=400)
    confidence: ExplanationConfidence


class AnomalyExplanationDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary: str = Field(min_length=1, max_length=600)
    likely_causes: list[LikelyCause] = Field(min_length=1, max_length=5)
    impact: str = Field(min_length=1, max_length=400)
    investigation_steps: list[str] = Field(min_length=1, max_length=8)
    confidence: ExplanationConfidence
    limitations: list[str] = Field(default_factory=list, max_length=8)


class AnomalyExplanationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    anomaly: Anomaly
    context: AnomalyInvestigationContext
    status: ExplanationStatus
    summary: str | None = None
    likely_causes: list[LikelyCause] = Field(default_factory=list)
    impact: str | None = None
    investigation_steps: list[str] = Field(default_factory=list)
    confidence: ExplanationConfidence | None = None
    limitations: list[str] = Field(default_factory=list)
    generated_at: datetime | None = None
    model: str | None = None
    prompt_version: str
    fallback_message: str | None = None
