# Changelog

All notable changes to the **Multi-Cloud AI Cost Detective** project are
documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

_No changes yet._

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

[Unreleased]: https://github.com/manikantadakarapu/multi-cloud-ai-cost-detective/compare/v0.3.0...HEAD
[0.3.0]: https://github.com/manikantadakarapu/multi-cloud-ai-cost-detective/releases/tag/v0.3.0
[0.1.0]: https://github.com/manikantadakarapu/multi-cloud-ai-cost-detective/releases/tag/v0.1.0
