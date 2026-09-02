"""Authenticated deterministic cost anomaly endpoint."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.auth.dependencies import get_current_active_user
from app.auth.models import User
from app.core.cache import RedisCache, get_cache
from app.core.rate_limit import enforce_cost_rate_limit
from app.schemas.anomaly import AnomalyQuery, AnomalyResponse
from app.schemas.anomaly_explanation import (
    AnomalyExplanationRequest,
    AnomalyExplanationResponse,
)
from app.services.ai.anomaly_explanations import (
    AnomalyExplanationNotFoundError,
    AnomalyExplanationService,
)
from app.services.anomaly import AnomalyDetectionService

router = APIRouter(prefix="/anomalies", tags=["anomalies"])


def get_anomaly_service(
    current_user: Annotated[User, Depends(get_current_active_user)],
    cache: Annotated[RedisCache, Depends(get_cache)],
) -> AnomalyDetectionService:
    scope = str(current_user.id)
    return AnomalyDetectionService(cache=cache, user_scope=scope)


def get_anomaly_explanation_service(
    current_user: Annotated[User, Depends(get_current_active_user)],
    cache: Annotated[RedisCache, Depends(get_cache)],
) -> AnomalyExplanationService:
    """Build an explanation service scoped to the authenticated user."""
    return AnomalyExplanationService(cache=cache, user_scope=str(current_user.id))


@router.get(
    "",
    response_model=AnomalyResponse,
    summary="Detect deterministic cloud cost anomalies",
)
@enforce_cost_rate_limit
async def get_anomalies(
    request: Request,
    query: Annotated[AnomalyQuery, Depends()],
    service: Annotated[AnomalyDetectionService, Depends(get_anomaly_service)],
) -> AnomalyResponse:
    return await service.detect(query)


@router.post(
    "/{anomaly_id}/explanation",
    response_model=AnomalyExplanationResponse,
    summary="Explain one verified cost anomaly",
    responses={404: {"description": "Anomaly not found for the supplied filters."}},
)
@enforce_cost_rate_limit
async def explain_anomaly(
    anomaly_id: str,
    request: Request,
    query: AnomalyExplanationRequest,
    service: Annotated[
        AnomalyExplanationService, Depends(get_anomaly_explanation_service)
    ],
) -> AnomalyExplanationResponse:
    """Build verified context and generate an optional AI explanation on demand."""
    try:
        return await service.explain(anomaly_id, query)
    except AnomalyExplanationNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(error)
        ) from error
