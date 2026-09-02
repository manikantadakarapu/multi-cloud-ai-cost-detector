"""Authenticated deterministic cost anomaly endpoint."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request

from app.auth.dependencies import get_current_active_user
from app.auth.models import User
from app.core.cache import RedisCache, get_cache
from app.core.rate_limit import enforce_cost_rate_limit
from app.schemas.anomaly import AnomalyQuery, AnomalyResponse
from app.services.anomaly import AnomalyDetectionService

router = APIRouter(prefix="/anomalies", tags=["anomalies"])


def get_anomaly_service(
    current_user: Annotated[User, Depends(get_current_active_user)],
    cache: Annotated[RedisCache, Depends(get_cache)],
) -> AnomalyDetectionService:
    scope = str(current_user.id)
    return AnomalyDetectionService(cache=cache, user_scope=scope)


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
