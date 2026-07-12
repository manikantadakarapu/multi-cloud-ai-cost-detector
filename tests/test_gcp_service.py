"""Tests for the GCP :class:`GCPBillingService`."""

from __future__ import annotations

from datetime import date
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from google.api_core.exceptions import (
    BadRequest,
    Forbidden,
    GoogleAPIError,
    NotFound,
    TooManyRequests,
)
from google.auth.exceptions import DefaultCredentialsError

from app.core.config import Settings
from app.services.gcp import billing as billing_module
from app.services.gcp.billing import GCPBillingService
from app.services.gcp.exceptions import (
    GCPBigQueryError,
    GCPBillingAccountNotFoundError,
    GCPCredentialsError,
    GCPQuotaExceededError,
)


def _make_settings(**overrides: Any) -> Settings:
    base = {
        "JWT_SECRET_KEY": "test-secret",
        "GCP_BILLING_ENABLED": True,
        "GOOGLE_APPLICATION_CREDENTIALS": None,
        "GCP_BILLING_ACCOUNT": "012345-678901-234567",
        "GCP_BILLING_PROJECT": "billing-project",
        "GCP_BILLING_DATASET": "billing_dataset",
        "GCP_BILLING_TABLE": "gcp_billing_export_v1",
    }
    base.update(overrides)
    return Settings(**base)


@pytest.fixture
def service() -> GCPBillingService:
    return GCPBillingService(_make_settings())


class _BigQueryRow(dict):
    """Mimic ``google.cloud.bigquery.Row`` (dict + attribute access)."""

    def __getattr__(self, key: str) -> Any:
        try:
            return self[key]
        except KeyError as e:
            raise AttributeError(key) from e


def _row(service_name: str, cost: float, currency: str = "USD") -> _BigQueryRow:
    return _BigQueryRow(service_name=service_name, total_cost=cost, currency=currency)


class TestGCPBillingService:
    @pytest.mark.asyncio
    async def test_disabled_returns_empty_response(self) -> None:
        settings = _make_settings(GCP_BILLING_ENABLED=False)
        svc = GCPBillingService(settings)

        with patch.object(billing_module, "bigquery") as mock_bq:
            result = await svc.get_costs(
                start_date=date(2024, 1, 1),
                end_date=date(2024, 1, 31),
                granularity="DAILY",
            )

        assert result["provider"] == "gcp"
        assert result["currency"] == "USD"
        assert result["total_cost"] == 0.0
        assert result["services"] == []
        assert result["date_range"] == {
            "start": "2024-01-01",
            "end": "2024-01-31",
            "granularity": "DAILY",
        }
        mock_bq.Client.assert_not_called()

    @pytest.mark.asyncio
    async def test_invalid_granularity_raises(self, service: GCPBillingService) -> None:
        with pytest.raises(GCPBillingAccountNotFoundError):
            await service.get_costs(
                start_date=date(2024, 1, 1),
                end_date=date(2024, 1, 31),
                granularity="WEEKLY",
            )

    @pytest.mark.asyncio
    async def test_missing_project_config_raises(
        self, service: GCPBillingService
    ) -> None:
        settings = _make_settings(GCP_BILLING_PROJECT=None)
        svc = GCPBillingService(settings)
        with pytest.raises(GCPBillingAccountNotFoundError):
            await svc.get_costs(
                start_date=date(2024, 1, 1),
                end_date=date(2024, 1, 31),
                granularity="DAILY",
            )

    @pytest.mark.asyncio
    async def test_missing_dataset_config_raises(
        self, service: GCPBillingService
    ) -> None:
        settings = _make_settings(GCP_BILLING_DATASET=None)
        svc = GCPBillingService(settings)
        with pytest.raises(GCPBillingAccountNotFoundError):
            await svc.get_costs(
                start_date=date(2024, 1, 1),
                end_date=date(2024, 1, 31),
                granularity="DAILY",
            )

    @pytest.mark.asyncio
    async def test_missing_table_config_raises(
        self, service: GCPBillingService
    ) -> None:
        settings = _make_settings(GCP_BILLING_TABLE=None)
        svc = GCPBillingService(settings)
        with pytest.raises(GCPBillingAccountNotFoundError):
            await svc.get_costs(
                start_date=date(2024, 1, 1),
                end_date=date(2024, 1, 31),
                granularity="DAILY",
            )

    @pytest.mark.asyncio
    async def test_start_after_end_raises(self, service: GCPBillingService) -> None:
        with pytest.raises(GCPBillingAccountNotFoundError):
            await service.get_costs(
                start_date=date(2024, 2, 1),
                end_date=date(2024, 1, 1),
                granularity="DAILY",
            )

    @pytest.mark.asyncio
    async def test_start_in_future_raises(self, service: GCPBillingService) -> None:
        with pytest.raises(GCPBillingAccountNotFoundError):
            await service.get_costs(
                start_date=date(2099, 1, 1),
                end_date=date(2099, 1, 31),
                granularity="DAILY",
            )

    @pytest.mark.asyncio
    async def test_successful_query_normalizes_rows(
        self, service: GCPBillingService
    ) -> None:
        rows = [
            _row("Compute Engine", 123.456, "USD"),
            _row("Cloud Storage", 45.67, "USD"),
            _row("BigQuery", 0.0, "USD"),  # zero-cost rows are dropped
            _row("Pub/Sub", 7.5, "USD"),
        ]

        with patch.object(billing_module, "bigquery") as mock_bq:
            mock_client = MagicMock()
            mock_bq.Client.return_value = mock_client
            mock_job = MagicMock()
            mock_client.query.return_value = mock_job
            mock_job.result.return_value = rows

            result = await service.get_costs(
                start_date=date(2024, 1, 1),
                end_date=date(2024, 1, 31),
                granularity="DAILY",
            )

        assert result["provider"] == "gcp"
        assert result["currency"] == "USD"
        assert result["total_cost"] == 176.63
        assert [s["service_name"] for s in result["services"]] == [
            "Compute Engine",
            "Cloud Storage",
            "Pub/Sub",
        ]
        assert result["date_range"] == {
            "start": "2024-01-01",
            "end": "2024-01-31",
            "granularity": "DAILY",
        }

        # SQL should be well-formed, reference the configured table, and
        # use parameter placeholders so user-controlled values cannot be
        # interpreted as SQL.
        query = mock_client.query.call_args.args[0]
        assert "`billing-project.billing_dataset.gcp_billing_export_v1`" in query
        assert "service.description AS service_name" in query
        assert "SUM(cost)" in query
        assert "GROUP BY service_name" in query
        assert "@start_date" in query
        assert "@end_date" in query
        assert "2024-01-01" not in query
        assert "2024-01-31" not in query

        # Date values must be bound via QueryJobConfig.query_parameters,
        # not interpolated into the SQL string.
        job_config = mock_client.query.call_args.kwargs["job_config"]
        param_names = [p.name for p in job_config.query_parameters]
        assert param_names == ["start_date", "end_date"]
        param_values = [p.value for p in job_config.query_parameters]
        assert [
            (v.isoformat() if hasattr(v, "isoformat") else v) for v in param_values
        ] == [
            "2024-01-01",
            "2024-01-31",
        ]

    @pytest.mark.asyncio
    async def test_quota_exceeded_translates(self, service: GCPBillingService) -> None:
        with patch.object(billing_module, "bigquery") as mock_bq:
            mock_client = MagicMock()
            mock_bq.Client.return_value = mock_client
            mock_job = MagicMock()
            mock_client.query.return_value = mock_job
            mock_job.result.side_effect = TooManyRequests("rate limited")

            with pytest.raises(GCPQuotaExceededError):
                await service.get_costs(
                    start_date=date(2024, 1, 1),
                    end_date=date(2024, 1, 31),
                    granularity="DAILY",
                )

    @pytest.mark.asyncio
    async def test_forbidden_translates_to_credentials_error(
        self, service: GCPBillingService
    ) -> None:
        with patch.object(billing_module, "bigquery") as mock_bq:
            mock_client = MagicMock()
            mock_bq.Client.return_value = mock_client
            mock_job = MagicMock()
            mock_client.query.return_value = mock_job
            mock_job.result.side_effect = Forbidden("denied")

            with pytest.raises(GCPCredentialsError):
                await service.get_costs(
                    start_date=date(2024, 1, 1),
                    end_date=date(2024, 1, 31),
                    granularity="DAILY",
                )

    @pytest.mark.asyncio
    async def test_not_found_translates_to_billing_account_error(
        self, service: GCPBillingService
    ) -> None:
        with patch.object(billing_module, "bigquery") as mock_bq:
            mock_client = MagicMock()
            mock_bq.Client.return_value = mock_client
            mock_job = MagicMock()
            mock_client.query.return_value = mock_job
            mock_job.result.side_effect = NotFound("missing table")

            with pytest.raises(GCPBillingAccountNotFoundError):
                await service.get_costs(
                    start_date=date(2024, 1, 1),
                    end_date=date(2024, 1, 31),
                    granularity="DAILY",
                )

    @pytest.mark.asyncio
    async def test_bad_request_translates_to_billing_account_error(
        self, service: GCPBillingService
    ) -> None:
        with patch.object(billing_module, "bigquery") as mock_bq:
            mock_client = MagicMock()
            mock_bq.Client.return_value = mock_client
            mock_job = MagicMock()
            mock_client.query.return_value = mock_job
            mock_job.result.side_effect = BadRequest("bad sql")

            with pytest.raises(GCPBillingAccountNotFoundError):
                await service.get_costs(
                    start_date=date(2024, 1, 1),
                    end_date=date(2024, 1, 31),
                    granularity="DAILY",
                )

    @pytest.mark.asyncio
    async def test_generic_bigquery_error_translates(
        self, service: GCPBillingService
    ) -> None:
        with patch.object(billing_module, "bigquery") as mock_bq:
            mock_client = MagicMock()
            mock_bq.Client.return_value = mock_client
            mock_job = MagicMock()
            mock_client.query.return_value = mock_job
            mock_job.result.side_effect = GoogleAPIError("boom")

            with pytest.raises(GCPBigQueryError):
                await service.get_costs(
                    start_date=date(2024, 1, 1),
                    end_date=date(2024, 1, 31),
                    granularity="DAILY",
                )

    def test_explicit_credentials_path_uses_service_account(self) -> None:
        """When GOOGLE_APPLICATION_CREDENTIALS is set, load via service_account."""
        settings = _make_settings(GOOGLE_APPLICATION_CREDENTIALS="/path/to/creds.json")
        svc = GCPBillingService(settings)

        with (
            patch.object(billing_module, "service_account") as mock_sa,
            patch.object(billing_module, "bigquery") as mock_bq,
        ):
            mock_sa.Credentials.from_service_account_file.return_value = MagicMock()
            mock_bq.Client.return_value = MagicMock()
            svc._build_client()

        mock_sa.Credentials.from_service_account_file.assert_called_once_with(
            "/path/to/creds.json"
        )
        mock_bq.Client.assert_called_once()
        call_kwargs = mock_bq.Client.call_args.kwargs
        assert "credentials" in call_kwargs
        assert call_kwargs["project"] == "billing-project"

    def test_missing_credentials_raises_credentials_error(self) -> None:
        """Bare DefaultCredentialsError from google.cloud maps to GCPCredentialsError."""
        settings = _make_settings(
            GOOGLE_APPLICATION_CREDENTIALS=None,
            GCP_BILLING_PROJECT=None,  # so bigquery.Client raises ValueError via ADC path
        )
        svc = GCPBillingService(settings)

        with patch.object(billing_module, "bigquery") as mock_bq:
            mock_bq.Client.side_effect = DefaultCredentialsError("no creds")
            with pytest.raises(GCPCredentialsError):
                svc._build_client()

    def test_malformed_credentials_file_raises_credentials_error(self) -> None:
        settings = _make_settings(GOOGLE_APPLICATION_CREDENTIALS="/path/to/bad.json")
        svc = GCPBillingService(settings)

        with patch.object(billing_module, "service_account") as mock_sa:
            mock_sa.Credentials.from_service_account_file.side_effect = ValueError(
                "bad json"
            )
            with pytest.raises(GCPCredentialsError):
                svc._build_client()
