"""Aggregated API router.

All feature routers are mounted under the ``/api/v1`` prefix here so the
versioned path (e.g. ``/api/v1/health``) is defined in exactly one place.
The root discovery route (``GET /``) is mounted directly on the application
in :mod:`app.main`, not here, because it lives at ``/`` rather than under
``/api/v1``.
"""

from fastapi import APIRouter

from app.api.routes.health import router as health_router
from app.auth.router import router as auth_router

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(health_router, tags=["health"])
api_router.include_router(auth_router)
