"""Pydantic v2 schemas for Azure Cost Management API."""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class AzureCostRequest(BaseModel):
    """Request for Azure cost retrieval."""

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
