"""Azure implementation of the :class:`CloudProvider` abstraction.

:class:`AzureCloudProvider` wraps the existing
:class:`app.services.azure.cost_management.AzureCostManagementService`,
translates its vendor-specific exceptions into the provider-agnostic
hierarchy defined in :mod:`app.providers.exceptions`, and exposes the
result as a :class:`app.providers.schemas.CostResponse` via
:class:`app.providers.azure.mapper.AzureMapper`.
"""

from __future__ import annotations

from datetime import date

from azure.core.exceptions import AzureError, ClientAuthenticationError

from app.core.config import settings as app_settings
from app.providers.azure.mapper import AzureMapper
from app.providers.base import CloudProvider
from app.providers.exceptions import (
    ProviderCredentialsError,
    ProviderInvalidDateRangeError,
    ProviderPermissionsError,
    ProviderServiceError,
    ProviderThrottlingError,
)
from app.providers.schemas import CostResponse
from app.services.azure.cost_management import AzureCostManagementService
from app.services.azure.exceptions import (
    AzureCredentialsError,
    AzureInvalidSubscriptionError,
    AzurePermissionsError,
    AzureServiceError,
    AzureThrottlingError,
)


class AzureCloudProvider(CloudProvider):
    """Cloud provider implementation backed by Azure Cost Management."""

    def __init__(self) -> None:
        self._service = AzureCostManagementService(app_settings)
        self._mapper = AzureMapper()

    def provider_name(self) -> str:
        """Return the short provider identifier."""
        return "azure"

    def authenticate(self) -> None:
        """Initialise the underlying Azure credential.

        Lets credential errors propagate so callers can surface them
        via :meth:`validate_credentials` or :meth:`get_costs`.
        """
        self._service._ensure_credential()
        return None

    def validate_credentials(self) -> bool:
        """Return ``True`` when configured Azure credentials are usable."""
        try:
            self.authenticate()
        except (AzureCredentialsError, ClientAuthenticationError):
            return False
        return True

    async def get_costs(
        self,
        start_date: date,
        end_date: date,
        granularity: str,
    ) -> CostResponse:
        """Retrieve normalized Azure costs and translate Azure errors.

        Azure-specific exceptions raised by the underlying service are
        converted to the provider-agnostic hierarchy so route handlers
        can react without depending on the Azure SDK.
        """
        try:
            raw = await self._service.get_costs(
                start_date=start_date,
                end_date=end_date,
                granularity=granularity,
            )
        except AzureCredentialsError as e:
            raise ProviderCredentialsError(str(e.message)) from e
        except AzureThrottlingError as e:
            raise ProviderThrottlingError(str(e.message)) from e
        except AzurePermissionsError as e:
            raise ProviderPermissionsError(str(e.message)) from e
        except AzureInvalidSubscriptionError as e:
            raise ProviderInvalidDateRangeError(str(e.message)) from e
        except AzureServiceError as e:
            raise ProviderServiceError(str(e.message)) from e
        except ClientAuthenticationError as e:
            raise ProviderCredentialsError(str(e)) from e
        except AzureError as e:
            raise ProviderServiceError(f"Azure service error: {e}") from e

        return self._mapper.map(
            raw,
            start_date=start_date,
            end_date=end_date,
            granularity=granularity,
        )
