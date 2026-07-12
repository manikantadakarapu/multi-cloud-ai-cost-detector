"""AWS Cost Explorer service for retrieving and normalizing cost data."""

from __future__ import annotations

import logging
import time
from datetime import date
from typing import Any

import boto3
from botocore.config import Config as BotocoreConfig
from botocore.exceptions import ClientError, NoCredentialsError

from app.core.config import Settings
from app.services.aws.exceptions import (
    AWSCostExplorerError,
    AWSCredentialsError,
    AWSInvalidDateRangeError,
    AWSPermissionsError,
    AWSServiceError,
    AWSThrottlingError,
)

logger = logging.getLogger(__name__)


class CostExplorerService:
    """Service for retrieving AWS cost data via Cost Explorer API."""

    GRANULARITY_DAILY = "DAILY"
    GRANULARITY_MONTHLY = "MONTHLY"
    METRIC_UNBLENDED_COST = "UnblendedCost"
    GROUP_BY_SERVICE = [{"Type": "DIMENSION", "Key": "SERVICE"}]

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client: Any | None = None

    def _ensure_client(self) -> None:
        """Lazy-initialize boto3 Cost Explorer client."""
        if self._client is not None:
            return

        try:
            session_kwargs = {"region_name": self._settings.aws_default_region}
            if self._settings.aws_profile:
                session_kwargs["profile_name"] = self._settings.aws_profile
            if self._settings.aws_access_key_id and self._settings.aws_secret_access_key:
                session_kwargs["aws_access_key_id"] = self._settings.aws_access_key_id
                session_kwargs["aws_secret_access_key"] = self._settings.aws_secret_access_key

            session = boto3.Session(**session_kwargs)
            self._client = session.client(
                "ce",
                config=BotocoreConfig(
                    retries={"max_attempts": 3, "mode": "standard"},
                    connect_timeout=10,
                    read_timeout=30,
                ),
            )
        except NoCredentialsError as e:
            logger.error(
                "aws_credentials_not_found",
                extra={"region": self._settings.aws_default_region},
            )
            raise AWSCredentialsError("AWS credentials not found") from e
        except AWSCostExplorerError:
            raise
        except Exception as e:
            logger.error("aws_client_creation_failed", extra={"error": str(e)})
            raise AWSCredentialsError(f"Failed to create AWS client: {e}") from e

    def _validate_date_range(self, start_date: date, end_date: date) -> None:
        """Validate date range for Cost Explorer API."""
        if start_date > end_date:
            raise AWSInvalidDateRangeError("start_date must be before or equal to end_date")
        if start_date > date.today():
            raise AWSInvalidDateRangeError("start_date cannot be in the future")
        if (end_date - start_date).days > 365 * 2:
            raise AWSInvalidDateRangeError("Date range cannot exceed 2 years")

    def _build_request(
        self,
        start_date: date,
        end_date: date,
        granularity: str,
    ) -> dict[str, Any]:
        """Build Cost Explorer GetCostAndUsage request."""
        return {
            "TimePeriod": {
                "Start": start_date.isoformat(),
                "End": end_date.isoformat(),
            },
            "Granularity": granularity,
            "Metrics": [self.METRIC_UNBLENDED_COST],
            "GroupBy": self.GROUP_BY_SERVICE,
        }

    def _fetch_all_pages(self, request: dict[str, Any]) -> dict[str, Any]:
        """Fetch all paginated results from Cost Explorer.

        Returns a synthetic response dict containing combined ResultsByTime.
        """
        results_by_time: list[dict[str, Any]] = []
        next_token: str | None = None
        page_count = 0

        while True:
            page_request = dict(request)
            if next_token:
                page_request["NextPageToken"] = next_token

            response = self._client.get_cost_and_usage(**page_request)
            page_count += 1
            results_by_time.extend(response.get("ResultsByTime", []))
            next_token = response.get("NextPageToken")
            if not next_token:
                break

        return {
            "ResultsByTime": results_by_time,
            "PageCount": page_count,
        }

    def _normalize_response(self, response: dict[str, Any]) -> dict[str, Any]:
        """Normalize AWS Cost Explorer response to unified schema."""
        services: list[dict[str, Any]] = []
        total_cost = 0.0
        currency = "USD"

        for time_period in response.get("ResultsByTime", []):
            for group in time_period.get("Groups", []):
                keys = group.get("Keys", [])
                service_name = keys[0] if keys else "Unknown"
                metrics = group.get("Metrics", {})
                cost_data = metrics.get(self.METRIC_UNBLENDED_COST, {})
                cost = float(cost_data.get("Amount", 0.0))
                currency = cost_data.get("Unit", currency)

                if cost > 0:
                    services.append({"service_name": service_name, "cost": cost})
                    total_cost += cost

        services.sort(key=lambda x: x["cost"], reverse=True)

        return {
            "provider": "aws",
            "currency": currency,
            "total_cost": round(total_cost, 2),
            "services": services,
        }

    async def get_costs(
        self,
        start_date: date,
        end_date: date,
        granularity: str = GRANULARITY_DAILY,
    ) -> dict[str, Any]:
        """Retrieve and normalize AWS costs for the given date range.

        Args:
            start_date: Start date (inclusive).
            end_date: End date (inclusive).
            granularity: "DAILY" or "MONTHLY".

        Returns:
            Normalized cost data with provider, currency, total_cost, and services.

        Raises:
            AWSCredentialsError: If AWS credentials are missing or invalid.
            AWSThrottlingError: If AWS API throttles the request.
            AWSPermissionsError: If credentials lack Cost Explorer permissions.
            AWSInvalidDateRangeError: If date range is invalid.
            AWSServiceError: For other AWS service errors.
        """
        if not self._settings.aws_cost_explorer_enabled:
            logger.info("aws_cost_explorer_disabled")
            return {
                "provider": "aws",
                "currency": "USD",
                "total_cost": 0.0,
                "date_range": {
                    "start": start_date.isoformat(),
                    "end": end_date.isoformat(),
                    "granularity": granularity,
                },
                "services": [],
            }

        if granularity not in (self.GRANULARITY_DAILY, self.GRANULARITY_MONTHLY):
            raise AWSInvalidDateRangeError(f"Invalid granularity: {granularity}")

        self._validate_date_range(start_date, end_date)

        request = self._build_request(start_date, end_date, granularity)
        logger.info(
            "aws_cost_explorer_request",
            extra={
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "granularity": granularity,
            },
        )

        self._ensure_client()

        start_time = time.perf_counter()
        try:
            response = self._fetch_all_pages(request)
            elapsed_ms = int((time.perf_counter() - start_time) * 1000)

            logger.info(
                "aws_cost_explorer_response",
                extra={
                    "elapsed_ms": elapsed_ms,
                    "results_count": len(response.get("ResultsByTime", [])),
                    "page_count": response.get("PageCount", 1),
                },
            )

            normalized = self._normalize_response(response)
            normalized["date_range"] = {
                "start": start_date.isoformat(),
                "end": end_date.isoformat(),
                "granularity": granularity,
            }
            return normalized

        except NoCredentialsError as e:
            logger.error("aws_credentials_missing", extra={"error": str(e)})
            raise AWSCredentialsError("AWS credentials not found") from e
        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "")
            error_message = e.response.get("Error", {}).get("Message", "")
            elapsed_ms = int((time.perf_counter() - start_time) * 1000)

            logger.error(
                "aws_cost_explorer_error",
                extra={
                    "error_code": error_code,
                    "error_message": error_message,
                    "elapsed_ms": elapsed_ms,
                },
            )

            if error_code == "ThrottlingException":
                raise AWSThrottlingError("AWS API request throttled") from e
            if error_code in ("AccessDeniedException", "UnauthorizedOperation"):
                raise AWSPermissionsError("Insufficient AWS permissions for Cost Explorer") from e
            if error_code == "ValidationException":
                raise AWSInvalidDateRangeError(f"Invalid request: {error_message}") from e

            raise AWSServiceError(f"AWS Cost Explorer error: {error_message}") from e
        except AWSCostExplorerError:
            raise
        except Exception as e:
            elapsed_ms = int((time.perf_counter() - start_time) * 1000)
            logger.error(
                "aws_cost_explorer_unexpected_error",
                extra={"error": str(e), "elapsed_ms": elapsed_ms},
            )
            raise AWSServiceError(f"Unexpected error querying Cost Explorer: {e}") from e
