"""Authenticated advisory FinOps recommendation routes."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.auth.dependencies import get_current_active_user
from app.auth.models import User
from app.core.cache import RedisCache, get_cache
from app.core.rate_limit import enforce_cost_rate_limit
from app.schemas.optimization import (
    OptimizationQuery,
    OptimizationResponse,
    Recommendation,
    RecommendationStatusUpdate,
)
from app.schemas.optimization_advisor import (
    OptimizationAdvisorRequest,
    OptimizationAdvisorResponse,
)
from app.services.ai.optimization_advisor import (
    OptimizationAdvisorService,
    RecommendationNotFoundError,
)
from app.services.optimization import OptimizationService

router = APIRouter(prefix="/optimization", tags=["optimization"])


def get_optimization_service(
    current_user: Annotated[User, Depends(get_current_active_user)],
    cache: Annotated[RedisCache, Depends(get_cache)],
) -> OptimizationService:
    return OptimizationService(cache=cache, user_scope=str(current_user.id))


def get_optimization_advisor_service(
    current_user: Annotated[User, Depends(get_current_active_user)],
    cache: Annotated[RedisCache, Depends(get_cache)],
) -> OptimizationAdvisorService:
    return OptimizationAdvisorService(cache=cache, user_scope=str(current_user.id))


@router.get(
    "/recommendations",
    response_model=OptimizationResponse,
    summary="List deterministic FinOps recommendations",
)
@enforce_cost_rate_limit
async def list_recommendations(
    request: Request,
    query: Annotated[OptimizationQuery, Depends()],
    service: Annotated[OptimizationService, Depends(get_optimization_service)],
) -> OptimizationResponse:
    return await service.list_recommendations(query)


@router.get(
    "/recommendations/{recommendation_id}",
    response_model=Recommendation,
    summary="Get one FinOps recommendation",
)
@enforce_cost_rate_limit
async def get_recommendation(
    recommendation_id: str,
    request: Request,
    query: Annotated[OptimizationQuery, Depends()],
    service: Annotated[OptimizationService, Depends(get_optimization_service)],
) -> Recommendation:
    recommendation = await service.get_recommendation(recommendation_id, query)
    if recommendation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Recommendation not found"
        )
    return recommendation


@router.patch(
    "/recommendations/{recommendation_id}/status",
    response_model=Recommendation,
    summary="Update recommendation lifecycle status",
)
@enforce_cost_rate_limit
async def update_recommendation_status(
    recommendation_id: str,
    request: Request,
    update: RecommendationStatusUpdate,
    service: Annotated[OptimizationService, Depends(get_optimization_service)],
) -> Recommendation:
    query = OptimizationQuery(
        start_date=update.start_date,
        end_date=update.end_date,
        limit=100,
    )
    recommendation = await service.update_status(
        recommendation_id, update.status, query
    )
    if recommendation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Recommendation not found"
        )
    return recommendation


@router.post(
    "/recommendations/{recommendation_id}/advisor",
    response_model=OptimizationAdvisorResponse,
    summary="Explain one deterministic FinOps recommendation",
    responses={
        404: {"description": "Recommendation not found for the supplied period."}
    },
)
@enforce_cost_rate_limit
async def explain_recommendation(
    recommendation_id: str,
    request: Request,
    advisor_request: OptimizationAdvisorRequest,
    service: Annotated[
        OptimizationAdvisorService, Depends(get_optimization_advisor_service)
    ],
) -> OptimizationAdvisorResponse:
    try:
        return await service.explain(recommendation_id, advisor_request)
    except RecommendationNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(error)
        ) from error
