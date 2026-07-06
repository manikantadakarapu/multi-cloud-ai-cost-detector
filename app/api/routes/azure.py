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

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.auth.dependencies import get_current_active_user
from app.auth.models import User
from app.core.logging import get_logger
from app.providers import CloudProvider, get_provider
from app.providers.exceptions import (
    ProviderCredentialsError,
    ProviderInvalidDateRangeError,
    ProviderPermissionsError,
    ProviderServiceError,
    ProviderThrottlingError,
)
from app.providers.schemas import CostResponse
from app.schemas.azure import AzureCostRequest

logger = get_logger(__name__)

router = APIRouter(prefix="/azure", tags=["azure"])


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
async def get_azure_costs(
    request: Annotated[AzureCostRequest, Query()],
    current_user: Annotated[User, Depends(get_current_active_user)],
    provider: Annotated[CloudProvider, Depends(get_provider("azure"))],
) -> CostResponse:
    """Retrieve Azure costs grouped by service via the provider abstraction."""
    logger.info(
        "azure_costs_request",
        extra={
            "user_id": str(current_user.id),
            "start_date": request.start_date.isoformat(),
            "end_date": request.end_date.isoformat(),
            "granularity": request.granularity,
        },
    )

    try:
        result = await provider.get_costs(
            start_date=request.start_date,
            end_date=request.end_date,
            granularity=request.granularity,
        )
        logger.info(
            "azure_costs_response",
            extra={
                "total_cost": result.total_cost,
                "service_count": len(result.services),
            },
        )
        return result
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
