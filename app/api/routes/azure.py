"""Azure Cost Management API routes.

The route resolves a :class:`CloudProvider` implementation via the
provider registry, keeping the HTTP contract (path, query parameters,
status codes, response body) consistent with the AWS route. Vendor
specific exceptions are translated to the provider-agnostic hierarchy
inside :class:`app.providers.azure.AzureCloudProvider`, so this layer
only handles the normalised error types.
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
from app.schemas.azure import AzureCostRequest
from app.services.azure.exceptions import (
    AzureCredentialsError,
    AzureInvalidSubscriptionError,
    AzurePermissionsError,
    AzureServiceError,
    AzureThrottlingError,
)
from app.services.cost_aggregator import CostAggregatorService, get_cost_aggregator

logger = get_logger(__name__)

router = APIRouter(prefix="/azure", tags=["azure"])
azure_provider_dependency = get_provider("azure")
azure_cost_aggregator_dependency = get_cost_aggregator("azure", azure_provider_dependency)


@router.get(
    "/costs",
    response_model=CostResponse,
    summary="Retrieve Azure costs",
    description=(
        "Retrieve normalized Azure cost data grouped by service. "
        "Requires valid JWT authentication. "
        "Supports DAILY and MONTHLY granularity."
    ),
    responses={
        200: {"description": "Cost data retrieved successfully."},
        400: {"description": "Invalid date range or parameters."},
        401: {"description": "Not authenticated."},
        403: {"description": "Insufficient Azure permissions."},
        422: {"description": "Validation error."},
        429: {"description": "Azure API throttling."},
        500: {"description": "Azure credentials missing or invalid."},
        502: {"description": "Azure service error."},
    },
)
@enforce_cost_rate_limit
async def get_azure_costs(
    request: Request,
    query: Annotated[AzureCostRequest, Query()],
    current_user: Annotated[User, Depends(get_current_active_user)],
    aggregator: Annotated[
        CostAggregatorService,
        Depends(azure_cost_aggregator_dependency),
    ],
) -> CostResponse:
    """Retrieve Azure costs grouped by service via the provider abstraction."""
    logger.info(
        "azure_costs_request",
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
            "azure_costs_response",
            extra={
                "total_cost": result.total_cost,
                "service_count": len(result.services),
            },
        )
        return result
    except (AzureInvalidSubscriptionError, ProviderInvalidDateRangeError) as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=e.message,
            headers={"X-Error-Code": e.error_code},
        ) from e
    except (AzureCredentialsError, ProviderCredentialsError) as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=e.message,
            headers={"X-Error-Code": e.error_code},
        ) from e
    except (AzureThrottlingError, ProviderThrottlingError) as e:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=e.message,
            headers={"X-Error-Code": e.error_code},
        ) from e
    except (AzurePermissionsError, ProviderPermissionsError) as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=e.message,
            headers={"X-Error-Code": e.error_code},
        ) from e
    except (AzureServiceError, ProviderServiceError) as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=e.message,
            headers={"X-Error-Code": e.error_code},
        ) from e
