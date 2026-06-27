# Multi-Cloud AI Cost Detective

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

> **Status:** Phase 1 — backend foundation complete. Cloud provider integrations
> and the AI recommendation engine are planned for later phases.

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

| Phase | Focus                                    | Status      |
| ----- | ---------------------------------------- | ----------- |
| 1     | Backend foundation                       | ✅ Complete  |
| 2     | Authentication & authorisation           | ⏳ Planned   |
| 3     | Azure cost ingestion & analysis         | ⏳ Planned   |
| 4     | AWS cost ingestion & analysis            | ⏳ Planned   |
| 5     | GCP cost ingestion & analysis            | ⏳ Planned   |
| 6     | AI recommendation engine                 | ⏳ Planned   |
| 7     | Dashboard & reporting API                | ⏳ Planned   |
| 8     | Docker containerisation of the app      | ⏳ Planned   |
| 9     | Kubernetes deployment                    | ⏳ Planned   |
| 10    | Production AWS deployment               | ⏳ Planned   |

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

## Future Improvements

- GitHub Actions CI pipeline with automated testing and linting
- Dockerfile for the application itself (Phase 8)
- Kubernetes manifests and Helm chart (Phase 9)
- Terraform infrastructure-as-code for AWS deployment (Phase 10)
- Redis-backed caching layer for provider API responses
- Rate limiting and API key authentication (Phase 2)
- Cost anomaly detection models and the AI recommendation engine (Phase 6)
