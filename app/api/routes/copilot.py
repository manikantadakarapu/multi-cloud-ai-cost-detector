"""Authenticated FinOps Copilot endpoint."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db_session
from app.auth.dependencies import get_current_active_user
from app.auth.models import User
from app.budgets.repository import BudgetRepository
from app.budgets.service import BudgetEvaluationService
from app.core.cache import RedisCache, get_cache
from app.core.rate_limit import enforce_cost_rate_limit
from app.schemas.copilot import CopilotQuery, CopilotResponse
from app.services.ai.copilot import CopilotService
from app.services.ai.copilot_context import CopilotContextService
from app.services.anomaly import AnomalyDetectionService
from app.services.explorer.service import CostExplorerService
from app.services.forecasting import ForecastingService
from app.services.optimization import OptimizationService

router = APIRouter(prefix="/copilot", tags=["copilot"])


def get_copilot_service(
    current_user: Annotated[User, Depends(get_current_active_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    cache: Annotated[RedisCache, Depends(get_cache)],
) -> CopilotService:
    scope = str(current_user.id)
    explorer = CostExplorerService(cache=cache, user_scope=scope)
    forecasting = ForecastingService(cache=cache, user_scope=scope, explorer=explorer)
    context = CopilotContextService(
        explorer=explorer,
        detector=AnomalyDetectionService(cache=cache, user_scope=scope),
        forecasting=forecasting,
        optimization=OptimizationService(
            cache=cache, user_scope=scope, explorer=explorer
        ),
        budgets=BudgetRepository(session),
        budget_evaluator=BudgetEvaluationService(
            explorer=explorer,
            forecasting=forecasting,
            cache=cache,
            user_scope=scope,
        ),
        budget_user_id=current_user.id,
    )
    return CopilotService(context_service=context, cache=cache, user_scope=scope)


@router.post(
    "/query",
    response_model=CopilotResponse,
    summary="Ask a bounded FinOps Copilot question",
)
@enforce_cost_rate_limit
async def query_copilot(
    request: Request,
    payload: CopilotQuery,
    service: Annotated[CopilotService, Depends(get_copilot_service)],
) -> CopilotResponse:
    return await service.answer(payload.question)
