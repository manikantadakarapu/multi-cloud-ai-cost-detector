"""Response model for the health check endpoint (``GET /api/v1/health``)."""

from typing import Literal

from pydantic import BaseModel, ConfigDict


class HealthCheckResponse(BaseModel):
    """Production health payload.

    ``status`` is ``"healthy"`` only when the database round-trip and Redis
    health check succeed; otherwise the route returns HTTP 503 with
    ``status="unhealthy"``.
    ``database`` and ``redis`` mirror the underlying dependency states so
    monitoring tools can distinguish "app up, dependency down" from a fully
    healthy service.
    """

    model_config = ConfigDict(extra="forbid")

    status: Literal["healthy", "unhealthy"]
    database: Literal["up", "down"]
    redis: Literal["up", "down"]
    application: Literal["up", "down"]
    version: str
    environment: str
    timestamp: str
