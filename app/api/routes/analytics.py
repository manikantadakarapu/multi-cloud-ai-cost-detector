"""Authenticated deterministic cost analytics endpoints."""

from __future__ import annotations

from typing import Annotated, NoReturn

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from app.auth.dependencies import get_current_active_user
from app.auth.models import User
from app.core.cache import RedisCache, get_cache
from app.core.rate_limit import enforce_cost_rate_limit
from app.providers.exceptions import (
    ProviderCredentialsError,
    ProviderInvalidDateRangeError,
    ProviderPermissionsError,
    ProviderServiceError,
    ProviderThrottlingError,
)
from app.schemas.analytics import (
    AnalyticsQuery,
    AnalyticsSummary,
    ComparisonQuery,
    CostComparison,
    CostDriversResponse,
    DailyAnalytics,
    ProviderAnalytics,
    ServiceAnalytics,
)
from app.services.analytics.exceptions import (
    AnalyticsCurrencyError,
    AnalyticsError,
    AnalyticsNoDataError,
)
from app.services.analytics.service import AnalyticsService

router = APIRouter(prefix="/analytics", tags=["analytics"])


def get_analytics_service(
    current_user: Annotated[User, Depends(get_current_active_user)],
    cache: Annotated[RedisCache, Depends(get_cache)],
) -> AnalyticsService:
    """Build an analytics service scoped to the authenticated user."""
    return AnalyticsService(cache=cache, user_scope=str(current_user.id))


def _raise_analytics_error(error: Exception) -> NoReturn:
    """Translate domain and provider failures into stable HTTP responses."""
    if isinstance(error, AnalyticsCurrencyError):
        code = error.error_code
        http_status = status.HTTP_409_CONFLICT
        detail = error.message
    elif isinstance(error, AnalyticsNoDataError):
        code = error.error_code
        http_status = status.HTTP_404_NOT_FOUND
        detail = error.message
    elif isinstance(error, AnalyticsError):
        code = error.error_code
        http_status = status.HTTP_400_BAD_REQUEST
        detail = error.message
    elif isinstance(error, ProviderInvalidDateRangeError):
        code = error.error_code
        http_status = status.HTTP_400_BAD_REQUEST
        detail = error.message
    elif isinstance(error, ProviderCredentialsError):
        code = error.error_code
        http_status = status.HTTP_500_INTERNAL_SERVER_ERROR
        detail = error.message
    elif isinstance(error, ProviderThrottlingError):
        code = error.error_code
        http_status = status.HTTP_429_TOO_MANY_REQUESTS
        detail = error.message
    elif isinstance(error, ProviderPermissionsError):
        code = error.error_code
        http_status = status.HTTP_403_FORBIDDEN
        detail = error.message
    elif isinstance(error, ProviderServiceError):
        code = error.error_code
        http_status = status.HTTP_502_BAD_GATEWAY
        detail = error.message
    else:
        raise error
    raise HTTPException(
        status_code=http_status,
        detail=detail,
        headers={"X-Error-Code": code},
    ) from error


@router.get(
    "/summary",
    response_model=AnalyticsSummary,
    summary="Summarize multi-cloud costs",
    responses={400: {}, 401: {}, 404: {}, 409: {}, 429: {}, 502: {}},
)
@enforce_cost_rate_limit
async def get_summary(
    request: Request,
    query: Annotated[AnalyticsQuery, Query()],
    service: Annotated[AnalyticsService, Depends(get_analytics_service)],
) -> AnalyticsSummary:
    """Return total, provider, and top-service cost metrics."""
    try:
        return await service.summary(query)
    except Exception as error:
        _raise_analytics_error(error)


@router.get(
    "/providers",
    response_model=list[ProviderAnalytics],
    summary="Break down costs by provider",
)
@enforce_cost_rate_limit
async def get_provider_breakdown(
    request: Request,
    query: Annotated[AnalyticsQuery, Query()],
    service: Annotated[AnalyticsService, Depends(get_analytics_service)],
) -> list[ProviderAnalytics]:
    """Return provider totals and percentage contribution."""
    try:
        return await service.providers(query)
    except Exception as error:
        _raise_analytics_error(error)


@router.get(
    "/services",
    response_model=list[ServiceAnalytics],
    summary="Break down costs by service",
)
@enforce_cost_rate_limit
async def get_service_breakdown(
    request: Request,
    query: Annotated[AnalyticsQuery, Query()],
    service: Annotated[AnalyticsService, Depends(get_analytics_service)],
) -> list[ServiceAnalytics]:
    """Return the highest-cost provider/service pairs."""
    try:
        return await service.services(query)
    except Exception as error:
        _raise_analytics_error(error)


@router.get(
    "/trends",
    response_model=list[DailyAnalytics],
    summary="Return daily cost trends",
)
@enforce_cost_rate_limit
async def get_trends(
    request: Request,
    query: Annotated[AnalyticsQuery, Query()],
    service: Annotated[AnalyticsService, Depends(get_analytics_service)],
) -> list[DailyAnalytics]:
    """Return one deterministic total for every day in the requested period."""
    try:
        return await service.trends(query)
    except Exception as error:
        _raise_analytics_error(error)


@router.get(
    "/compare",
    response_model=CostComparison,
    summary="Compare two cost periods",
)
@enforce_cost_rate_limit
async def compare_periods(
    request: Request,
    query: Annotated[ComparisonQuery, Query()],
    service: Annotated[AnalyticsService, Depends(get_analytics_service)],
) -> CostComparison:
    """Return absolute and percentage change between two periods."""
    try:
        return await service.compare(query)
    except Exception as error:
        _raise_analytics_error(error)


@router.get(
    "/drivers",
    response_model=CostDriversResponse,
    summary="Identify top cost drivers",
)
@enforce_cost_rate_limit
async def cost_drivers(
    request: Request,
    query: Annotated[ComparisonQuery, Query()],
    service: Annotated[AnalyticsService, Depends(get_analytics_service)],
) -> CostDriversResponse:
    """Return providers and services with the largest cost changes."""
    try:
        return await service.drivers(query, top_n=query.top_n)
    except Exception as error:
        _raise_analytics_error(error)
