"""GCP implementation of the :class:`CloudProvider` abstraction.

:class:`GCPCloudProvider` wraps the existing
:class:`app.services.gcp.billing.GCPBillingService`, translates its
vendor-specific exceptions into the provider-agnostic hierarchy
defined in :mod:`app.providers.exceptions`, and exposes the result as a
:class:`app.providers.schemas.CostResponse` via
:class:`app.providers.gcp.mapper.GCPMapper`.
"""

from __future__ import annotations

from datetime import date

from google.api_core.exceptions import Forbidden, GoogleAPIError
from google.auth.exceptions import DefaultCredentialsError, RefreshError

from app.core.config import settings as app_settings
from app.providers.base import CloudProvider
from app.providers.exceptions import (
    ProviderCredentialsError,
    ProviderInvalidDateRangeError,
    ProviderServiceError,
    ProviderThrottlingError,
)
from app.providers.gcp.mapper import GCPMapper
from app.providers.schemas import CostResponse
from app.services.gcp.billing import GCPBillingService
from app.services.gcp.exceptions import (
    GCPBigQueryError,
    GCPBillingAccountNotFoundError,
    GCPCredentialsError,
    GCPQuotaExceededError,
)


class GCPCloudProvider(CloudProvider):
    """Cloud provider implementation backed by GCP BigQuery billing export."""

    def __init__(self) -> None:
        self._service = GCPBillingService(app_settings)
        self._mapper = GCPMapper()

    def provider_name(self) -> str:
        """Return the short provider identifier."""
        return "gcp"

    def authenticate(self) -> None:
        """Initialise the underlying BigQuery client.

        Lets credential errors propagate so callers can surface them
        via :meth:`validate_credentials` or :meth:`get_costs`.
        """
        self._service._ensure_client()
        return None

    def validate_credentials(self) -> bool:
        """Return ``True`` when configured GCP credentials are usable."""
        try:
            self.authenticate()
        except (
            GCPCredentialsError,
            DefaultCredentialsError,
            RefreshError,
        ):
            return False
        return True

    async def get_costs(
        self,
        start_date: date,
        end_date: date,
        granularity: str,
    ) -> CostResponse:
        """Retrieve normalized GCP costs and translate GCP errors.

        GCP-specific exceptions raised by the underlying service are
        converted to the provider-agnostic hierarchy so route handlers
        can react without depending on the BigQuery SDK.
        """
        try:
            raw = await self._service.get_costs(
                start_date=start_date,
                end_date=end_date,
                granularity=granularity,
            )
        except GCPCredentialsError as e:
            raise ProviderCredentialsError(str(e.message)) from e
        except GCPQuotaExceededError as e:
            raise ProviderThrottlingError(str(e.message)) from e
        except GCPBillingAccountNotFoundError as e:
            raise ProviderInvalidDateRangeError(str(e.message)) from e
        except GCPBigQueryError as e:
            raise ProviderServiceError(str(e.message)) from e
        except (DefaultCredentialsError, RefreshError) as e:
            raise ProviderCredentialsError(str(e)) from e
        except Forbidden as e:
            raise ProviderCredentialsError(
                "Insufficient GCP permissions for BigQuery billing export"
            ) from e
        except GoogleAPIError as e:
            raise ProviderServiceError(f"GCP service error: {e}") from e

        return self._mapper.map(
            raw,
            start_date=start_date,
            end_date=end_date,
            granularity=granularity,
        )
