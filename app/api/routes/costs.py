"""Unified multi-cloud cost API route.

A single ``GET /api/v1/costs`` endpoint that dispatches to any
registered cloud provider based on the ``provider`` query parameter.

Business logic (provider resolution, service invocation, error mapping)
lives in :mod:`app.services.cost_service` so this module stays focused
on the HTTP contract: path, query parameters, status codes, response
body, and structured logging.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from app.auth.dependencies import get_current_active_user
from app.auth.models import User
from app.core.logging import get_logger
from app.core.rate_limit import enforce_cost_rate_limit
from app.providers.exceptions import (
    ProviderCredentialsError,
    ProviderInvalidDateRangeError,
    ProviderNotSupportedException,
    ProviderPermissionsError,
    ProviderServiceError,
    ProviderThrottlingError,
)
from app.providers.schemas import CostResponse
from app.schemas.cost import UnifiedCostRequest
from app.services.cost_service import UnifiedCostService

logger = get_logger(__name__)

router = APIRouter(prefix="/costs", tags=["costs"])


@router.get(
    "/",
    response_model=CostResponse,
    summary="Retrieve costs from any cloud provider",
    description=(
        "Retrieve normalized cost data from a registered cloud provider "
        "(aws, azure, gcp). The provider is selected via the ``provider`` "
        "query parameter so a single route can dispatch to any backend "
        "without changing the request path. "
        "Requires valid JWT authentication."
    ),
    responses={
        200: {"description": "Cost data retrieved successfully."},
        400: {"description": "Invalid date range, unsupported provider, or bad parameters."},
        401: {"description": "Not authenticated."},
        403: {"description": "Insufficient provider permissions."},
        422: {"description": "Validation error."},
        429: {"description": "Provider API throttling."},
        500: {"description": "Provider credentials missing or invalid."},
        502: {"description": "Provider service error."},
    },
)
@enforce_cost_rate_limit
async def get_unified_costs(
    request: Request,
    query: Annotated[UnifiedCostRequest, Query()],
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> CostResponse:
    """Retrieve normalized costs from any registered cloud provider.

    The provider is resolved from the query parameter at runtime (not
    via a module-level dependency) so the same handler can dispatch
    to ``aws``, ``azure``, or ``gcp`` without code changes. Provider-
    specific exceptions are already translated into the provider-
    agnostic hierarchy inside each concrete :class:`CloudProvider`
    implementation, so this handler only catches the agnostic types.
    """
    logger.info(
        "unified_costs_request",
        extra={
            "user_id": str(current_user.id),
            "provider": query.provider,
            "start_date": query.start_date.isoformat(),
            "end_date": query.end_date.isoformat(),
            "granularity": query.granularity,
        },
    )

    service = UnifiedCostService(
        provider_name=query.provider,
    )

    try:
        result = await service.get_costs(
            start_date=query.start_date,
            end_date=query.end_date,
            granularity=query.granularity,
        )
        logger.info(
            "unified_costs_response",
            extra={
                "provider": query.provider,
                "total_cost": result.total_cost,
                "service_count": len(result.services),
            },
        )
        return result

    except ProviderNotSupportedException as e:
        logger.error(
            "unified_costs_unsupported_provider",
            extra={"provider": query.provider, "error": str(e)},
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=e.message,
            headers={"X-Error-Code": "PROVIDER_NOT_SUPPORTED"},
        ) from e

    except ProviderInvalidDateRangeError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=e.message,
            headers={"X-Error-Code": e.error_code},
        ) from e

    except ProviderCredentialsError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=e.message,
            headers={"X-Error-Code": e.error_code},
        ) from e

    except ProviderThrottlingError as e:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=e.message,
            headers={"X-Error-Code": e.error_code},
        ) from e

    except ProviderPermissionsError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=e.message,
            headers={"X-Error-Code": e.error_code},
        ) from e

    except ProviderServiceError as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=e.message,
            headers={"X-Error-Code": e.error_code},
        ) from e
