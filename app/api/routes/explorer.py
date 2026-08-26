"""Authenticated Cost Explorer API routes for multi-dimensional spend drill-down."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.auth.dependencies import get_current_active_user
from app.auth.models import User
from app.core.cache import RedisCache, get_cache
from app.core.logging import get_logger
from app.core.rate_limit import enforce_cost_rate_limit
from app.providers.exceptions import (
    ProviderCredentialsError,
    ProviderInvalidDateRangeError,
    ProviderPermissionsError,
    ProviderServiceError,
    ProviderThrottlingError,
)
from app.schemas.explorer import ExplorerQuery, ExplorerResponse
from app.services.explorer.service import CostExplorerService

logger = get_logger(__name__)

router = APIRouter(prefix="/explorer", tags=["explorer"])


def get_explorer_service(
    current_user: Annotated[User, Depends(get_current_active_user)],
    cache: Annotated[RedisCache, Depends(get_cache)],
) -> CostExplorerService:
    """Build a Cost Explorer service scoped to the authenticated user."""
    return CostExplorerService(cache=cache, user_scope=str(current_user.id))


@router.get(
    "",
    response_model=ExplorerResponse,
    summary="Explore and drill down into multi-cloud costs",
    description=(
        "Retrieve normalized, multi-dimensional cost records filtered by provider, "
        "service, region, account, and date range with automated rollups."
    ),
    responses={
        200: {"description": "Cost Explorer data retrieved successfully."},
        400: {"description": "Invalid date range or query parameters."},
        401: {"description": "Authentication required."},
        403: {"description": "Insufficient cloud provider permissions."},
        422: {"description": "Validation error on query parameters."},
        429: {"description": "Rate limit exceeded or provider throttling."},
        500: {"description": "Cloud provider credentials missing or invalid."},
        502: {"description": "Upstream cloud provider error."},
    },
)
@enforce_cost_rate_limit
async def explore_costs(
    request: Request,
    query: Annotated[ExplorerQuery, Depends()],
    service: Annotated[CostExplorerService, Depends(get_explorer_service)],
) -> ExplorerResponse:
    """Execute Cost Explorer query and return rollups and line items."""
    try:
        return await service.get_explorer_data(query)
    except ProviderInvalidDateRangeError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except ProviderCredentialsError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc
    except ProviderPermissionsError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc
    except ProviderThrottlingError as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=str(exc),
        ) from exc
    except ProviderServiceError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        logger.error("explorer_endpoint_error", extra={"error": str(exc)})
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Cost exploration error: {exc}",
        ) from exc
