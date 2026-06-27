# Contributing to Multi-Cloud AI Cost Detective

Thank you for your interest in contributing to **Multi-Cloud AI Cost Detective**
(MCAICD). This document describes how to set up the project locally, the
coding standards we follow, and the process for submitting changes.

---

## Project Overview

MCAICD is a FastAPI backend platform that ingests cost data across AWS,
Azure, and Google Cloud Platform, normalises it into a unified schema, and
will eventually apply AI-powered anomaly detection to surface cloud waste.

Phase 1 (the backend foundation) is complete. Subsequent phases add cloud
provider integrations, authentication, and the AI recommendation engine.

---

## Local Development Setup

### Prerequisites

- **Python** 3.12 or newer
- **Docker Desktop** (for the local PostgreSQL instance)
- **Git**

### Clone the repository

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

### Configure environment variables

```bash
cp .env.example .env
```

Edit `.env` and set `DATABASE_URL` to match your PostgreSQL credentials.
See the [Environment Variables](README.md#environment-variables) table in the
README for the full list.

### Start PostgreSQL

```bash
docker compose up -d
```

### Run database migrations

```bash
alembic upgrade head
```

### Start the FastAPI backend

```bash
uvicorn app.main:app --reload
```

The API is now available at <http://localhost:8000>. Interactive Swagger docs
live at <http://localhost:8000/docs>.

---

## Coding Standards

- **Language**: Python 3.12+. Use modern type hints (`list[str]`, not
  `List[str]`).
- **Linter / formatter**: [Ruff](https://docs.astral.sh/ruff/) handles both
  linting and formatting. Line length is **100** characters.
- **Async-first**: all database access uses async SQLAlchemy 2.x and
  `asyncpg`. Do not introduce synchronous database calls.
- **Configuration**: all settings flow through `app/core/config.py`
  (Pydantic Settings). Do not read environment variables directly in
  application code.
- **Structure**: keep routes thin. Business logic belongs in
  `app/services/`, data models in `app/models/`, and request/response
  schemas in `app/schemas/`.

Run these before every commit:

```bash
ruff check .
ruff format .
```

---

## Branch Naming Strategy

Use lowercase, kebab-case descriptions with a type prefix:

| Prefix      | Use when                                  | Example                         |
| ----------- | ----------------------------------------- | ------------------------------- |
| `feature/`  | New functionality                         | `feature/azure-cost-ingestion`  |
| `bugfix/`   | Bug fixes                                 | `bugfix/health-timestamp-tz`    |
| `chore/`    | Tooling, dependencies, refactors          | `chore/bump-sqlalchemy`         |
| `docs/`     | Documentation-only changes                | `docs/update-readme`            |

---

## Commit Message Convention

This project follows [Conventional Commits](https://www.conventionalcommits.org/).

```
<type>(<optional scope>): <short imperative description>

<optional body explaining why>

<optional footer>
```

Common types:

```
feat:     a new feature
fix:      a bug fix
docs:     documentation only
refactor: code change that neither fixes a bug nor adds a feature
test:     adding or correcting tests
chore:    build, tooling, or dependency changes
```

Examples:

```
feat: add Azure cost ingestion endpoint
fix: correct timezone in health timestamp
docs: update environment variable table
chore: bump SQLAlchemy to 2.0.32
```

---

## Pull Request Process

1. **Create a branch** from `main` using the naming strategy above.
2. **Write tests** for any new endpoint, service, or schema. Tests live under
   `tests/` and mirror the `app/` structure.
3. **Run the full quality gate** locally:
   ```bash
   ruff check .
   ruff format .
   pytest
   ```
4. **Open a pull request** against `main` using the
   [pull request template](.github/PULL_REQUEST_TEMPLATE.md).
5. **Link the related issue** in the PR description.
6. **Request review** from a maintainer. The `CODEOWNERS` file automatically
   adds the required reviewer.
7. **Address review feedback** with additional commits. Avoid force-pushing
   once review has started.
8. **Squash-merge** is the default merge strategy. Your PR should have a
   clean, conventional-commit-friendly title.

---

## Testing Expectations

- Every new endpoint must have at least one happy-path test and one
  error-path test.
- Use `pytest-asyncio` for async tests. The suite is configured with
  `asyncio_mode = "auto"`.
- Use the `client` fixture in `tests/conftest.py` (httpx + ASGITransport)
  for endpoint tests — it exercises the real ASGI app without binding a port.
- Do not commit snapshot files or large fixtures. Keep test data inline and
  minimal.
- `pytest` must pass locally before a PR is submitted.

---

## Code Review Expectations

Reviewers and authors share responsibility for code quality.

**For authors:**

- Self-review your diff before requesting review.
- Ensure the PR description explains *why* the change is needed, not just
  *what* changed.
- Keep PRs small and focused — one logical change per PR.

**For reviewers:**

- Review for correctness, security, performance, and clarity — in that order.
- Leave constructive, specific feedback. Suggest alternatives rather than
  just pointing out problems.
- Approve only when `ruff check`, `ruff format`, and `pytest` all pass and
  the change is within the agreed scope.

---

## Questions

If anything in this document is unclear, please open an issue with the
`documentation` label and we will improve it.
