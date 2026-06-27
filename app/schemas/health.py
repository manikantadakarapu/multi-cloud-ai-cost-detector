"""Response model for the health check endpoint (``GET /api/v1/health``)."""

from typing import Literal

from pydantic import BaseModel, ConfigDict


class HealthCheckResponse(BaseModel):
    """Production health payload.

    ``status`` is ``"healthy"`` only when the database round-trip succeeds;
    otherwise the route returns HTTP 503 with ``status="unhealthy"``.
    ``database`` mirrors the underlying connectivity state so monitoring
    tools can distinguish "app up, DB down" from a fully healthy service.
    """

    model_config = ConfigDict(extra="forbid")

    status: Literal["healthy", "unhealthy"]
    database: Literal["connected", "disconnected"]
    version: str
    environment: str
    timestamp: str
