from __future__ import annotations

import pytest

from app.services.azure.exceptions import (
    AzureCostManagementError,
    AzureCredentialsError,
    AzureInvalidSubscriptionError,
    AzurePermissionsError,
    AzureServiceError,
    AzureThrottlingError,
)


class TestAzureExceptions:
    @pytest.mark.parametrize(
        "exc_class, default_code",
        [
            (AzureCredentialsError, "AZURE_CREDENTIALS_ERROR"),
            (AzureThrottlingError, "AZURE_THROTTLING_ERROR"),
            (AzurePermissionsError, "AZURE_PERMISSIONS_ERROR"),
            (AzureInvalidSubscriptionError, "AZURE_INVALID_SUBSCRIPTION"),
            (AzureServiceError, "AZURE_SERVICE_ERROR"),
        ],
    )
    def test_default_error_code(
        self, exc_class: type[AzureCostManagementError], default_code: str
    ) -> None:
        exc = exc_class()
        assert exc.error_code == default_code
        assert isinstance(exc.message, str)
