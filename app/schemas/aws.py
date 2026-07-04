"""Pydantic v2 schemas for AWS Cost Explorer API."""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class AWSCostRequest(BaseModel):
    """Request for AWS cost retrieval."""

    model_config = ConfigDict(extra="forbid")

    start_date: date = Field(
        ...,
        description="Start date for cost retrieval (inclusive).",
        examples=["2024-01-01"],
    )
    end_date: date = Field(
        ...,
        description="End date for cost retrieval (inclusive).",
        examples=["2024-01-31"],
    )
    granularity: Literal["DAILY", "MONTHLY"] = Field(
        default="DAILY",
        description="Granularity of cost data.",
        examples=["DAILY"],
    )

    @field_validator("end_date")
    @classmethod
    def end_after_start(cls, v: date, info) -> date:
        if info.data.get("start_date") and v < info.data["start_date"]:
            raise ValueError("end_date must be on or after start_date")
        return v


class AWSServiceCost(BaseModel):
    """Cost breakdown for a single AWS service."""

    model_config = ConfigDict(extra="forbid", from_attributes=True)

    service_name: str = Field(
        ...,
        description="AWS service name.",
        examples=["AmazonEC2"],
    )
    cost: float = Field(
        ...,
        ge=0,
        description="Cost in the response currency.",
        examples=[100.50],
    )


class AWSCostResponse(BaseModel):
    """Normalized AWS cost response."""

    model_config = ConfigDict(extra="forbid")

    provider: Literal["aws"] = Field(
        default="aws",
        description="Cloud provider identifier.",
    )
    currency: str = Field(
        default="USD",
        description="Currency code for costs.",
        examples=["USD"],
    )
    total_cost: float = Field(
        ...,
        ge=0,
        description="Total cost across all services.",
        examples=[150.75],
    )
    date_range: dict[str, str] = Field(
        ...,
        description="Date range and granularity of the query.",
        examples=[
            {
                "start": "2024-01-01",
                "end": "2024-01-31",
                "granularity": "DAILY",
            }
        ],
    )
    services: list[AWSServiceCost] = Field(
        default_factory=list,
        description="Per-service cost breakdown.",
    )
