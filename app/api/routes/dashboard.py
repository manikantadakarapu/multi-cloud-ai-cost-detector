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
from app.services.ai.insights import AIInsightService
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
        ai_service=AIInsightService(cache=cache, user_scope=str(current_user.id)),
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
    query: Annotated[AnalyticsQuery, Depends()],
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
    summary="Return dashboard cost insights",
    description=(
        "Returns rule-based cost increase, decrease, and top-driver insights. "
        "When AI insights are enabled, Gemini explanations of selected cost "
        "events are included. Gemini failures never omit deterministic insights."
    ),
    responses={400: {}, 401: {}, 404: {}, 409: {}, 429: {}, 502: {}},
)
@enforce_cost_rate_limit
async def get_dashboard_insights(
    request: Request,
    query: Annotated[AnalyticsQuery, Depends()],
    service: Annotated[DashboardService, Depends(get_dashboard_service)],
    include_ai: Annotated[bool, Query()] = True,
) -> DashboardInsights:
    """Return deterministic insights and optional Gemini explanations."""
    try:
        return await service.insights(query, include_ai=include_ai)
    except Exception as error:
        _raise_analytics_error(error)
