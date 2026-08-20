"""Authenticated frontend-ready dashboard endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request

from app.api.routes.analytics import _raise_analytics_error
from app.auth.dependencies import get_current_active_user
from app.auth.models import User
from app.core.cache import RedisCache, get_cache
from app.core.rate_limit import enforce_cost_rate_limit
from app.schemas.analytics import AnalyticsQuery
from app.schemas.dashboard import DashboardSummary
from app.schemas.insights import DashboardInsights
from app.services.analytics.service import AnalyticsService
from app.services.dashboard import DashboardService

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


def get_dashboard_service(
    current_user: Annotated[User, Depends(get_current_active_user)],
    cache: Annotated[RedisCache, Depends(get_cache)],
) -> DashboardService:
    """Build a dashboard service scoped to the authenticated user."""
    analytics = AnalyticsService(cache=cache, user_scope=str(current_user.id))
    return DashboardService(
        analytics=analytics,
        cache=cache,
        user_scope=str(current_user.id),
    )


@router.get(
    "/summary",
    response_model=DashboardSummary,
    summary="Return the frontend dashboard summary",
    description=(
        "Returns overview, provider and service breakdowns, daily trend, and "
        "top cost drivers for an authenticated user."
    ),
    responses={400: {}, 401: {}, 404: {}, 409: {}, 429: {}, 502: {}},
)
@enforce_cost_rate_limit
async def get_dashboard_summary(
    request: Request,
    query: Annotated[AnalyticsQuery, Query()],
    service: Annotated[DashboardService, Depends(get_dashboard_service)],
) -> DashboardSummary:
    """Return one stable payload for the initial dashboard view."""
    try:
        return await service.summary(query)
    except Exception as error:
        _raise_analytics_error(error)


@router.get(
    "/insights",
    response_model=DashboardInsights,
    summary="Return deterministic dashboard insights",
    description=(
        "Returns rule-based cost increase, decrease, and top-driver insights. "
        "No AI or machine-learning service is called."
    ),
    responses={400: {}, 401: {}, 404: {}, 409: {}, 429: {}, 502: {}},
)
@enforce_cost_rate_limit
async def get_dashboard_insights(
    request: Request,
    query: Annotated[AnalyticsQuery, Query()],
    service: Annotated[DashboardService, Depends(get_dashboard_service)],
) -> DashboardInsights:
    """Return stable insight objects suitable for a frontend or future AI layer."""
    try:
        return await service.insights(query)
    except Exception as error:
        _raise_analytics_error(error)
