"""Provider-agnostic Pydantic schemas for cloud cost responses.

These models define the normalized shape used across all cloud
provider implementations (AWS, GCP, Azure, etc.). Concrete providers
adapt their vendor-specific responses into these types so the rest of
the application can work against a single, stable contract.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class ServiceCost(BaseModel):
    """Cost breakdown for a single cloud service."""

    model_config = ConfigDict(extra="forbid", from_attributes=True)

    service_name: str = Field(
        ...,
        description="Cloud provider service name (e.g. 'AmazonEC2').",
        examples=["AmazonEC2"],
    )
    cost: float = Field(
        ...,
        ge=0,
        description="Cost in the response currency.",
        examples=[100.50],
    )


class CostResponse(BaseModel):
    """Normalized cost response across all cloud providers."""

    model_config = ConfigDict(extra="forbid")

    provider: str = Field(
        ...,
        description="Cloud provider identifier (e.g. 'aws', 'gcp', 'azure').",
        examples=["aws"],
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
    services: list[ServiceCost] = Field(
        default_factory=list,
        description="Per-service cost breakdown.",
    )
