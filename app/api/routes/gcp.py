"""GCP Cloud Billing API routes.

The route resolves a :class:`CloudProvider` implementation via the
provider registry, keeping the HTTP contract (path, query parameters,
status codes, response body) identical to the AWS cost route.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from app.auth.dependencies import get_current_active_user
from app.auth.models import User
from app.core.logging import get_logger
from app.core.rate_limit import enforce_cost_rate_limit
from app.providers import get_provider
from app.providers.exceptions import (
    ProviderCredentialsError,
    ProviderInvalidDateRangeError,
    ProviderPermissionsError,
    ProviderServiceError,
    ProviderThrottlingError,
)
from app.providers.schemas import CostResponse
from app.schemas.gcp import GCPCostRequest
from app.services.cost_aggregator import CostAggregatorService, get_cost_aggregator
from app.services.gcp.exceptions import (
    GCPBigQueryError,
    GCPBillingAccountNotFoundError,
    GCPCredentialsError,
    GCPQuotaExceededError,
)

logger = get_logger(__name__)

router = APIRouter(prefix="/gcp", tags=["gcp"])
gcp_provider_dependency = get_provider("gcp")
gcp_cost_aggregator_dependency = get_cost_aggregator("gcp", gcp_provider_dependency)


@router.get(
    "/costs",
    response_model=CostResponse,
    summary="Retrieve GCP costs",
    description=(
        "Retrieve normalized GCP cost data grouped by service. "
        "Requires valid JWT authentication. "
        "Supports DAILY and MONTHLY granularity."
    ),
    responses={
        200: {"description": "Cost data retrieved successfully."},
        400: {"description": "Invalid date range or parameters."},
        401: {"description": "Not authenticated."},
        403: {"description": "Insufficient GCP permissions."},
        422: {"description": "Validation error."},
        429: {"description": "GCP API throttling."},
        500: {"description": "GCP credentials missing or invalid."},
        502: {"description": "GCP service error."},
    },
)
@enforce_cost_rate_limit
async def get_gcp_costs(
    request: Request,
    query: Annotated[GCPCostRequest, Query()],
    current_user: Annotated[User, Depends(get_current_active_user)],
    aggregator: Annotated[
        CostAggregatorService,
        Depends(gcp_cost_aggregator_dependency),
    ],
) -> CostResponse:
    """Retrieve GCP costs grouped by service via the provider abstraction."""
    logger.info(
        "gcp_costs_request",
        extra={
            "user_id": str(current_user.id),
            "start_date": query.start_date.isoformat(),
            "end_date": query.end_date.isoformat(),
            "granularity": query.granularity,
        },
    )

    try:
        result = await aggregator.get_costs(
            start_date=query.start_date,
            end_date=query.end_date,
            granularity=query.granularity,
        )
        logger.info(
            "gcp_costs_response",
            extra={
                "total_cost": result.total_cost,
                "service_count": len(result.services),
            },
        )
        return result
    except (GCPBillingAccountNotFoundError, ProviderInvalidDateRangeError) as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=e.message,
            headers={"X-Error-Code": e.error_code},
        ) from e
    except (GCPCredentialsError, ProviderCredentialsError) as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=e.message,
            headers={"X-Error-Code": e.error_code},
        ) from e
    except (GCPQuotaExceededError, ProviderThrottlingError) as e:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=e.message,
            headers={"X-Error-Code": e.error_code},
        ) from e
    except GCPBigQueryError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=e.message,
            headers={"X-Error-Code": e.error_code},
        ) from e
    except (ProviderPermissionsError, ProviderServiceError) as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=e.message,
            headers={"X-Error-Code": e.error_code},
        ) from e