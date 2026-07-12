"""AWS Cost Explorer API routes.

The route now resolves a :class:`CloudProvider` implementation via the
provider registry, keeping the HTTP contract (path, query parameters,
status codes, response body) identical to the previous direct-service
implementation.
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
from app.schemas.aws import AWSCostRequest
from app.services.aws.exceptions import (
    AWSCredentialsError,
    AWSInvalidDateRangeError,
    AWSPermissionsError,
    AWSServiceError,
    AWSThrottlingError,
)
from app.services.cost_aggregator import CostAggregatorService, get_cost_aggregator

logger = get_logger(__name__)

router = APIRouter(prefix="/aws", tags=["aws"])
aws_provider_dependency = get_provider("aws")
aws_cost_aggregator_dependency = get_cost_aggregator("aws", aws_provider_dependency)


@router.get(
    "/costs",
    response_model=CostResponse,
    summary="Retrieve AWS costs",
    description=(
        "Retrieve normalized AWS cost data grouped by service. "
        "Requires valid JWT authentication. "
        "Supports DAILY and MONTHLY granularity."
    ),
    responses={
        200: {"description": "Cost data retrieved successfully."},
        400: {"description": "Invalid date range or parameters."},
        401: {"description": "Not authenticated."},
        403: {"description": "Insufficient AWS permissions."},
        422: {"description": "Validation error."},
        429: {"description": "AWS API throttling."},
        500: {"description": "AWS credentials missing or invalid."},
        502: {"description": "AWS service error."},
    },
)
@enforce_cost_rate_limit
async def get_aws_costs(
    request: Request,
    query: Annotated[AWSCostRequest, Query()],
    current_user: Annotated[User, Depends(get_current_active_user)],
    aggregator: Annotated[
        CostAggregatorService,
        Depends(aws_cost_aggregator_dependency),
    ],
) -> CostResponse:
    """Retrieve AWS costs grouped by service via the provider abstraction."""
    logger.info(
        "aws_costs_request",
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
            "aws_costs_response",
            extra={
                "total_cost": result.total_cost,
                "service_count": len(result.services),
            },
        )
        return result
    except (AWSInvalidDateRangeError, ProviderInvalidDateRangeError) as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=e.message,
            headers={"X-Error-Code": e.error_code},
        ) from e
    except (AWSCredentialsError, ProviderCredentialsError) as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=e.message,
            headers={"X-Error-Code": e.error_code},
        ) from e
    except (AWSThrottlingError, ProviderThrottlingError) as e:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=e.message,
            headers={"X-Error-Code": e.error_code},
        ) from e
    except (AWSPermissionsError, ProviderPermissionsError) as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=e.message,
            headers={"X-Error-Code": e.error_code},
        ) from e
    except (AWSServiceError, ProviderServiceError) as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=e.message,
            headers={"X-Error-Code": e.error_code},
        ) from e
