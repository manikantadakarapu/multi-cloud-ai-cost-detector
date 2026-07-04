# Multi-Cloud AI Cost Detector

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.12%2B-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.111%2B-009688.svg)](https://fastapi.tiangolo.com/)
[![Code Style: Ruff](https://img.shields.io/badge/code%20style-ruff-261230.svg)](https://docs.astral.sh/ruff/)

A FastAPI backend platform for detecting cost anomalies across AWS, Azure, and
Google Cloud Platform, with AI-powered recommendations to reduce cloud spend.

The platform ingests billing and usage data from multiple cloud providers,
normalises it into a unified schema, and applies anomaly detection to surface
unexpected cost spikes, idle resources, and optimisation opportunities. Long
term it will expose AI-driven recommendations that engineering and platform
teams can act on directly.

> **Status:** Sprint 0.2 — Engineering documentation & architecture complete. Backend
> foundation (Sprint 0.1) done. Authentication (Sprint 0.3) and cloud integrations
> (Sprint 0.4) planned.

## Table of Contents

- [Architecture](#architecture)
- [Tech Stack](#tech-stack)
- [Features Completed](#features-completed)
- [Roadmap](#roadmap)
- [Getting Started](#getting-started)
- [Environment Variables](#environment-variables)
- [Development Commands](#development-commands)
- [Contributing](#contributing)
- [License](#license)
- [Future Improvements](#future-improvements)

---

## Architecture

```text
MCAICD/
├── alembic/               # Database migration scripts and config
│   └── versions/
├── app/
│   ├── api/               # Routers, dependencies, and route modules
│   │   ├── deps.py
│   │   ├── router.py
│   │   └── routes/
│   ├── core/              # Configuration, logging, OpenAPI metadata
│   ├── database/          # Async engine, session factory, declarative base
│   ├── models/            # SQLAlchemy ORM models
│   ├── schemas/          # Pydantic request/response schemas
│   ├── services/         # Business logic (health checks, future services)
│   └── main.py           # FastAPI application factory
├── scripts/
│   └── check_db.py       # Database connectivity diagnostic
├── tests/                # Test suite
├── .env.example
├── alembic.ini
├── docker-compose.yml
├── pyproject.toml
└── requirements.txt
```

---

## Tech Stack

| Layer              | Technology                                   |
| ------------------ | -------------------------------------------- |
| Language           | Python 3.12+                                 |
| Web framework      | FastAPI                                      |
| ORM                | SQLAlchemy 2.x (async)                        |
| Database           | PostgreSQL 16                                 |
| Migrations         | Alembic                                       |
| Settings           | Pydantic v2 + pydantic-settings               |
| ASGI server        | Uvicorn                                       |
| Linting / format   | Ruff                                          |
| Testing            | pytest, pytest-asyncio, httpx                 |
| Containerisation   | Docker, Docker Compose                        |
| CI (future)        | GitHub Actions                                |
| Infrastructure     | Terraform *(future)*                          |
| Caching            | Redis *(future)*                              |

---

## Features Completed

- ✅ FastAPI application factory with lifespan management
- ✅ Async SQLAlchemy 2.x engine and session factory
- ✅ PostgreSQL integration via asyncpg
- ✅ Alembic migration setup with autogenerate
- ✅ Structured JSON logging
- ✅ Centralised environment configuration (Pydantic Settings)
- ✅ Production health endpoint with database probe
- ✅ Service root endpoint for discovery
- ✅ Rich OpenAPI / Swagger documentation
- ✅ Docker Compose for local PostgreSQL

---

## Roadmap

| Sprint | Status | Description |
| ------ | ------ | ----------- |
| 0.1 | ✅ Complete | Backend foundation — FastAPI app factory, async SQLAlchemy 2.x, PostgreSQL, Alembic, structured logging, health endpoint. |
| 0.2 | ✅ Complete | Engineering documentation & architecture — ADRs, architecture doc, development workflow, roadmap. |
| 0.3 | ⏳ Planned | Authentication — JWT bearer auth, Azure AD (OIDC), Google Login (OAuth 2.0), role-based access control. |
| 0.4 | ⏳ Planned | Cloud integrations — Azure Cost Management, AWS Cost Explorer, GCP Billing export, unified normalised schema. |
| 0.5 | ⏳ Planned | AI analysis engine — anomaly detection, idle resource detection, recommendation generation. |
| 0.6 | ⏳ Planned | REST APIs — cost query, anomaly, recommendation, and reporting endpoints with pagination and filtering. |
| 0.7 | ⏳ Planned | Frontend dashboard — React/Next.js, cost breakdowns, anomaly feed, recommendation inbox. |
| 0.8 | ⏳ Planned | Real-time monitoring — WebSocket anomaly push, alerting rules, notification channels. |
| 0.9 | ⏳ Planned | Deployment — Dockerfile for the app, Kubernetes manifests, Helm chart, Terraform IaC. |
| 1.0 | 🔭 Future | Production release — hardening, load testing, security audit, GA.

---

## Getting Started

### Prerequisites

- **Python** 3.12 or newer
- **Docker Desktop** (for PostgreSQL)
- **Git**

### Clone

```bash
git clone git@github.com:manikantadakarapu/multi-cloud-ai-cost-detective.git
cd multi-cloud-ai-cost-detective
```

### Create a virtual environment

```bash
python -m venv .venv
source .venv/bin/activate        # Linux / macOS / WSL
# .\.venv\Scripts\Activate.ps1   # Windows PowerShell
```

### Install dependencies

```bash
pip install -e ".[dev]"
```

### Configure environment

```bash
cp .env.example .env
```

Edit `.env` and set `DATABASE_URL` to match your PostgreSQL credentials.

### Start PostgreSQL

```bash
docker compose up -d
```

### Run migrations

```bash
alembic upgrade head
```

### Start the backend

```bash
uvicorn app.main:app --reload
```

### Access the API

| URL                     | Purpose                         |
| ----------------------- | ------------------------------- |
| http://localhost:8000/  | Service root (discovery)        |
| http://localhost:8000/docs | Swagger UI (interactive docs) |
| http://localhost:8000/api/v1/health | Health check endpoint |

---

## Environment Variables

| Variable         | Description                                          | Default |
| ---------------- | ---------------------------------------------------- | ------- |
| `APP_NAME`       | Application display name                             | `Multi-Cloud AI Cost Detective` |
| `APP_ENV`        | Runtime environment (`local`, `development`, `staging`, `production`) | `local` |
| `APP_VERSION`    | Semantic version string                              | `0.1.0` |
| `APP_DEBUG`      | Enable FastAPI / SQLAlchemy debug mode               | `false` |
| `LOG_LEVEL`      | Logging level (`DEBUG`–`CRITICAL`)                   | `INFO` |
| `DATABASE_URL`   | PostgreSQL async connection string (`postgresql+asyncpg://...`) | — |
| `DB_POOL_SIZE`   | SQLAlchemy connection pool size                      | `10` |
| `DB_MAX_OVERFLOW`| Maximum overflow connections beyond pool size        | `20` |
| `DB_POOL_TIMEOUT`| Connection checkout timeout (seconds)                | `30` |
| `DB_POOL_RECYCLE`| Connection recycle interval (seconds)               | `1800` |
| `CORS_ORIGINS`   | Allowed CORS origins (JSON list)                     | `[]` |

> **Note:** `POSTGRES_USER`, `POSTGRES_PASSWORD`, and `POSTGRES_DB` are used by
> `docker-compose.yml` to initialise the PostgreSQL container. They are only
> honoured on the **first** container start — changing them later does not
> update existing database users.

---

## Development Commands

```bash
# Infrastructure
docker compose up -d            # Start PostgreSQL
docker compose down             # Stop PostgreSQL
docker compose down -v          # Stop and delete the data volume

# Database
alembic upgrade head            # Apply all migrations
alembic revision --autogenerate -m "description"  # Create a migration
alembic downgrade -1           # Roll back one migration
alembic current                # Show current revision

# Server
uvicorn app.main:app --reload   # Start dev server with hot reload

# Diagnostics
python scripts/check_db.py     # Verify database connectivity

# Code quality
ruff check .                    # Lint
ruff format .                   # Format

# Tests
pytest                          # Run all tests
pytest -v                        # Verbose output
```

---

## Contributing

Contributions are welcome! Please read [CONTRIBUTING.md](CONTRIBUTING.md) for
the full guide covering local setup, coding standards, branch naming, commit
messages, the pull request process, and code review expectations.

A quick summary of the branch naming convention:

### Branch naming

```
feature/<short-description>     # New features
bugfix/<short-description>       # Bug fixes
chore/<short-description>        # Maintenance / tooling
```

### Commit message style

Use [Conventional Commits](https://www.conventionalcommits.org/):

```
feat: add Azure cost ingestion endpoint
fix: correct timezone in health timestamp
docs: update environment variable table
chore: bump SQLAlchemy to 2.0.32
```

### Code formatting & linting

- The project uses **Ruff** for both linting and formatting.
- Line length is **100** characters.
- Run `ruff check .` and `ruff format .` before every commit.

### Testing

- Write tests for all new endpoints and services.
- Place tests under `tests/` mirroring the `app/` structure.
- Use `pytest-asyncio` for async tests.
- Ensure `pytest` passes before submitting a pull request.

---

## License

This project is intended to be released under the **MIT License**. A formal
`LICENSE` file will be added before the first public release.

---

## Project Documentation

This repository maintains production-quality engineering documentation under
`docs/`. The documentation is structured for a professional software
engineering organisation and reflects the current Sprint 0.2 progress.

| Document | Description |
| -------- | ----------- |
| [`docs/project-roadmap.md`](docs/project-roadmap.md) | Product and engineering roadmap with sprint plan, milestones, and long-term vision. |
| [`docs/architecture.md`](docs/architecture.md) | System architecture with Mermaid diagrams, component breakdown, and deployment view. |
| [`docs/development-workflow.md`](docs/development-workflow.md) | Engineering workflow: branching, commits, PR process, testing, linting, Docker, migrations, releases, and CI/CD philosophy. |
| [`docs/adr/ADR-0001-fastapi.md`](docs/adr/ADR-0001-fastapi.md) | Why FastAPI over Flask, Django, Express.js. |
| [`docs/adr/ADR-0002-postgresql.md`](docs/adr/ADR-0002-postgresql.md) | Why PostgreSQL over MongoDB, MySQL, SQLite. |
| [`docs/adr/ADR-0003-clean-architecture.md`](docs/adr/ADR-0003-clean-architecture.md) | Why clean architecture layering and the dependency rules that govern the codebase. |
| [`docs/adr/ADR-0004-docker-development.md`](docs/adr/ADR-0004-docker-development.md) | Why Docker-first development and the dev/prod container strategy. |
| [`docs/adr/ADR-0005-ai-provider-abstraction.md`](docs/adr/ADR-0005-ai-provider-abstraction.md) | Why an AI provider abstraction protocol to avoid vendor lock-in. |

---

## Future Improvements

- GitHub Actions CI pipeline with automated testing and linting
- Dockerfile for the application itself (Sprint 0.9)
- Kubernetes manifests and Helm chart (Sprint 0.9)
- Terraform infrastructure-as-code for AWS deployment (Sprint 0.9)
- Redis-backed caching layer for provider API responses
- Rate limiting and API key authentication (Sprint 0.3)
- Cost anomaly detection models and the AI recommendation engine (Sprint 0.5)
