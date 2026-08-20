"""SlowAPI integration for cost-query rate limits."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import Request, status
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.core.config import settings

limiter = Limiter(key_func=get_remote_address, default_limits=[])


def cost_rate_limit() -> str:
    """Return the configured per-client limit for a cost endpoint."""
    return f"{settings.rate_limit_per_minute}/minute"


def enforce_cost_rate_limit(func: Callable[..., Any]) -> Callable[..., Any]:
    """Apply the configured SlowAPI limit to a cost route handler."""
    return limiter.limit(cost_rate_limit)(func)


def auth_rate_limit() -> str:
    """Return the configured per-client limit for an auth endpoint."""
    return f"{settings.auth_rate_limit_per_minute}/minute"


def enforce_auth_rate_limit(func: Callable[..., Any]) -> Callable[..., Any]:
    """Apply the configured SlowAPI limit to an auth route handler."""
    return limiter.limit(auth_rate_limit)(func)


def reset_rate_limits() -> None:
    """Clear limiter state to isolate test cases."""
    limiter._storage.reset()  # noqa: SLF001 - SlowAPI exposes no public reset API.


def configure_rate_limiting(app: Any) -> None:
    """Register the SlowAPI limiter and its HTTP 429 response handler."""
    app.state.limiter = limiter

    @app.exception_handler(RateLimitExceeded)
    async def _rate_limit_handler(_: Request, __: Exception) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            content={"detail": "Rate limit exceeded"},
        )
