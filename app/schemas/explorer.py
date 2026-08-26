"""Provider-independent contracts for Cost Explorer and drill-down analysis."""

from __future__ import annotations

from datetime import date as date_type
from decimal import Decimal
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.cost import SupportedProvider


class ExplorerDimension(StrEnum):
    """Supported aggregation dimensions for cost exploration."""

    PROVIDER = "provider"
    ACCOUNT = "account"
    SERVICE = "service"
    REGION = "region"
    DATE = "date"


class CostRecord(BaseModel):
    """A single normalized cost line-item record."""

    model_config = ConfigDict(extra="forbid")

    date: date_type = Field(..., description="Date of the cost line item.")
    provider: str = Field(
        ...,
        description="Cloud provider identifier (e.g. 'aws', 'azure', 'gcp').",
    )
    account_id: str | None = Field(
        default=None,
        description="Cloud account / subscription / project identifier.",
    )
    account_name: str | None = Field(
        default=None,
        description="Human-readable account or project name.",
    )
    service: str = Field(
        ...,
        description="Cloud service name (e.g. 'AmazonEC2', 'Virtual Machines').",
    )
    region: str | None = Field(
        default=None,
        description="Cloud region identifier (e.g. 'us-east-1', 'eastus').",
    )
    cost: Decimal = Field(
        ..., ge=0, description="Cost amount in the response currency."
    )
    currency: str = Field(default="USD", description="Currency code (e.g. 'USD').")


class DimensionTotal(BaseModel):
    """Aggregated cost summary for a single dimension key."""

    model_config = ConfigDict(extra="forbid")

    key: str = Field(..., description="Dimension key identifier.")
    label: str = Field(..., description="Human-readable label.")
    cost: Decimal = Field(..., ge=0, description="Total cost for this key.")
    percentage: Decimal = Field(
        ...,
        ge=0,
        le=100,
        description="Percentage of total filtered spend.",
    )
    currency: str = Field(default="USD", description="Currency code.")
    record_count: int = Field(
        default=1, ge=0, description="Number of contributing records."
    )


class DailyCostRecord(BaseModel):
    """Daily cost total for trend visualization."""

    model_config = ConfigDict(extra="forbid")

    date: date_type = Field(..., description="Calendar date.")
    cost: Decimal = Field(..., ge=0, description="Cost for the day.")
    currency: str = Field(default="USD", description="Currency code.")


class DimensionBreakdowns(BaseModel):
    """Multi-dimensional rollups across provider, service, region, account, and date."""

    model_config = ConfigDict(extra="forbid")

    by_provider: list[DimensionTotal] = Field(
        default_factory=list, description="Breakdown by provider."
    )
    by_service: list[DimensionTotal] = Field(
        default_factory=list, description="Breakdown by service."
    )
    by_region: list[DimensionTotal] = Field(
        default_factory=list, description="Breakdown by region."
    )
    by_account: list[DimensionTotal] = Field(
        default_factory=list, description="Breakdown by account/project."
    )
    by_date: list[DailyCostRecord] = Field(
        default_factory=list, description="Daily cost trend."
    )


class ExplorerOverview(BaseModel):
    """Top-level aggregate metrics for the active filter set."""

    model_config = ConfigDict(extra="forbid")

    total_cost: Decimal = Field(
        ..., ge=0, description="Total cost for the filtered query."
    )
    currency: str = Field(default="USD", description="Currency code.")
    record_count: int = Field(
        ..., ge=0, description="Total number of matching line-item records."
    )
    start_date: date_type = Field(..., description="Query period start date.")
    end_date: date_type = Field(..., description="Query period end date.")


class AvailableFilters(BaseModel):
    """Discovered filter options for interactive UI drill-down dropdowns."""

    model_config = ConfigDict(extra="forbid")

    providers: list[str] = Field(
        default_factory=list, description="Available providers."
    )
    accounts: list[str] = Field(
        default_factory=list, description="Available accounts / projects."
    )
    services: list[str] = Field(default_factory=list, description="Available services.")
    regions: list[str] = Field(default_factory=list, description="Available regions.")


class ExplorerQuery(BaseModel):
    """Validated query parameters for the Cost Explorer API."""

    model_config = ConfigDict(extra="forbid")

    start_date: date_type = Field(..., description="Period start date, inclusive.")
    end_date: date_type = Field(..., description="Period end date, inclusive.")
    provider: SupportedProvider | None = Field(
        default=None,
        description="Optional provider filter ('aws', 'azure', 'gcp').",
    )
    account_id: str | None = Field(
        default=None,
        description="Optional account, subscription, or project filter.",
    )
    service: str | None = Field(
        default=None, description="Optional service name filter."
    )
    region: str | None = Field(
        default=None,
        description="Optional region identifier filter.",
    )
    granularity: Literal["DAILY", "MONTHLY"] = Field(
        default="DAILY", description="Time granularity."
    )
    limit: int = Field(
        default=100,
        ge=1,
        le=1000,
        description="Maximum number of line items to return.",
    )
    offset: int = Field(default=0, ge=0, description="Pagination offset.")

    @field_validator("service", "region", "account_id")
    @classmethod
    def strip_whitespace(cls, value: str | None) -> str | None:
        if value is not None:
            stripped = value.strip()
            return stripped if stripped else None
        return None

    @model_validator(mode="after")
    def validate_period(self) -> ExplorerQuery:
        if self.end_date < self.start_date:
            raise ValueError("end_date must be on or after start_date")
        return self


class ExplorerResponse(BaseModel):
    """Normalized response payload for the Cost Explorer API."""

    model_config = ConfigDict(extra="forbid")

    overview: ExplorerOverview = Field(
        ..., description="Aggregate overview of filtered spend."
    )
    records: list[CostRecord] = Field(
        default_factory=list, description="Paginated line-item records."
    )
    dimension_totals: DimensionBreakdowns = Field(
        ...,
        description="Breakdowns by provider, service, region, account, and date.",
    )
    available_filters: AvailableFilters = Field(
        ..., description="Filter options available in the result set."
    )
    total_records: int = Field(
        ..., ge=0, description="Total matching records across all pages."
    )
    limit: int = Field(..., ge=1, description="Page limit applied.")
    offset: int = Field(..., ge=0, description="Page offset applied.")
