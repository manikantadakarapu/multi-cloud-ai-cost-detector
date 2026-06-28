# ADR-0004: Docker-First Development Environment

> **Status:** Accepted
>
> **Date:** 2026-06-27 (Sprint 0.1)
>
> **Deciders:** Platform team
>
> **Technical Story:** [MCAICD-1](https://github.com/manikantadakarapu/multi-cloud-ai-cost-detective/issues/1) — Backend foundation

---

## Context

MCAICD requires a PostgreSQL database for development, testing, and
production. The team needs a development environment that:

- Is identical for every developer regardless of host OS (Linux, macOS,
  Windows/WSL).
- Matches the production runtime (PostgreSQL 16, same configuration).
- Requires zero manual database installation or configuration.
- Supports the full migration workflow (`alembic upgrade head`) out of the
  box.
- Can be torn down and recreated in seconds for a clean slate.

The decision was made at project inception (Sprint 0.1) before any
application code was written, because the database is the first external
dependency the application has.

---

## Decision

**Adopt Docker Compose as the standard development environment for
PostgreSQL, with the application running natively on the host (via
`uvicorn --reload`).**

The current `docker-compose.yml` defines:

```yaml
services:
  postgres:
    image: postgres:16
    container_name: postgres-mcaicd
    environment:
      POSTGRES_USER: ${POSTGRES_USER:-testuser}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-testuser123}
      POSTGRES_DB: ${POSTGRES_DB:-testdb}
    ports:
      - "${POSTGRES_PORT:-5432}:5432"
    volumes:
      - postgres-mcaicd-data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER:-testuser} -d ${POSTGRES_DB:-testdb}"]
      interval: 5s
      timeout: 5s
      retries: 10
    restart: unless-stopped

volumes:
  postgres-mcaicd-data:
    name: postgres-mcaicd-data
```

The application itself runs on the host (`uvicorn app.main:app --reload`)
connecting to the containerised PostgreSQL via `localhost:5432`.

### Developer Workflow

```bash
# One-time
docker compose up -d
alembic upgrade head

# Daily
docker compose up -d          # Start DB (idempotent)
uvicorn app.main:app --reload # Start app with hot reload

# Clean slate
docker compose down -v        # Stop + delete volume
docker compose up -d
alembic upgrade head
```

---

## Alternatives Considered

### Local PostgreSQL Installation

| Criterion | Assessment |
| --------- | ---------- |
| **Consistency** | Version drift between developers (14 vs 15 vs 16). Config drift (shared_buffers, work_mem, max_connections). |
| **Onboarding** | Requires OS-specific install steps (Homebrew, apt, Chocolatey, Windows installer). PATH, service management, user creation. |
| **Isolation** | One PostgreSQL instance serves all projects. Port conflicts, database name collisions, leftover test data. |
| **Clean slate** | `DROP DATABASE` / `CREATE DATABASE` or reinstall. Slow and error-prone. |
| **Production parity** | Local config never matches managed service (RDS, Cloud SQL). |

**Verdict:** Rejected. The inconsistency and onboarding friction are
unacceptable for a team project.

### PostgreSQL in a VM (Vagrant / Multipass)

| Criterion | Assessment |
| --------- | ---------- |
| **Consistency** | High — the VM image is versioned. |
| **Onboarding** | Requires a hypervisor (VirtualBox, Hyper-V, QEMU). Heavier than Docker. |
| **Resource usage** | Full OS overhead. Slower start/stop. |
| **File sharing** | Mounting host code into the VM for hot reload is fragile. |
| **Tooling familiarity** | Docker is the de-facto standard; Vagrant is legacy. |

**Verdict:** Rejected. Docker is lighter, faster, and the industry standard.

### Testcontainers (Programmatic Containers in Tests)

| Criterion | Assessment |
| --------- | ---------- |
| **Use case** | Spins up a real PostgreSQL per test run. Excellent for CI and integration tests. |
| **Development** | Not a development environment. The app still needs a DB for manual testing and `uvicorn --reload`. |
| **Complementary** | **Accepted for CI/integration tests (planned).** Not a replacement for the dev workflow. |

**Verdict:** Complementary, not an alternative. The dev workflow needs a
persistent, addressable database for interactive development.

### Docker Compose for Everything (App + DB)

| Criterion | Assessment |
| --------- | ---------- |
| **Consistency** | Maximum — the app runs in the same container in dev, CI, and prod. |
| **Hot reload** | Requires volume-mounting source code and a reload-capable entrypoint. Works but adds complexity (file system notification issues on macOS/Windows). |
| **Debugging** | Attaching a debugger to a containerised app is an extra step. |
| **Iteration speed** | Container rebuild on dependency change. Slower than host `uvicorn --reload`. |
| **Current phase** | Sprint 0.1–0.8: the app changes daily. Containerising it now adds friction without benefit. |

**Verdict:** Deferred. The application will be containerised in Sprint 0.9
(Deployment). Until then, host execution with a containerised database
gives the best iteration speed with production-parity for the data layer.

### Cloud Development Database (Neon, Supabase, RDS Dev Instance)

| Criterion | Assessment |
| --------- | ---------- |
| **Consistency** | High — same engine as production. |
| **Latency** | Network round-trip for every query. Slower local iteration. |
| **Cost** | Free tiers exist but have limits (compute hours, storage). |
| **Offline work** | Impossible. |
| **Secrets** | Credentials must be managed per developer. |

**Verdict:** Rejected for daily development. Acceptable as a staging
environment (planned).

---

## Consequences

### Positive

- **Zero-config onboarding:** A new contributor runs `docker compose up -d`
  and has a PostgreSQL 16 instance matching production. No `brew install`,
  no `initdb`, no user creation.
- **Production parity:** The same major version (16), same authentication
  method (scram-sha-256), same default configuration. The `healthcheck`
  ensures the container is truly ready before the app connects.
- **Instant clean slate:** `docker compose down -v` deletes the volume.
  `docker compose up -d` + `alembic upgrade head` = fresh database in
  ~10 seconds.
- **Version pinning:** `postgres:16` in `docker-compose.yml` means every
  developer and CI runner uses the exact same image digest (when pinned to
  a digest in CI).
- **Portability:** Works identically on Linux, macOS, and Windows/WSL2.
  The `container_name` (`postgres-mcaicd`) makes it discoverable via
  `docker ps`.
- **CI/CD foundation:** The same `docker-compose.yml` (or a CI-specific
  variant) runs in GitHub Actions for the test suite.

### Negative

- **Docker Desktop dependency:** Required on macOS and Windows. Linux users
  can use the Docker Engine directly. This is a universal prerequisite
  documented in `README.md` and `CONTRIBUTING.md`.
- **Volume persistence confusion:** `POSTGRES_USER` / `POSTGRES_PASSWORD`
  / `POSTGRES_DB` are only honoured on **first** volume initialisation.
  Changing them in `.env` or `docker-compose.yml` later has no effect.
  Documented prominently in `docker-compose.yml` comments and
  `scripts/check_db.py`.
- **Port conflicts:** If another process uses 5432, the container fails to
  start. Mitigated by `POSTGRES_PORT` override in `.env`.
- **No app container yet:** The application runs on the host. This is
  intentional for iteration speed (see Alternatives) but means the dev
  environment is not *fully* containerised.

### Neutral

- **Healthcheck dependency:** The `pg_isready` healthcheck ensures
  `docker compose up -d` waits for PostgreSQL to accept connections.
  Without it, `alembic upgrade head` races the database startup and fails
  nondeterministically.

---

## Future Considerations

### Sprint 0.9 — Application Containerisation

A multi-stage `Dockerfile` will be added:

```dockerfile
# Builder
FROM python:3.12-slim AS builder
WORKDIR /app
COPY pyproject.toml requirements.txt ./
RUN pip install --user -r requirements.txt

# Runner
FROM python:3.12-slim
WORKDIR /app
COPY --from=builder /root/.local /root/.local
COPY app/ ./app
ENV PATH=/root/.local/bin:$PATH
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

The `docker-compose.yml` will be extended with an `app` service for
full-stack local development:

```yaml
services:
  app:
    build: .
    ports:
      - "8000:8000"
    environment:
      - DATABASE_URL=postgresql+asyncpg://testuser:testuser123@postgres:5432/testdb
    depends_on:
      postgres:
        condition: service_healthy
    volumes:
      - ./app:/app/app  # For hot reload in dev
```

### Production Deployment

The same `Dockerfile` (without the source volume mount) will be the
deployable artifact for Kubernetes (Helm) and Terraform-provisioned
infrastructure.

### Testcontainers for CI

Integration tests (planned) will use `testcontainers-python` to spin up a
fresh PostgreSQL per test module, ensuring test isolation without a shared
CI database.

---

## References

- [Docker Compose Specification](https://docs.docker.com/compose/)
- [PostgreSQL Docker Image](https://hub.docker.com/_/postgres)
- [ADR-0002: PostgreSQL](../adr/ADR-0002-postgresql.md) — the database that Docker provides
- [ADR-0003: Clean Architecture](../adr/ADR-0003-clean-architecture.md) — the layering that keeps the app portable
- `docker-compose.yml` — the authoritative dev environment definition
- `scripts/check_db.py` — the diagnostic that surfaces the most common Docker/DB footgun
