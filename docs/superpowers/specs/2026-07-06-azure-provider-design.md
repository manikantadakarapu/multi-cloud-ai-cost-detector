# Azure Cost Management Provider — Design Spec

**Date:** 2026-07-06  
**Sprint:** 0.6  
**Status:** Approved

## Goal

Implement a production-quality Azure cost provider that plugs into the existing `CloudProvider` abstraction introduced in Sprint 0.5. The provider must expose the same interface, return the same normalized `CostResponse`, and mirror the AWS public API behaviour.

## Context

Sprint 0.5 delivered:

- `CloudProvider` abstract base class (`app/providers/base.py`)
- Provider-agnostic schemas (`CostResponse`, `ServiceCost`) in `app/providers/schemas.py`
- Provider-agnostic exceptions in `app/providers/exceptions.py`
- Manual provider registry in `app/providers/registry.py`
- AWS implementation in `app/providers/aws/`
- AWS route at `GET /api/v1/aws/costs`

The abstraction is stable. This sprint adds Azure as the second provider without redesigning any shared component.

## Design Decisions

### 1. Mirror the AWS structure

Create an internal Azure SDK service layer plus a provider wrapper, matching the AWS pattern:

```
app/
  providers/azure/
    __init__.py
    provider.py
    mapper.py
  services/azure/
    cost_management.py
    exceptions.py
  schemas/azure.py
  api/routes/azure.py
```

**Rationale:** Keeps the codebase predictable, testable, and consistent with the existing AWS implementation.

### 2. Subscription ID handling (Option C)

- If `AZURE_SUBSCRIPTION_ID` is configured, use it.
- If not configured, discover the default subscription at runtime using `azure.mgmt.subscription.SubscriptionClient`.
- If neither is available, raise `ProviderCredentialsError`.

**Rationale:** Supports explicit production configuration while remaining convenient for local development.

### 3. Authentication

Use `azure.identity.DefaultAzureCredential` by default. It supports:

- Managed Identity
- Azure CLI login
- Environment credentials (`AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_CLIENT_SECRET`)
- Visual Studio Code / Azure PowerShell (where available)

No interactive authentication. Optional service-principal settings in `Settings` can constrain `DefaultAzureCredential` when provided.

### 4. Cost Management Query API

Use `azure.mgmt.costmanagement.CostManagementClient` with the `query.usage` API call.

Query scope: `/subscriptions/{subscription_id}`.

Query parameters:

- `type`: `"Usage"`
- `timeframe`: `"Custom"`
- `time_period.from` and `time_period.to`: ISO date strings
- `dataset.granularity`: `"Daily"` or `"Monthly"`
- `dataset.aggregation`: `{"totalCost": {"name": "Cost", "function": "Sum"}}`
- `dataset.grouping`: `[{"type": "Dimension", "name": "ServiceName"}]`

### 5. Error mapping

Azure SDK and service exceptions are translated to the existing provider-agnostic hierarchy:

| Azure failure | Provider exception |
|---|---|
| `ClientAuthenticationError` / credential unavailable | `ProviderCredentialsError` |
| `HttpResponseError` 401/403 / authorization failed | `ProviderPermissionsError` |
| `HttpResponseError` 400 / invalid subscription | `ProviderInvalidDateRangeError` or `ProviderServiceError` |
| `HttpResponseError` 429 | `ProviderThrottlingError` |
| Other `HttpResponseError` / AzureError | `ProviderServiceError` |
| Timeout / `ServiceRequestError` | `ProviderServiceError` |

## Dependencies

Add to `pyproject.toml` under `[project] dependencies`:

```toml
"azure-identity>=1.16.0,<2.0.0",
"azure-mgmt-costmanagement>=4.0.0,<5.0.0",
"azure-mgmt-subscription>=3.1.1,<4.0.0",
```

Run `pip install -e ".[dev]"` or equivalent after updating.

## Configuration

Add to `app/core/config.py`:

```python
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

## File Changes

### New files

- `app/providers/azure/__init__.py` — exports `AzureCloudProvider`, `AzureMapper`, registers `"azure"` factory.
- `app/providers/azure/provider.py` — `AzureCloudProvider` implementing `CloudProvider`.
- `app/providers/azure/mapper.py` — `AzureMapper` converting raw Azure response dict to `CostResponse`.
- `app/services/azure/cost_management.py` — `AzureCostManagementService` wrapping the Azure SDK.
- `app/services/azure/exceptions.py` — Azure-specific exception hierarchy.
- `app/services/azure/__init__.py` — package init.
- `app/schemas/azure.py` — `AzureCostRequest` Pydantic model (mirrors `AWSCostRequest`).
- `app/api/routes/azure.py` — Azure cost endpoint.
- `tests/test_providers_azure.py` — provider and mapper unit tests.
- `tests/test_azure_endpoint.py` — endpoint tests with mocked provider.
- `tests/test_azure_service.py` — service layer tests (optional but recommended).

### Modified files

- `pyproject.toml` — add Azure SDK dependencies.
- `app/core/config.py` — add Azure settings.
- `app/providers/__init__.py` — import `app.providers.azure` at load time to register factory.
- `app/api/router.py` — include Azure router.
- `docs/architecture.md` — document Azure provider, auth flow, registration, and supported credentials.

## Authentication Flow

1. `AzureCloudProvider` is instantiated per request via `get_provider("azure")`.
2. `AzureCostManagementService` is created with `app_settings`.
3. On first SDK call, `_ensure_client()` builds a `DefaultAzureCredential` (optionally constrained by tenant/client IDs) and a `CostManagementClient`.
4. If `azure_subscription_id` is absent, `_resolve_subscription_id()` queries the default subscription.
5. Any credential failure raises `ProviderCredentialsError`.

## Cost Retrieval Flow

1. Route receives authenticated `GET /api/v1/azure/costs` with `start_date`, `end_date`, `granularity`.
2. Route injects `CloudProvider` via `Depends(get_provider("azure"))`.
3. Route calls `await provider.get_costs(...)`.
4. Provider delegates to `AzureCostManagementService.get_costs(...)`.
5. Service builds the query, calls Azure Cost Management Query API, and returns a raw dict.
6. Provider maps Azure exceptions to provider-agnostic exceptions.
7. `AzureMapper` converts the raw dict into `CostResponse(provider="azure", ...)`.
8. Route returns `CostResponse` and maps provider-agnostic exceptions to HTTP status codes (same as AWS).

## API Route

```python
@router.get(
    "/costs",
    response_model=CostResponse,
    summary="Retrieve Azure costs",
    description="Retrieve normalized Azure cost data grouped by service.",
)
async def get_azure_costs(
    request: Annotated[AzureCostRequest, Query()],
    current_user: Annotated[User, Depends(get_current_active_user)],
    provider: Annotated[CloudProvider, Depends(get_provider("azure"))],
) -> CostResponse:
    ...
```

HTTP status codes mirror AWS:

- 200 OK
- 400 Bad Request
- 401 Unauthorized
- 403 Forbidden
- 422 Validation Error
- 429 Too Many Requests
- 500 Credentials Error
- 502 Service Error

## Tests

### Unit tests

- `AzureMapper` correctly converts raw Azure response dict to `CostResponse`.
- `AzureCloudProvider` implements `CloudProvider` interface.
- Exception translation covers credential, permission, throttling, and service errors.

### Service tests

- Subscription resolution prefers configured ID over discovered default.
- `DefaultAzureCredential` is built correctly from settings.
- Cost query payload matches Azure Cost Management Query API expectations.

### Endpoint tests

- Authenticated request returns normalized cost response.
- Unauthenticated request returns 401.
- Invalid granularity returns 422.
- Provider exceptions map to correct HTTP status codes.

### Regression

- All existing AWS tests continue to pass.
- Registry tests confirm both `aws` and `azure` are registered.

## Documentation

Update `docs/architecture.md` Cloud Provider Abstraction section to:

- List Azure as an implemented provider alongside AWS.
- Document Azure authentication options (DefaultAzureCredential, Managed Identity, CLI, env SP).
- Document subscription ID resolution behavior.
- Update the extension guide: GCP remains the future example.

## Constraints

- Do not modify `CloudProvider`, registry, or normalized schemas.
- Do not modify AWS implementation unless fixing a genuine bug.
- Do not introduce Azure-specific response models outside the mapper.
- Keep changes isolated to Azure implementation.
