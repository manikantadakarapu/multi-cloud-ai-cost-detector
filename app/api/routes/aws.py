"""AWS Cost Explorer API routes."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.auth.dependencies import get_current_active_user
from app.auth.models import User
from app.core.config import settings
from app.core.logging import get_logger
from app.schemas.aws import AWSCostRequest, AWSCostResponse
from app.services.aws.cost_explorer import CostExplorerService
from app.services.aws.exceptions import (
    AWSCredentialsError,
    AWSInvalidDateRangeError,
    AWSPermissionsError,
    AWSServiceError,
    AWSThrottlingError,
)

logger = get_logger(__name__)

router = APIRouter(prefix="/aws", tags=["aws"])


def get_cost_explorer_service() -> CostExplorerService:
    """Dependency providing CostExplorerService instance."""
    return CostExplorerService(settings)


@router.get(
    "/costs",
    response_model=AWSCostResponse,
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
async def get_aws_costs(
    request: Annotated[AWSCostRequest, Query()],
    current_user: Annotated[User, Depends(get_current_active_user)],
    service: Annotated[CostExplorerService, Depends(get_cost_explorer_service)],
) -> AWSCostResponse:
    """Retrieve AWS costs grouped by service."""
    logger.info(
        "aws_costs_request",
        extra={
            "user_id": str(current_user.id),
            "start_date": request.start_date.isoformat(),
            "end_date": request.end_date.isoformat(),
            "granularity": request.granularity,
        },
    )

    try:
        result = await service.get_costs(
            start_date=request.start_date,
            end_date=request.end_date,
            granularity=request.granularity,
        )
        logger.info(
            "aws_costs_response",
            extra={
                "total_cost": result.get("total_cost", 0),
                "service_count": len(result.get("services", [])),
            },
        )
        return AWSCostResponse(**result)
    except AWSInvalidDateRangeError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=e.message,
            headers={"X-Error-Code": e.error_code},
        ) from e
    except AWSCredentialsError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=e.message,
            headers={"X-Error-Code": e.error_code},
        ) from e
    except AWSThrottlingError as e:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=e.message,
            headers={"X-Error-Code": e.error_code},
        ) from e
    except AWSPermissionsError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=e.message,
            headers={"X-Error-Code": e.error_code},
        ) from e
    except AWSServiceError as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=e.message,
            headers={"X-Error-Code": e.error_code},
        ) from e
