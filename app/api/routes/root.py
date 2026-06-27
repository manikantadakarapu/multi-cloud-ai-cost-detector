"""Service root route (``GET /``).

Returns a small discovery payload so clients do not have to guess the
location of the API docs or health endpoint.
"""

from fastapi import APIRouter

from app.core.config import settings
from app.schemas.root import RootResponse

router = APIRouter()


@router.get(
    "/",
    response_model=RootResponse,
    include_in_schema=False,
    summary="Service root",
    description="Returns service identity and links to docs and health.",
)
async def root() -> RootResponse:
    """Return a self-describing payload for the API root."""
    return RootResponse(
        name=settings.app_name,
        version=settings.app_version,
        status="running",
        docs="/docs",
        health="/api/v1/health",
    )
