# Changelog

All notable changes to the **Multi-Cloud AI Cost Detective** project are
documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

### Added

- Sprint 0.6 Azure Cost Management integration:
  - Azure Cost Management Query API integration
    (`app/services/azure/cost_management.py`) using `azure-identity` and
    `azure-mgmt-costmanagement` with `DefaultAzureCredential` and optional
    `ClientSecretCredential`, subscription scope, and date-range validation.
  - `GET /api/v1/azure/costs` endpoint (`app/api/routes/azure.py`) mounted
    under the v1 API router and protected by the existing
    `get_current_active_user` JWT dependency.
  - Normalised `CostResponse` output (`app/schemas/azure.py`) matching the
    AWS cost-response shape, with provider, currency, total cost,
    date range, and service-level breakdown.
  - Azure-specific exception hierarchy (`app/services/azure/exceptions.py`):
    `AzureCostManagementError` (base) and `AzureCredentialsError`,
    `AzureThrottlingError`, `AzurePermissionsError`,
    `AzureInvalidSubscriptionError`, and `AzureServiceError`, each carrying
    a stable `error_code`.
  - Provider-level tests, registry tests, mapper tests, and route error
    tests for Azure Cost Management.
  - Documentation updates in `README.md` and `.env.example` covering Azure
    authentication, required environment variables, the new endpoint, and
    example requests and responses.

---

## [0.4.1] - 2026-07-05

### Added

- GitHub Actions CI/CD workflows:
  - `.github/workflows/backend-ci.yml` — Python 3.12 setup, dependency caching,
    `ruff check`, `black --check`, `pytest` with coverage reporting.
  - `.github/workflows/security.yml` — `bandit` static analysis and
    `pip-audit` vulnerability scanning on every push/PR and weekly.
  - `.github/workflows/codeql.yml` — GitHub CodeQL analysis for Python on
    push/PR and weekly schedule.
  - `.github/workflows/release.yml` — automated GitHub Release creation
    triggered by `v*.*.*` tags with auto-generated release notes.
- `.github/dependabot.yml` — weekly Dependabot updates for `pip` and
  `github-actions` ecosystems.
- `.pre-commit-config.yaml` — hooks for trailing whitespace, end-of-file
  fixer, YAML validation, `ruff` check/format, and `black`.
- `.editorconfig` — editor defaults for Python and YAML files.
- README badges for Backend CI, CodeQL, and coverage placeholder.
- README "Development Workflow" section documenting tests, linting,
  formatting, security scanning, pre-commit hooks, and the release process.

### Changed

- `pyproject.toml` dev dependencies expanded to include `black`, `bandit[toml]`,
  `pip-audit`, `pre-commit`, and `pytest-cov`.
- Bumped `black` to `>=26.3.1,<27.0.0` and `pytest` to `>=9.0.3,<10.0.0`
  to resolve known vulnerabilities.
- Widened `pytest-asyncio` upper bound to `<2.0.0` for `pytest` 9.x
  compatibility.

### Fixed

- Applied `black` formatting across the codebase.
- Suppressed `bandit` B106 false positives for JWT `token_type` string
  literals (`access`, `refresh`, `bearer`) in `app/auth/jwt.py`,
  `app/auth/router.py`, and `app/auth/service.py`.

### Security

- Added automated `bandit` and `pip-audit` scans in CI.

---

## [0.4.0] - 2026-07-05

### Added

- AWS Cost Explorer settings in `app/core/config.py`:
  `aws_default_region` (default `us-east-1`), `aws_profile`,
  `aws_access_key_id`, `aws_secret_access_key`, and
  `aws_cost_explorer_enabled` (default `true`), all bound via
  `validation_alias` to `AWS_DEFAULT_REGION`, `AWS_PROFILE`,
  `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, and
  `AWS_COST_EXPLORER_ENABLED`. Documented in `.env.example`.
- AWS Cost Explorer service (`app/services/aws/cost_explorer.py`) wrapping
  `boto3` Cost Explorer `GetCostAndUsage` with paginated retrieval,
  service-grouped normalisation, daily and monthly granularity, and
  structured logging. The service short-circuits to an empty result when
  `aws_cost_explorer_enabled` is `false` and surfaces typed exceptions for
  missing credentials, throttling, missing permissions, invalid date
  ranges, and upstream service errors.
- AWS-specific exception hierarchy in `app/services/aws/exceptions.py`:
  `AWSCostExplorerError` (base) and `AWSCredentialsError`,
  `AWSThrottlingError`, `AWSPermissionsError`,
  `AWSInvalidDateRangeError`, and `AWSServiceError`, each carrying a
  stable `error_code`.
- Pydantic v2 schemas for AWS in `app/schemas/aws.py`:
  `AWSCostRequest` (start_date, end_date, granularity with
  `Literal["DAILY", "MONTHLY"]` and an end-after-start validator),
  `AWSServiceCost` (service_name, cost), and `AWSCostResponse`
  (provider, currency, total_cost, date_range, services).
- AWS Cost Explorer endpoint `GET /api/v1/aws/costs`
  (`app/api/routes/aws.py`) mounted under the v1 API router and
  protected by the existing `get_current_active_user` JWT dependency.
  Maps AWS exceptions to `400 / 403 / 429 / 500 / 502` responses with the
  error code returned in the `X-Error-Code` header.
- Test coverage for the AWS Cost Explorer integration:
  - `tests/test_aws_exceptions.py` — exception hierarchy and error codes.
  - `tests/test_cost_explorer.py` — service-level success, credential,
    throttling, permission, invalid date range, and disabled-flag paths
    against a mocked boto3 client.
  - `tests/test_aws_schemas.py` — request and response schema validation.
  - `tests/test_aws_endpoint.py` — endpoint auth, success, validation,
    and AWS-error mapping using the `auth_client` fixture.
  - `tests/test_aws_integration.py` — full-flow integration tests for
    daily and monthly granularity, empty responses, and the disabled-flag
    short-circuit, with `CostExplorerService.get_costs` patched via
    `AsyncMock`.
- README documentation for AWS Cost Explorer: roadmap Sprint 0.4 row
  updated to reflect AWS completion, an `AWS Cost Explorer` section
  added with authentication chain, required IAM permissions JSON, the
  AWS environment variable table, the `GET /api/v1/aws/costs` endpoint
  reference, an example `curl` request, an example JSON response, and
  the error-response table.

### Changed

- _Nothing._

### Deprecated

- _Nothing._

### Removed

- _Nothing._

### Fixed

- _Nothing._

### Security

- AWS credentials are never persisted by the application; they are
  resolved at request time through the standard AWS credential chain
  (env vars, profile, IAM role). No credentials are written to logs;
  the structured logger only records the resolved region and request
  metadata.

---

## [0.3.0] - 2026-07-04

### Added

- `users` table with UUID primary key, unique `email`, `full_name`,
  `password_hash`, `is_active`, and timestamp columns (`app/auth/models.py`).
- Alembic migration `20260629_0000_create_users_and_revoked_tokens` adding
  the `users` table (with the unique index on `email`) and the
  `revoked_tokens` table for future refresh-token invalidation.
- Authentication router mounted under `/api/v1/auth` (`app/auth/router.py`)
  exposing:
  - `POST /api/v1/auth/register` — create a new user, returns the user
    profile and an initial access + refresh token pair.
  - `POST /api/v1/auth/login` — exchange email + password for tokens.
  - `POST /api/v1/auth/refresh` — exchange a refresh token for a new
    access token.
  - `POST /api/v1/auth/logout` — stateless logout.
  - `GET  /api/v1/auth/me` — return the authenticated user's profile.
- `AuthService` (`app/auth/service.py`) and `AuthRepository`
  (`app/auth/repository.py`) implementing registration, password
  verification, JWT issuance, and refresh-token decoding. Registration
  catches unique-constraint violations and converts them into
  `EMAIL_ALREADY_REGISTERED` to prevent HTTP 500s under concurrent
  registrations.
- JWT helpers (`app/auth/jwt.py`) for creating and decoding HS256 access
  and refresh tokens, including `jti` claims for future revocation
  tracking.
- Password hashing using `passlib[bcrypt]` (`app/auth/security.py`) with
  the bcrypt 72-byte input limit handled by pre-truncation.
- Pydantic request/response schemas for auth (`app/auth/schemas.py`):
  `UserRegisterRequest`, `UserLoginRequest`, `TokenRefreshRequest`,
  `LogoutRequest`, `UserResponse`, `UserRegisterResponse`,
  `TokenResponse`, `MessageResponse`, and `ErrorResponse`.
- FastAPI dependencies (`app/auth/dependencies.py`) implementing
  `get_current_user` and `get_current_active_user` based on
  `HTTPBearer`. The authenticated user is returned directly; handlers
  depend on this function rather than reading from `request.state`.
- JWT-related settings in `app/core/config.py`: `JWT_SECRET_KEY`,
  `JWT_ALGORITHM`, `ACCESS_TOKEN_EXPIRE_MINUTES`,
  `REFRESH_TOKEN_EXPIRE_DAYS`, `AUTH_RATE_LIMIT_PER_MINUTE`, and
  `AUTH_MAX_LOGIN_ATTEMPTS`. Documented in `.env.example`.
- Auth test coverage (`tests/test_auth.py`) covering registration
  success and validation, duplicate-email handling, login success and
  invalid credentials, inactive account rejection, refresh and logout
  flows, `/auth/me` with and without a token, and JWT decoding
  edge cases.
- Status line in `README.md` updated to reflect Sprint 0.3 local JWT
  auth completion, with the new auth endpoints added to the API table
  and the new environment variables documented.

### Changed

- _Nothing._

### Deprecated

- _Nothing._

### Removed

- _Nothing._

### Fixed

- _Nothing._

### Security

- Passwords are stored only as bcrypt hashes (no plaintext or reversible
  encoding). The `users.password_hash` column is sized to accommodate the
  full bcrypt output.
- All auth handlers return generic 401 messages for invalid credentials
  to prevent email enumeration.
- `.env.example` ships a placeholder `JWT_SECRET_KEY`; production
  deployments must override it via the environment with a long random
  value (`python -c "import secrets; print(secrets.token_urlsafe(48))"`).

---

## [0.1.0] - 2026-06-27

### Added

- FastAPI application factory with lifespan management (`app.main:create_app`).
- Service root endpoint (`GET /`) returning name, version, status, docs, and
  health links.
- Production health endpoint (`GET /api/v1/health`) with a live database
  round-trip probe (`SELECT 1`) that returns HTTP 503 when the database is
  unreachable.
- `HealthService` in `app/services/health.py` isolating the database
  connectivity check from the HTTP layer.
- Async SQLAlchemy 2.x engine and session factory (`app/database/session.py`)
  with connection-pool tuning (`pool_pre_ping`, size, overflow, timeout,
  recycle).
- Declarative base with naming conventions (`app/database/base.py`).
- Alembic migration setup with autogenerate support (`alembic/env.py`).
- Centralised configuration via Pydantic Settings (`app/core/config.py`)
  with `.env` file loading and a `database_url_source` field that reports
  whether the active value came from the process environment, the `.env`
  file, or the default.
- Structured JSON logging (`app/core/logging.py`) with a custom
  `JsonFormatter` and configurable log level.
- OpenAPI / Swagger metadata module (`app/core/openapi.py`) providing title,
  description, contact, MIT licence info, and tags.
- `scripts/check_db.py` standalone database connectivity diagnostic.
- Docker Compose configuration for a local PostgreSQL 16 instance
  (`docker-compose.yml`).
- Pydantic v2 response models for the root and health endpoints
  (`app/schemas/root.py`, `app/schemas/health.py`).
- Test scaffold with `pytest`, `pytest-asyncio`, and an httpx ASGI client
  fixture (`tests/conftest.py`, `tests/test_api.py`).

### Changed

- _Initial release — no prior version to compare against._

### Deprecated

- _Nothing._

### Removed

- _Nothing._

### Fixed

- _Nothing._

### Security

- `.gitignore` excludes `.env` and all `.env.*` variants (except
  `.env.example`) to prevent secret leakage.
- `pg_hba.conf`-related connection failures documented alongside the
  diagnostic script so contributors do not paste credentials into source
  control during debugging.

[Unreleased]: https://github.com/manikantadakarapu/multi-cloud-ai-cost-detective/compare/v0.4.1...HEAD
[0.4.1]: https://github.com/manikantadakarapu/multi-cloud-ai-cost-detective/releases/tag/v0.4.1
[0.4.0]: https://github.com/manikantadakarapu/multi-cloud-ai-cost-detective/releases/tag/v0.4.0
[0.3.0]: https://github.com/manikantadakarapu/multi-cloud-ai-cost-detective/releases/tag/v0.3.0
[0.1.0]: https://github.com/manikantadakarapu/multi-cloud-ai-cost-detective/releases/tag/v0.1.0
