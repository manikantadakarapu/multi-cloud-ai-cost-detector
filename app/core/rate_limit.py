"""SlowAPI integration for cost-query rate limits."""

from __future__ import annotations

import types
from collections.abc import Callable
from typing import Any

from fastapi import Request, status
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from starlette.responses import Response

from app.core.config import settings

limiter = Limiter(key_func=get_remote_address, default_limits=[])


def cost_rate_limit() -> str:
    """Return the configured per-client limit for a cost endpoint."""
    return f"{settings.rate_limit_per_minute}/minute"


def _bind_rate_limit(
    wrapper: Callable[..., Any], func: Callable[..., Any]
) -> Callable[..., Any]:
    """Rebind SlowAPI wrapper to original function globals for FastAPI annotation resolution."""
    globals_dict = dict(func.__globals__)
    globals_dict.setdefault("Response", Response)
    bound = types.FunctionType(
        wrapper.__code__,
        globals_dict,
        wrapper.__name__,
        wrapper.__defaults__,
        wrapper.__closure__,
    )
    bound.__dict__.update(wrapper.__dict__)
    bound.__annotations__ = func.__annotations__
    bound.__wrapped__ = func
    bound.__kwdefaults__ = getattr(wrapper, "__kwdefaults__", None)
    return bound


def enforce_cost_rate_limit(func: Callable[..., Any]) -> Callable[..., Any]:
    """Apply the configured SlowAPI limit to a cost route handler."""
    wrapper = limiter.limit(cost_rate_limit)(func)
    return _bind_rate_limit(wrapper, func)


def auth_rate_limit() -> str:
    """Return the configured per-client limit for an auth endpoint."""
    return f"{settings.auth_rate_limit_per_minute}/minute"


def enforce_auth_rate_limit(func: Callable[..., Any]) -> Callable[..., Any]:
    """Apply the configured SlowAPI limit to an auth route handler."""
    wrapper = limiter.limit(auth_rate_limit)(func)
    return _bind_rate_limit(wrapper, func)


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
