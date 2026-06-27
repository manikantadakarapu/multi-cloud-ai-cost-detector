# Changelog

All notable changes to the **Multi-Cloud AI Cost Detective** project are
documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

_No changes yet._

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

[Unreleased]: https://github.com/manikantadakarapu/multi-cloud-ai-cost-detective/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/manikantadakarapu/multi-cloud-ai-cost-detective/releases/tag/v0.1.0
