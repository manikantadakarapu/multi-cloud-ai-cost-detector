"""Pydantic v2 schemas for the unified multi-cloud cost API.

The unified endpoint accepts a provider name plus a date range and
granularity, and returns the shared :class:`CostResponse` shape used
by every concrete cloud provider. This module defines only the request
schema; the response schema lives in
:mod:`app.providers.schemas` so all providers and all endpoints share
a single response contract.
"""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

SupportedProvider = Literal["aws", "azure", "gcp"]
"""Provider names accepted by the unified cost endpoint."""

__all__ = ["SupportedProvider", "UnifiedCostRequest"]


class UnifiedCostRequest(BaseModel):
    """Query parameters for ``GET /api/v1/costs``.

    The ``provider`` field is part of the query string (rather than the
    path) so a single route can dispatch to any registered provider.
    Validation here happens before the handler runs, so an unsupported
    provider surfaces as a ``422`` validation error from FastAPI before
    :class:`~app.providers.exceptions.ProviderNotSupportedException`
    ever fires — the resolver-level check exists as a defence-in-depth
    for non-HTTP callers (e.g. internal services).
    """

    model_config = ConfigDict(extra="forbid")

    provider: SupportedProvider = Field(
        ...,
        description="Cloud provider to retrieve costs from.",
        examples=["aws"],
    )
    start_date: date = Field(
        ...,
        description="Start date for cost retrieval (inclusive).",
        examples=["2026-07-01"],
    )
    end_date: date = Field(
        ...,
        description="End date for cost retrieval (inclusive).",
        examples=["2026-07-31"],
    )
    granularity: Literal["DAILY", "MONTHLY"] = Field(
        default="DAILY",
        description="Granularity of cost data.",
        examples=["DAILY"],
    )

    @field_validator("end_date")
    @classmethod
    def end_after_start(cls, v: date, info) -> date:
        """Ensure ``end_date`` is on or after ``start_date``."""
        if info.data.get("start_date") and v < info.data["start_date"]:
            raise ValueError("end_date must be on or after start_date")
        return v
