"""Authenticated CRUD and evaluation endpoints for cost alerts."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.alerts.notifications import EmailNotificationService
from app.alerts.repository import AlertRepository
from app.alerts.service import AlertEvaluationService, AlertNotFoundError, AlertService
from app.api.deps import get_db_session
from app.auth.dependencies import get_current_active_user
from app.auth.models import User
from app.core.cache import RedisCache, get_cache
from app.core.rate_limit import enforce_cost_rate_limit
from app.schemas.alerts import (
    AlertCreate,
    AlertEvaluationRequest,
    AlertEvaluationResult,
    AlertResponse,
    AlertUpdate,
)
from app.services.anomaly import AnomalyDetectionService
from app.services.explorer.service import CostExplorerService
from app.services.forecasting import ForecastingService

router = APIRouter(prefix="/alerts", tags=["alerts"])


def get_alert_repo(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> AlertRepository:
    return AlertRepository(session)


def get_alert_service(
    repo: Annotated[AlertRepository, Depends(get_alert_repo)],
) -> AlertService:
    return AlertService(repo)


def get_alert_evaluator(
    current_user: Annotated[User, Depends(get_current_active_user)],
    repo: Annotated[AlertRepository, Depends(get_alert_repo)],
    cache: Annotated[RedisCache, Depends(get_cache)],
) -> AlertEvaluationService:
    scope = str(current_user.id)
    return AlertEvaluationService(
        repo=repo,
        explorer=CostExplorerService(cache=cache, user_scope=scope),
        detector=AnomalyDetectionService(cache=cache, user_scope=scope),
        forecasting=ForecastingService(cache=cache, user_scope=scope),
        notifier=EmailNotificationService(),
    )


@router.get(
    "",
    response_model=list[AlertResponse],
    summary="List the current user's cost alerts",
)
@enforce_cost_rate_limit
async def list_alerts(
    request: Request,
    current_user: Annotated[User, Depends(get_current_active_user)],
    service: Annotated[AlertService, Depends(get_alert_service)],
) -> list[AlertResponse]:
    return await service.list(current_user.id)


@router.post(
    "",
    response_model=AlertResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a cost alert",
)
@enforce_cost_rate_limit
async def create_alert(
    request: Request,
    payload: AlertCreate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    service: Annotated[AlertService, Depends(get_alert_service)],
) -> AlertResponse:
    return await service.create(payload, current_user.id)


@router.post(
    "/evaluate",
    response_model=list[AlertEvaluationResult],
    summary="Evaluate enabled cost alerts",
)
@enforce_cost_rate_limit
async def evaluate_alerts(
    request: Request,
    payload: AlertEvaluationRequest,
    current_user: Annotated[User, Depends(get_current_active_user)],
    evaluator: Annotated[AlertEvaluationService, Depends(get_alert_evaluator)],
) -> list[AlertEvaluationResult]:
    return await evaluator.evaluate(
        current_user.id, current_user.email, payload.start_date, payload.end_date
    )


@router.get("/{alert_id}", response_model=AlertResponse, summary="Get one cost alert")
@enforce_cost_rate_limit
async def get_alert(
    alert_id: uuid.UUID,
    request: Request,
    current_user: Annotated[User, Depends(get_current_active_user)],
    service: Annotated[AlertService, Depends(get_alert_service)],
) -> AlertResponse:
    try:
        return await service.get(alert_id, current_user.id)
    except AlertNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.patch(
    "/{alert_id}", response_model=AlertResponse, summary="Update a cost alert"
)
@enforce_cost_rate_limit
async def update_alert(
    alert_id: uuid.UUID,
    request: Request,
    payload: AlertUpdate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    service: Annotated[AlertService, Depends(get_alert_service)],
) -> AlertResponse:
    try:
        return await service.update(alert_id, payload, current_user.id)
    except AlertNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.delete(
    "/{alert_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    summary="Delete a cost alert",
)
@enforce_cost_rate_limit
async def delete_alert(
    alert_id: uuid.UUID,
    request: Request,
    current_user: Annotated[User, Depends(get_current_active_user)],
    service: Annotated[AlertService, Depends(get_alert_service)],
) -> Response:
    try:
        await service.delete(alert_id, current_user.id)
    except AlertNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    return Response(status_code=status.HTTP_204_NO_CONTENT)
