"""GCP Billing service for retrieving and normalizing cost data via BigQuery.

GCP billing data is exposed through a BigQuery dataset that the user
configures with a "Billing export to BigQuery" sink. This service
authenticates via Google Application Default Credentials (ADC), runs a
parameterised SQL aggregation against the configured export table, and
normalises the response to the same shape returned by the AWS and
Azure services.
"""

from __future__ import annotations

import logging
import time
from datetime import date
from typing import Any

from google.api_core.exceptions import (
    BadRequest,
    Forbidden,
    GoogleAPIError,
    NotFound,
    TooManyRequests,
)
from google.auth.exceptions import DefaultCredentialsError, RefreshError
from google.cloud import bigquery
from google.cloud.bigquery import Client as BigQueryClient
from google.cloud.bigquery import QueryJobConfig, ScalarQueryParameter
from google.oauth2 import service_account

from app.core.config import Settings
from app.services.gcp.exceptions import (
    GCPBigQueryError,
    GCPBillingAccountNotFoundError,
    GCPBillingError,
    GCPCredentialsError,
    GCPQuotaExceededError,
)

logger = logging.getLogger(__name__)


class GCPBillingService:
    """Service for retrieving GCP cost data via BigQuery billing export."""

    GRANULARITY_DAILY = "DAILY"
    GRANULARITY_MONTHLY = "MONTHLY"
    SUPPORTED_GRANULARITIES = (GRANULARITY_DAILY, GRANULARITY_MONTHLY)

    # BigQuery uses fully-qualified table identifiers that must be
    # back-tick quoted. We allow callers to override the project for the
    # table separate from the billing project; the table typically lives
    # in the same project as the billing export sink.
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client: BigQueryClient | None = None

    # -- Client management ----------------------------------------------------

    def _build_client(self) -> BigQueryClient:
        """Build a BigQuery client from explicit credentials or ADC.

        If ``GOOGLE_APPLICATION_CREDENTIALS`` points to a service-account
        JSON file we load credentials explicitly so that misconfiguration
        surfaces a :class:`GCPCredentialsError` with a useful message
        instead of the bare :class:`DefaultCredentialsError`.
        """
        project = self._settings.gcp_billing_project
        creds_path = self._settings.google_application_credentials

        try:
            if creds_path:
                credentials = service_account.Credentials.from_service_account_file(
                    creds_path
                )
                return bigquery.Client(
                    project=project,
                    credentials=credentials,
                )
            return bigquery.Client(project=project)
        except (DefaultCredentialsError, RefreshError) as e:
            logger.error("gcp_credentials_failed", extra={"error": str(e)})
            raise GCPCredentialsError("GCP credentials not found or invalid") from e
        except ValueError as e:
            # google.oauth2 raises ValueError for malformed key files.
            logger.error("gcp_credentials_invalid", extra={"error": str(e)})
            raise GCPCredentialsError(f"Invalid GCP credentials file: {e}") from e
        except Exception as e:  # pragma: no cover - defensive catch-all
            logger.error("gcp_client_creation_failed", extra={"error": str(e)})
            raise GCPCredentialsError(
                f"Failed to create GCP BigQuery client: {e}"
            ) from e

    def _ensure_client(self) -> BigQueryClient:
        """Lazy-initialise and cache the BigQuery client."""
        if self._client is None:
            self._client = self._build_client()
        return self._client

    # -- Validation -----------------------------------------------------------

    def _validate_date_range(self, start_date: date, end_date: date) -> None:
        """Validate the requested date range for a billing query."""
        if start_date > end_date:
            raise GCPBillingAccountNotFoundError(
                "start_date must be before or equal to end_date"
            )
        if start_date > date.today():
            raise GCPBillingAccountNotFoundError("start_date cannot be in the future")

    def _validate_config(self) -> None:
        """Validate that the GCP billing configuration is complete."""
        if not self._settings.gcp_billing_project:
            raise GCPBillingAccountNotFoundError(
                "GCP_BILLING_PROJECT is not configured"
            )
        if not self._settings.gcp_billing_dataset:
            raise GCPBillingAccountNotFoundError(
                "GCP_BILLING_DATASET is not configured"
            )
        if not self._settings.gcp_billing_table:
            raise GCPBillingAccountNotFoundError("GCP_BILLING_TABLE is not configured")

    # -- Query construction ---------------------------------------------------

    def _qualified_table(self) -> str:
        """Return the back-tick qualified fully-qualified table identifier."""
        project = self._settings.gcp_billing_project or ""
        dataset = self._settings.gcp_billing_dataset or ""
        table = self._settings.gcp_billing_table or ""
        return f"`{project}.{dataset}.{table}`"

    def _build_query(
        self,
        start_date: date,
        end_date: date,
        granularity: str,
    ) -> tuple[str, list[ScalarQueryParameter]]:
        """Build the SQL aggregation against the billing export table.

        The standard GCP billing export table exposes ``service.description``
        for the service label and ``cost`` (in billing currency) for the
        line-item cost. We aggregate per service for the requested period
        and order by descending cost so the mapper receives pre-sorted
        output.

        Date values are bound as BigQuery scalar parameters so they
        cannot be interpreted as SQL. The table identifier cannot be
        parameterised (BigQuery limitation) and is operator-controlled
        via :class:`Settings` rather than user input.
        """
        table = self._qualified_table()
        params = [
            ScalarQueryParameter("start_date", "DATE", start_date.isoformat()),
            ScalarQueryParameter("end_date", "DATE", end_date.isoformat()),
        ]
        return (
            "SELECT service.description AS service_name, "
            "SUM(cost) AS total_cost, "
            "ANY_VALUE(currency) AS currency "
            f"FROM {table} "  # nosec B608 — operator-configured table id, not user input
            "WHERE DATE(usage_start_time) >= @start_date "
            "AND DATE(usage_start_time) <= @end_date "
            "GROUP BY service_name "
            "ORDER BY total_cost DESC"
        ), params

    # -- Query execution ------------------------------------------------------

    def _execute_query(
        self,
        sql: str,
        params: list[ScalarQueryParameter],
    ) -> list[dict[str, Any]]:
        """Execute ``sql`` with ``params`` and return the result rows as dicts."""
        client = self._ensure_client()
        try:
            job_config = QueryJobConfig(query_parameters=params)
            job = client.query(sql, job_config=job_config)
            rows = list(job.result())
        except TooManyRequests as e:
            logger.error("gcp_bigquery_quota_exceeded", extra={"error": str(e)})
            raise GCPQuotaExceededError("GCP BigQuery quota exceeded") from e
        except Forbidden as e:
            logger.error("gcp_bigquery_forbidden", extra={"error": str(e)})
            raise GCPCredentialsError(
                "Insufficient GCP permissions for BigQuery billing export"
            ) from e
        except NotFound as e:
            logger.error("gcp_billing_table_not_found", extra={"error": str(e)})
            raise GCPBillingAccountNotFoundError(
                "GCP billing export table not found"
            ) from e
        except BadRequest as e:
            logger.error("gcp_bigquery_bad_request", extra={"error": str(e)})
            raise GCPBillingAccountNotFoundError(
                f"Invalid GCP BigQuery request: {e}"
            ) from e
        except GoogleAPIError as e:
            logger.error("gcp_bigquery_error", extra={"error": str(e)})
            raise GCPBigQueryError(f"GCP BigQuery error: {e}") from e
        except DefaultCredentialsError as e:
            logger.error("gcp_credentials_missing", extra={"error": str(e)})
            raise GCPCredentialsError("GCP credentials not found or invalid") from e

        return [dict(row) for row in rows]

    # -- Normalization --------------------------------------------------------

    def _normalize_response(
        self,
        rows: list[dict[str, Any]],
        start_date: date,
        end_date: date,
        granularity: str,
    ) -> dict[str, Any]:
        """Normalize BigQuery rows into the unified cost response shape."""
        services: list[dict[str, Any]] = []
        total_cost = 0.0
        currency = "USD"

        for row in rows:
            service_name = row.get("service_name") or "Unknown"
            try:
                cost = float(row.get("total_cost") or 0.0)
            except (TypeError, ValueError):
                cost = 0.0

            if row.get("currency"):
                currency = str(row["currency"])

            if cost > 0:
                services.append(
                    {"service_name": str(service_name), "cost": round(cost, 2)}
                )
                total_cost += cost

        return {
            "provider": "gcp",
            "currency": currency,
            "total_cost": round(total_cost, 2),
            "date_range": {
                "start": start_date.isoformat(),
                "end": end_date.isoformat(),
                "granularity": granularity,
            },
            "services": services,
        }

    # -- Public API -----------------------------------------------------------

    async def get_costs(
        self,
        start_date: date,
        end_date: date,
        granularity: str,
    ) -> dict[str, Any]:
        """Retrieve and normalize GCP costs for the given date range.

        Args:
            start_date: Start date (inclusive).
            end_date: End date (inclusive).
            granularity: ``"DAILY"`` or ``"MONTHLY"`` (currently informational;
                BigQuery billing export is inherently aggregated by usage
                rows, so granularity does not change the SQL).

        Returns:
            Normalized cost data with keys ``provider``, ``currency``,
            ``total_cost``, ``date_range``, and ``services``.

        Raises:
            GCPCredentialsError: When GCP credentials are missing or invalid.
            GCPQuotaExceededError: When BigQuery returns a quota error.
            GCPBillingAccountNotFoundError: When the export table cannot be
                resolved or the date range is invalid.
            GCPBigQueryError: For other BigQuery service errors.
        """
        if not self._settings.gcp_billing_enabled:
            logger.info("gcp_billing_disabled")
            return {
                "provider": "gcp",
                "currency": "USD",
                "total_cost": 0.0,
                "date_range": {
                    "start": start_date.isoformat(),
                    "end": end_date.isoformat(),
                    "granularity": granularity,
                },
                "services": [],
            }

        if granularity not in self.SUPPORTED_GRANULARITIES:
            raise GCPBillingAccountNotFoundError(f"Invalid granularity: {granularity}")

        self._validate_config()
        self._validate_date_range(start_date, end_date)

        sql, params = self._build_query(start_date, end_date, granularity)
        logger.info(
            "gcp_billing_request",
            extra={
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "granularity": granularity,
            },
        )

        start_time = time.perf_counter()
        try:
            rows = self._execute_query(sql, params)
        except GCPBillingError:
            # All GCP-specific errors are already correctly typed by
            # ``_execute_query``; let them propagate untouched so callers
            # can react to credentials / quota / not-found conditions
            # distinctly from generic BigQuery failures.
            raise
        except Exception as e:  # pragma: no cover - defensive catch-all
            elapsed_ms = int((time.perf_counter() - start_time) * 1000)
            logger.error(
                "gcp_billing_unexpected_error",
                extra={"error": str(e), "elapsed_ms": elapsed_ms},
            )
            raise GCPBigQueryError(
                f"Unexpected error querying GCP billing export: {e}"
            ) from e

        elapsed_ms = int((time.perf_counter() - start_time) * 1000)
        logger.info(
            "gcp_billing_response",
            extra={
                "elapsed_ms": elapsed_ms,
                "rows": len(rows),
            },
        )

        return self._normalize_response(rows, start_date, end_date, granularity)
