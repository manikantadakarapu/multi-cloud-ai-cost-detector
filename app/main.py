"""FastAPI application factory.

The application is constructed via :func:`create_app` so it can be imported
by ASGI servers (``uvicorn app.main:app``) and test clients alike. All
wiring — logging, lifespan hooks, routers, and OpenAPI metadata — happens
here to keep route modules focused on HTTP concerns.
"""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.alerts.scheduler import run_alert_scheduler
from app.api.router import api_router
from app.api.routes.root import router as root_router
from app.core.cache import shutdown_cache, startup_cache
from app.core.config import settings
from app.core.logging import configure_logging, get_logger
from app.core.openapi import configure_openapi
from app.core.rate_limit import configure_rate_limiting
from app.database.session import dispose_engine
from app.providers import list_providers


def _normalise_cors_origins(origins: list[object]) -> list[str]:
    """Return browser-compatible origins without a trailing slash."""
    return [str(origin).rstrip("/") for origin in origins]


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    configure_logging()
    logger = get_logger(__name__)
    registered_providers = list_providers()
    logger.info(
        "application_starting",
        extra={
            "app_name": settings.app_name,
            "app_env": settings.app_env,
            "app_version": settings.app_version,
            "registered_providers": registered_providers,
        },
    )
    scheduler_stop = asyncio.Event()
    scheduler_task: asyncio.Task[None] | None = None
    try:
        await startup_cache()
        if settings.alerts_scheduler_enabled:
            scheduler_task = asyncio.create_task(run_alert_scheduler(scheduler_stop))
        yield
    finally:
        if scheduler_task is not None:
            scheduler_stop.set()
            scheduler_task.cancel()
            await asyncio.gather(scheduler_task, return_exceptions=True)
        await shutdown_cache()
        await dispose_engine()
        logger.info("application_stopped")


def create_app() -> FastAPI:
    application = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        debug=settings.app_debug,
        lifespan=lifespan,
    )

    # CORS — allow the configured origins. In production this is an explicit
    # allow-list; in local/dev it typically includes localhost front-ends.
    application.add_middleware(
        CORSMiddleware,
        allow_origins=_normalise_cors_origins(settings.cors_origins),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    application.include_router(root_router)
    application.include_router(api_router)
    configure_rate_limiting(application)
    configure_openapi(application)
    return application


app = create_app()
