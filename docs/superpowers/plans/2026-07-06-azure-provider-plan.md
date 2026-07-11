# Azure Cost Management Provider Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a production-quality Azure cost provider that implements the existing `CloudProvider` interface, exposes `GET /api/v1/azure/costs`, and returns the normalized `CostResponse` used by AWS.

**Architecture:** Mirror the AWS structure: an internal `AzureCostManagementService` wraps the Azure SDK, an `AzureCloudProvider` implements the shared interface, an `AzureMapper` converts SDK responses to `CostResponse`, and a FastAPI route injects the provider via the registry. Authentication uses `DefaultAzureCredential` with optional service-principal settings; subscription resolution prefers a configured ID and falls back to the default subscription.

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, pytest, azure-identity, azure-mgmt-costmanagement, azure-mgmt-subscription.

---

## Task 1: Add Azure SDK dependencies and settings

**Files:**
- Modify: `pyproject.toml`
- Modify: `app/core/config.py`
- Test: existing config tests should still pass

- [ ] **Step 1: Add Azure SDK packages to dependencies**

In `pyproject.toml`, add these lines to the `[project] dependencies` list (keep alphabetical order where reasonable):

```toml
"azure-identity>=1.16.0,<2.0.0",
"azure-mgmt-costmanagement>=4.0.0,<5.0.0",
"azure-mgmt-subscription>=3.1.1,<4.0.0",
```

- [ ] **Step 2: Add Azure settings fields**

In `app/core/config.py`, add after the AWS Cost Explorer block:

```python
    # --- Azure Cost Management ---
    azure_cost_management_enabled: bool = Field(
        default=True,
        validation_alias="AZURE_COST_MANAGEMENT_ENABLED",
    )
    azure_subscription_id: str | None = Field(
        default=None,
        validation_alias="AZURE_SUBSCRIPTION_ID",
    )
    azure_tenant_id: str | None = Field(
        default=None,
        validation_alias="AZURE_TENANT_ID",
    )
    azure_client_id: str | None = Field(
        default=None,
        validation_alias="AZURE_CLIENT_ID",
    )
    azure_client_secret: str | None = Field(
        default=None,
        validation_alias="AZURE_CLIENT_SECRET",
    )
```

- [ ] **Step 3: Install dependencies**

Run:

```bash
.venv/bin/pip install -e ".[dev]"
```

Expected: packages install without errors.

- [ ] **Step 4: Verify config tests still pass**

Run:

```bash
.venv/bin/pytest tests/test_config.py -q
```

Expected: all tests pass.

---

## Task 2: Create Azure-specific exceptions

**Files:**
- Create: `app/services/azure/__init__.py`
- Create: `app/services/azure/exceptions.py`
- Test: `tests/test_azure_exceptions.py`

- [ ] **Step 1: Write the exception hierarchy**

Create `app/services/azure/exceptions.py`:

```python
"""Azure Cost Management specific exceptions."""

from __future__ import annotations


class AzureCostManagementError(Exception):
    """Base exception for Azure Cost Management errors."""

    def __init__(
        self, message: str, error_code: str = "AZURE_COST_MANAGEMENT_ERROR"
    ) -> None:
        self.message = message
        self.error_code = error_code
        super().__init__(message)


class AzureCredentialsError(AzureCostManagementError):
    """Raised when Azure credentials are missing or invalid."""

    def __init__(self, message: str = "Azure credentials not found or invalid") -> None:
        super().__init__(message, error_code="AZURE_CREDENTIALS_ERROR")


class AzureThrottlingError(AzureCostManagementError):
    """Raised when Azure API throttles the request."""

    def __init__(self, message: str = "Azure API request throttled") -> None:
        super().__init__(message, error_code="AZURE_THROTTLING_ERROR")


class AzurePermissionsError(AzureCostManagementError):
    """Raised when credentials lack required permissions."""

    def __init__(
        self, message: str = "Insufficient Azure permissions for Cost Management"
    ) -> None:
        super().__init__(message, error_code="AZURE_PERMISSIONS_ERROR")


class AzureInvalidSubscriptionError(AzureCostManagementError):
    """Raised when the Azure subscription is invalid or cannot be resolved."""

    def __init__(self, message: str = "Invalid or missing Azure subscription") -> None:
        super().__init__(message, error_code="AZURE_INVALID_SUBSCRIPTION")


class AzureServiceError(AzureCostManagementError):
    """Raised for unexpected Azure service errors."""

    def __init__(self, message: str = "Azure Cost Management service error") -> None:
        super().__init__(message, error_code="AZURE_SERVICE_ERROR")
```

Create `app/services/azure/__init__.py`:

```python
"""Azure services package."""

from __future__ import annotations

from app.services.azure.exceptions import (
    AzureCostManagementError,
    AzureCredentialsError,
    AzureInvalidSubscriptionError,
    AzurePermissionsError,
    AzureServiceError,
    AzureThrottlingError,
)

__all__ = [
    "AzureCostManagementError",
    "AzureCredentialsError",
    "AzureInvalidSubscriptionError",
    "AzurePermissionsError",
    "AzureServiceError",
    "AzureThrottlingError",
]
```

- [ ] **Step 2: Write exception tests**

Create `tests/test_azure_exceptions.py`:

```python
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
```

- [ ] **Step 3: Run exception tests**

```bash
.venv/bin/pytest tests/test_azure_exceptions.py -q
```

Expected: 5 passed.

---

## Task 3: Create Azure Cost Management service

**Files:**
- Create: `app/services/azure/cost_management.py`
- Test: `tests/test_azure_service.py`

- [ ] **Step 1: Implement the service**

Create `app/services/azure/cost_management.py`. Key behavior:

- Accept `Settings` in `__init__`.
- `_ensure_credential()` returns `DefaultAzureCredential` (optionally using `tenant_id`, `client_id`, `client_secret` via `EnvironmentCredential` or direct `ClientSecretCredential` when all three are provided; otherwise `DefaultAzureCredential`).
- `_resolve_subscription_id()` returns configured subscription ID or queries default via `SubscriptionClient`.
- `get_costs(start_date, end_date, granularity)` returns a normalized dict with keys `provider`, `currency`, `total_cost`, `services`, and `date_range`.
- If `azure_cost_management_enabled` is false, return empty response dict immediately.

Skeleton implementation (fill in):

```python
"""Azure Cost Management service for retrieving and normalizing cost data."""

from __future__ import annotations

import logging
from datetime import date
from typing import Any

from azure.core.exceptions import AzureError, ClientAuthenticationError, HttpResponseError, ServiceRequestError
from azure.identity import DefaultAzureCredential, ClientSecretCredential
from azure.mgmt.costmanagement import CostManagementClient
from azure.mgmt.subscription import SubscriptionClient

from app.core.config import Settings
from app.services.azure.exceptions import (
    AzureCredentialsError,
    AzureInvalidSubscriptionError,
    AzurePermissionsError,
    AzureServiceError,
    AzureThrottlingError,
)

logger = logging.getLogger(__name__)


class AzureCostManagementService:
    """Service for retrieving Azure cost data via Cost Management Query API."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._credential: Any | None = None
        self._cost_client: CostManagementClient | None = None
        self._subscription_client: SubscriptionClient | None = None

    def _ensure_credential(self) -> Any:
        if self._credential is not None:
            return self._credential
        try:
            tenant_id = self._settings.azure_tenant_id
            client_id = self._settings.azure_client_id
            client_secret = self._settings.azure_client_secret
            if tenant_id and client_id and client_secret:
                self._credential = ClientSecretCredential(
                    tenant_id=tenant_id,
                    client_id=client_id,
                    client_secret=client_secret,
                )
            else:
                self._credential = DefaultAzureCredential(
                    tenant_id=tenant_id,
                    managed_identity_client_id=client_id or None,
                )
            return self._credential
        except AzureError as e:
            logger.error("azure_credential_failed", extra={"error": str(e)})
            raise AzureCredentialsError(f"Failed to create Azure credential: {e}") from e

    def _resolve_subscription_id(self) -> str:
        configured = self._settings.azure_subscription_id
        if configured:
            return configured
        try:
            credential = self._ensure_credential()
            if self._subscription_client is None:
                self._subscription_client = SubscriptionClient(credential)
            for subscription in self._subscription_client.subscriptions.list():
                if getattr(subscription, "state", None) == "Enabled":
                    return str(subscription.subscription_id)
        except ClientAuthenticationError as e:
            raise AzureCredentialsError("Azure credentials not found or invalid") from e
        except HttpResponseError as e:
            raise AzurePermissionsError("Insufficient permissions to list subscriptions") from e
        except AzureError as e:
            raise AzureServiceError(f"Failed to resolve subscription: {e}") from e
        raise AzureInvalidSubscriptionError("No enabled Azure subscription found")

    def _build_query(
        self,
        start_date: date,
        end_date: date,
        granularity: str,
    ) -> dict[str, Any]:
        return {
            "type": "Usage",
            "timeframe": "Custom",
            "time_period": {
                "from": start_date.isoformat(),
                "to": end_date.isoformat(),
            },
            "dataset": {
                "granularity": granularity.capitalize(),
                "aggregation": {
                    "totalCost": {"name": "Cost", "function": "Sum"},
                },
                "grouping": [{"type": "Dimension", "name": "ServiceName"}],
            },
        }

    async def get_costs(
        self,
        start_date: date,
        end_date: date,
        granularity: str,
    ) -> dict[str, Any]:
        if not self._settings.azure_cost_management_enabled:
            return {
                "provider": "azure",
                "currency": "USD",
                "total_cost": 0.0,
                "date_range": {
                    "start": start_date.isoformat(),
                    "end": end_date.isoformat(),
                    "granularity": granularity,
                },
                "services": [],
            }

        if granularity not in ("DAILY", "MONTHLY"):
            raise AzureInvalidSubscriptionError(f"Invalid granularity: {granularity}")

        subscription_id = self._resolve_subscription_id()
        scope = f"/subscriptions/{subscription_id}"
        query = self._build_query(start_date, end_date, granularity)

        try:
            credential = self._ensure_credential()
            if self._cost_client is None:
                self._cost_client = CostManagementClient(credential)
            result = self._cost_client.query.usage(scope, query)
        except ClientAuthenticationError as e:
            raise AzureCredentialsError("Azure credentials not found or invalid") from e
        except HttpResponseError as e:
            status_code = e.status_code if hasattr(e, "status_code") else None
            if status_code == 429:
                raise AzureThrottlingError("Azure API request throttled") from e
            if status_code in (401, 403):
                raise AzurePermissionsError("Insufficient Azure permissions") from e
            if status_code == 400:
                raise AzureInvalidSubscriptionError(f"Invalid Azure request: {e}") from e
            raise AzureServiceError(f"Azure Cost Management error: {e}") from e
        except ServiceRequestError as e:
            raise AzureServiceError(f"Azure service request failed: {e}") from e
        except AzureError as e:
            raise AzureServiceError(f"Unexpected Azure error: {e}") from e

        return self._normalize_response(result, start_date, end_date, granularity)

    def _normalize_response(
        self,
        result: Any,
        start_date: date,
        end_date: date,
        granularity: str,
    ) -> dict[str, Any]:
        rows = []
        if result and getattr(result, "properties", None):
            rows = getattr(result.properties, "rows", []) or []

        services: dict[str, float] = {}
        total_cost = 0.0
        currency = "USD"

        # Columns metadata: find ServiceName and Cost indices
        columns = []
        if result and getattr(result.properties, "columns", None):
            columns = result.properties.columns

        service_idx: int | None = None
        cost_idx: int | None = None
        currency_idx: int | None = None
        for i, col in enumerate(columns):
            name = getattr(col, "name", "").lower()
            if name == "servicename":
                service_idx = i
            elif name == "cost":
                cost_idx = i
            elif name == "currency":
                currency_idx = i

        for row in rows:
            service_name = row[service_idx] if service_idx is not None and service_idx < len(row) else "Unknown"
            cost = float(row[cost_idx]) if cost_idx is not None and cost_idx < len(row) else 0.0
            if currency_idx is not None and currency_idx < len(row):
                currency = str(row[currency_idx])
            if cost > 0:
                services[str(service_name)] = services.get(str(service_name), 0.0) + cost
                total_cost += cost

        sorted_services = sorted(services.items(), key=lambda x: x[1], reverse=True)

        return {
            "provider": "azure",
            "currency": currency,
            "total_cost": round(total_cost, 2),
            "date_range": {
                "start": start_date.isoformat(),
                "end": end_date.isoformat(),
                "granularity": granularity,
            },
            "services": [
                {"service_name": name, "cost": round(cost, 2)}
                for name, cost in sorted_services
            ],
        }
```

- [ ] **Step 2: Write service tests**

Create `tests/test_azure_service.py` using mocks for Azure SDK clients. Test:

- Disabled flag returns empty response.
- Invalid granularity raises `AzureInvalidSubscriptionError`.
- Configured subscription ID is used without calling `SubscriptionClient`.
- Default subscription is discovered when ID is not configured.
- Credential error raises `AzureCredentialsError`.
- Permission error raises `AzurePermissionsError`.
- Throttling raises `AzureThrottlingError`.
- Successful query returns normalized dict.

- [ ] **Step 3: Run service tests**

```bash
.venv/bin/pytest tests/test_azure_service.py -q
```

Expected: all tests pass.

---

## Task 4: Create Azure mapper

**Files:**
- Create: `app/providers/azure/mapper.py`
- Test: `tests/test_providers_azure.py` (mapper section)

- [ ] **Step 1: Implement the mapper**

Create `app/providers/azure/mapper.py`:

```python
"""Mapper from raw Azure Cost Management responses to provider-agnostic schemas."""

from __future__ import annotations

from datetime import date
from typing import Any

from app.providers.schemas import CostResponse, ServiceCost


class AzureMapper:
    """Translate Azure-specific dicts into :class:`CostResponse`."""

    def map(
        self,
        raw: dict[str, Any],
        start_date: date,
        end_date: date,
        granularity: str,
    ) -> CostResponse:
        date_range = raw.get("date_range")
        if not isinstance(date_range, dict) or not date_range:
            date_range = {
                "start": start_date.isoformat(),
                "end": end_date.isoformat(),
                "granularity": granularity,
            }

        services_raw = raw.get("services") or []
        services = [
            ServiceCost(
                service_name=str(item["service_name"]),
                cost=float(item["cost"]),
            )
            for item in services_raw
        ]

        return CostResponse(
            provider=str(raw.get("provider", "azure")),
            currency=str(raw.get("currency", "USD")),
            total_cost=float(raw.get("total_cost", 0.0)),
            date_range={
                "start": str(date_range.get("start", start_date.isoformat())),
                "end": str(date_range.get("end", end_date.isoformat())),
                "granularity": str(date_range.get("granularity", granularity)),
            },
            services=services,
        )
```

- [ ] **Step 2: Write mapper tests**

In `tests/test_providers_azure.py`, add:

```python
class TestAzureMapper:
    def test_maps_raw_response_to_cost_response(self) -> None:
        raw = {
            "provider": "azure",
            "currency": "USD",
            "total_cost": 123.45,
            "services": [
                {"service_name": "Storage", "cost": 100.0},
                {"service_name": "Compute", "cost": 23.45},
            ],
        }
        mapper = AzureMapper()
        response = mapper.map(raw, date(2024, 1, 1), date(2024, 1, 31), "DAILY")
        assert response.provider == "azure"
        assert response.total_cost == 123.45
        assert len(response.services) == 2
        assert response.services[0].service_name == "Storage"

    def test_defensive_defaults_for_missing_keys(self) -> None:
        mapper = AzureMapper()
        response = mapper.map({}, date(2024, 1, 1), date(2024, 1, 31), "MONTHLY")
        assert response.provider == "azure"
        assert response.total_cost == 0.0
        assert response.services == []
        assert response.date_range["granularity"] == "MONTHLY"
```

---

## Task 5: Create Azure provider and register it

**Files:**
- Create: `app/providers/azure/__init__.py`
- Create: `app/providers/azure/provider.py`
- Modify: `app/providers/__init__.py`
- Test: `tests/test_providers_azure.py`

- [ ] **Step 1: Implement AzureCloudProvider**

Create `app/providers/azure/provider.py`. Follow the same exception translation pattern as AWS:

```python
"""Azure implementation of the :class:`CloudProvider` abstraction."""

from __future__ import annotations

from datetime import date

from azure.core.exceptions import AzureError, ClientAuthenticationError, HttpResponseError, ServiceRequestError

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
        return "azure"

    def authenticate(self) -> None:
        self._service._ensure_credential()
        return None

    def validate_credentials(self) -> bool:
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
        except AzureError as e:
            raise ProviderServiceError(f"Azure service error: {e}") from e

        return self._mapper.map(
            raw,
            start_date=start_date,
            end_date=end_date,
            granularity=granularity,
        )
```

- [ ] **Step 2: Register Azure provider**

Create `app/providers/azure/__init__.py`:

```python
"""Azure provider package."""

from __future__ import annotations

from app.providers.azure.mapper import AzureMapper
from app.providers.azure.provider import AzureCloudProvider
from app.providers.registry import register_provider

__all__ = ["AzureCloudProvider", "AzureMapper"]

register_provider("azure", lambda: AzureCloudProvider())
```

Modify `app/providers/__init__.py` to import azure at load time. Add after the existing aws import:

```python
# Load provider registrations so get_provider("...") works at import time.
from app.providers import aws, azure  # noqa: F401,E501
```

- [ ] **Step 3: Write provider tests**

In `tests/test_providers_azure.py`, test:

- `provider_name()` returns `"azure"`.
- `validate_credentials()` returns True/False.
- `get_costs()` returns `CostResponse`.
- Exception translations for all five provider-agnostic types.

- [ ] **Step 4: Run provider tests**

```bash
.venv/bin/pytest tests/test_providers_azure.py -q
```

Expected: all tests pass.

---

## Task 6: Create Azure request schema

**Files:**
- Create: `app/schemas/azure.py`
- Test: `tests/test_azure_schemas.py`

- [ ] **Step 1: Implement AzureCostRequest**

Create `app/schemas/azure.py` mirroring `app/schemas/aws.py`:

```python
"""Pydantic v2 schemas for Azure Cost Management API."""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class AzureCostRequest(BaseModel):
    """Request for Azure cost retrieval."""

    model_config = ConfigDict(extra="forbid")

    start_date: date = Field(...)
    end_date: date = Field(...)
    granularity: Literal["DAILY", "MONTHLY"] = Field(default="DAILY")

    @field_validator("end_date")
    @classmethod
    def end_after_start(cls, v: date, info) -> date:
        if info.data.get("start_date") and v < info.data["start_date"]:
            raise ValueError("end_date must be on or after start_date")
        return v
```

- [ ] **Step 2: Write schema tests**

Create `tests/test_azure_schemas.py` mirroring `tests/test_aws_schemas.py`.

---

## Task 7: Create Azure API route and mount it

**Files:**
- Create: `app/api/routes/azure.py`
- Modify: `app/api/router.py`
- Test: `tests/test_azure_endpoint.py`

- [ ] **Step 1: Implement the route**

Create `app/api/routes/azure.py` mirroring `app/api/routes/aws.py`:

- Router prefix `/azure`, tags `["azure"]`.
- `GET /costs` with `AzureCostRequest` query model.
- Dependency injection via `get_provider("azure")`.
- Return `CostResponse`.
- Catch provider-agnostic exceptions and map to HTTP status codes.

- [ ] **Step 2: Mount the router**

Modify `app/api/router.py`:

```python
from app.api.routes.azure import router as azure_router

api_router.include_router(azure_router)
```

- [ ] **Step 3: Write endpoint tests**

Create `tests/test_azure_endpoint.py` mirroring `tests/test_aws_endpoint.py`:

- Success case with mocked provider.
- Unauthorized case.
- Invalid granularity.
- Bad dates.
- Credentials error → 500.
- Throttling → 429.
- Permissions → 403.
- Service error → 502.

- [ ] **Step 4: Run endpoint tests**

```bash
.venv/bin/pytest tests/test_azure_endpoint.py -q
```

Expected: all tests pass.

---

## Task 8: Update registry test to include Azure

**Files:**
- Modify: `tests/test_providers_registry.py`

- [ ] **Step 1: Add Azure registration assertion**

In `tests/test_providers_registry.py`, add a test:

```python
class TestProviderRegistry:
    ...

    def test_azure_provider_is_registered(self) -> None:
        factory = get_provider_factory("azure")
        provider = factory()
        assert isinstance(provider, AzureCloudProvider)
        assert provider.provider_name() == "azure"
```

Import `AzureCloudProvider` from `app.providers.azure`.

---

## Task 9: Update architecture documentation

**Files:**
- Modify: `docs/architecture.md`

- [ ] **Step 1: Update Cloud Provider Abstraction section**

- List Azure as an implemented provider alongside AWS.
- Add a subsection on Azure authentication (`DefaultAzureCredential`, Managed Identity, Azure CLI, env SP).
- Document subscription ID resolution (configured → discovered default).
- Update extension guide: GCP remains the future example.

---

## Task 10: Final verification

- [ ] **Step 1: Run full test suite**

```bash
.venv/bin/pytest -q
```

Expected: all tests pass (existing AWS tests + new Azure tests).

- [ ] **Step 2: Run lint**

```bash
.venv/bin/ruff check .
```

Expected: clean.

- [ ] **Step 3: Run format check**

```bash
.venv/bin/black --check .
```

Expected: clean.

- [ ] **Step 4: Verify registry exposes both providers**

```bash
.venv/bin/python -c "from app.providers.registry import get_provider_factory; print(get_provider_factory('aws')()); print(get_provider_factory('azure')())"
```

Expected: prints AWS and Azure provider instances.

---

## Handoff

After Task 10 passes, the feature is ready for final review and PR creation. Use `superpowers:requesting-code-review` or the finishing-a-development-branch workflow.
