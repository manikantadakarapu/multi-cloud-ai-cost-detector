"""AWS implementation of the :class:`CloudProvider` abstraction.

:class:`AWSCloudProvider` wraps the existing
:class:`app.services.aws.cost_explorer.CostExplorerService`, translates
its vendor-specific exceptions into the provider-agnostic hierarchy
defined in :mod:`app.providers.exceptions`, and exposes the result as a
:class:`app.providers.schemas.CostResponse` via :class:`app.providers.aws.mapper.AWSMapper`.
"""

from __future__ import annotations

from datetime import date

from botocore.exceptions import ClientError, NoCredentialsError

from app.core.config import settings as app_settings
from app.providers.aws.mapper import AWSMapper
from app.providers.base import CloudProvider
from app.providers.exceptions import (
    ProviderCredentialsError,
    ProviderInvalidDateRangeError,
    ProviderPermissionsError,
    ProviderServiceError,
    ProviderThrottlingError,
)
from app.providers.schemas import CostResponse
from app.services.aws.cost_explorer import CostExplorerService
from app.services.aws.exceptions import (
    AWSCredentialsError,
    AWSInvalidDateRangeError,
    AWSPermissionsError,
    AWSServiceError,
    AWSThrottlingError,
)


class AWSCloudProvider(CloudProvider):
    """Cloud provider implementation backed by AWS Cost Explorer."""

    def __init__(self) -> None:
        self._service = CostExplorerService(app_settings)
        self._mapper = AWSMapper()

    def provider_name(self) -> str:
        """Return the short provider identifier."""
        return "aws"

    def authenticate(self) -> None:
        """Initialise the underlying boto3 client.

        Lets credential errors propagate so callers can surface them
        via :meth:`validate_credentials` or :meth:`get_costs`.
        """
        self._service._ensure_client()
        return None

    def validate_credentials(self) -> bool:
        """Return ``True`` when configured AWS credentials are usable."""
        try:
            self.authenticate()
        except (AWSCredentialsError, NoCredentialsError):
            return False
        return True

    async def get_costs(
        self,
        start_date: date,
        end_date: date,
        granularity: str,
    ) -> CostResponse:
        """Retrieve normalized AWS costs and translate AWS errors.

        AWS-specific exceptions raised by the underlying service are
        converted to the provider-agnostic hierarchy so route handlers
        can react without depending on the AWS SDK.
        """
        try:
            raw = await self._service.get_costs(
                start_date=start_date,
                end_date=end_date,
                granularity=granularity,
            )
        except AWSCredentialsError as e:
            raise ProviderCredentialsError(str(e.message)) from e
        except NoCredentialsError as e:
            raise ProviderCredentialsError(str(e)) from e
        except AWSThrottlingError as e:
            raise ProviderThrottlingError(str(e.message)) from e
        except AWSPermissionsError as e:
            raise ProviderPermissionsError(str(e.message)) from e
        except AWSInvalidDateRangeError as e:
            raise ProviderInvalidDateRangeError(str(e.message)) from e
        except AWSServiceError as e:
            raise ProviderServiceError(str(e.message)) from e
        except ClientError as e:
            raise ProviderServiceError(f"AWS service error: {e}") from e

        return self._mapper.map(
            raw,
            start_date=start_date,
            end_date=end_date,
            granularity=granularity,
        )
