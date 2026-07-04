"""Health check route (``GET /api/v1/health``).

A production-style readiness probe: it performs a real database round-trip
and returns HTTP 503 when the dependency is unavailable, so load balancers
and orchestrators can pull the instance out of rotation.
"""

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api.deps import get_session_factory
from app.schemas.health import HealthCheckResponse
from app.services.health import HealthService

router = APIRouter()


@router.get(
    "/health",
    response_model=HealthCheckResponse,
    summary="Service health",
    description=(
        "Returns the service health status. Performs a database round-trip "
        "(``SELECT 1``) on every call. Responds with HTTP 503 when the "
        "database is unreachable so upstream proxies can drain traffic."
    ),
)
async def health_check(
    response: Response,
    session_factory: async_sessionmaker[AsyncSession] = Depends(  # noqa: B008
        get_session_factory,
    ),
) -> HealthCheckResponse:
    """Probe database connectivity and report aggregate service health."""
    health = HealthService(session_factory)
    payload = await health.get_status()

    if payload["status"] != "healthy":
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return HealthCheckResponse(**payload)
