"""Authenticated CRUD and evaluation endpoints for cost budgets."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db_session
from app.auth.dependencies import get_current_active_user
from app.auth.models import User
from app.budgets.repository import BudgetRepository
from app.budgets.service import (
    BudgetEvaluationService,
    BudgetNotFoundError,
    BudgetService,
)
from app.core.cache import RedisCache, get_cache
from app.core.rate_limit import enforce_cost_rate_limit
from app.schemas.budgets import (
    BudgetCreate,
    BudgetEvaluation,
    BudgetEvaluationError,
    BudgetResponse,
    BudgetUpdate,
)
from app.services.explorer.service import CostExplorerService
from app.services.forecasting import ForecastingService

router = APIRouter(prefix="/budgets", tags=["budgets"])


def get_budget_repo(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> BudgetRepository:
    return BudgetRepository(session)


def get_budget_service(
    repo: Annotated[BudgetRepository, Depends(get_budget_repo)],
) -> BudgetService:
    return BudgetService(repo)


def get_budget_evaluator(
    current_user: Annotated[User, Depends(get_current_active_user)],
    cache: Annotated[RedisCache, Depends(get_cache)],
) -> BudgetEvaluationService:
    scope = str(current_user.id)
    explorer = CostExplorerService(cache=cache, user_scope=scope)
    return BudgetEvaluationService(
        explorer=explorer,
        forecasting=ForecastingService(
            cache=cache, user_scope=scope, explorer=explorer
        ),
        cache=cache,
        user_scope=scope,
    )


@router.get(
    "", response_model=list[BudgetResponse], summary="List the current user's budgets"
)
@enforce_cost_rate_limit
async def list_budgets(
    request: Request,
    current_user: Annotated[User, Depends(get_current_active_user)],
    service: Annotated[BudgetService, Depends(get_budget_service)],
) -> list[BudgetResponse]:
    return await service.list(current_user.id)


@router.post(
    "",
    response_model=BudgetResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a cost budget",
)
@enforce_cost_rate_limit
async def create_budget(
    request: Request,
    payload: BudgetCreate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    service: Annotated[BudgetService, Depends(get_budget_service)],
) -> BudgetResponse:
    return await service.create(payload, current_user.id)


@router.get(
    "/{budget_id}/evaluation",
    response_model=BudgetEvaluation,
    summary="Evaluate one cost budget",
)
@enforce_cost_rate_limit
async def evaluate_budget(
    budget_id: uuid.UUID,
    request: Request,
    current_user: Annotated[User, Depends(get_current_active_user)],
    service: Annotated[BudgetService, Depends(get_budget_service)],
    evaluator: Annotated[BudgetEvaluationService, Depends(get_budget_evaluator)],
) -> BudgetEvaluation:
    try:
        budget = await service.get(budget_id, current_user.id)
        return await evaluator.evaluate(budget)
    except BudgetNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except BudgetEvaluationError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.get(
    "/{budget_id}", response_model=BudgetResponse, summary="Get one cost budget"
)
@enforce_cost_rate_limit
async def get_budget(
    budget_id: uuid.UUID,
    request: Request,
    current_user: Annotated[User, Depends(get_current_active_user)],
    service: Annotated[BudgetService, Depends(get_budget_service)],
) -> BudgetResponse:
    try:
        return await service.get(budget_id, current_user.id)
    except BudgetNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.patch(
    "/{budget_id}", response_model=BudgetResponse, summary="Update a cost budget"
)
@enforce_cost_rate_limit
async def update_budget(
    budget_id: uuid.UUID,
    request: Request,
    payload: BudgetUpdate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    service: Annotated[BudgetService, Depends(get_budget_service)],
) -> BudgetResponse:
    try:
        return await service.update(budget_id, payload, current_user.id)
    except BudgetNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.delete(
    "/{budget_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    summary="Delete a cost budget",
)
@enforce_cost_rate_limit
async def delete_budget(
    budget_id: uuid.UUID,
    request: Request,
    current_user: Annotated[User, Depends(get_current_active_user)],
    service: Annotated[BudgetService, Depends(get_budget_service)],
) -> Response:
    try:
        await service.delete(budget_id, current_user.id)
    except BudgetNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    return Response(status_code=status.HTTP_204_NO_CONTENT)
