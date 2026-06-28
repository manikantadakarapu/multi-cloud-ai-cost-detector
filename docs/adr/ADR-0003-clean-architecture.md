# ADR-0003: Clean Architecture Layering

> **Status:** Accepted
>
> **Date:** 2026-06-27 (Sprint 0.1)
>
> **Deciders:** Platform team
>
> **Technical Story:** [MCAICD-1](https://github.com/manikantadakarapu/multi-cloud-ai-cost-detective/issues/1) — Backend foundation

---

## Context

MCAICD will grow from a backend foundation into a platform with cloud
ingestion pipelines, an AI recommendation engine, a REST API surface, a
frontend dashboard, and operational tooling. Without an explicit
architectural boundary discipline, the codebase risks becoming a
tightly-coupled monolith where:

- Routes contain business logic and are hard to test without a running
  server.
- Database models leak into API schemas.
- External provider calls are scattered across the codebase.
- Adding a new cloud provider or AI vendor touches core logic.
- Extracting a service later requires a full rewrite.

The team adopted a clean architecture pattern at project inception (Sprint
0.1) to prevent these outcomes. The pattern is not dogmatic — it is a set
of dependency rules that keep the domain logic portable and the transport
layer thin.

---

## Decision

**Adopt a four-layer clean architecture with strict inward-only
dependencies.**

```
┌─────────────────────────────────────────────────────────────┐
│                    Transport Layer                          │
│  app/api/routes/  ·  app/api/deps.py  ·  app/schemas/       │
│  (FastAPI routes, dependencies, request/response models)    │
└──────────────────────────────┬──────────────────────────────┘
                               │ depends on
                               ▼
┌─────────────────────────────────────────────────────────────┐
│                      Domain Layer                           │
│  app/services/                                              │
│  (Business logic, use cases, orchestrates data & providers) │
└──────────────────────────────┬──────────────────────────────┘
                               │ depends on
                               ▼
┌─────────────────────────────────────────────────────────────┐
│                       Data Layer                            │
│  app/models/  ·  app/database/                              │
│  (ORM models, session factory, declarative base)            │
└─────────────────────────────────────────────────────────────┘
```

### Dependency Rules

| Layer | May import from | Must NOT import from |
| ----- | --------------- | -------------------- |
| **Transport** | Domain, Data, Cross-cutting | (nothing outward) |
| **Domain** | Data, Cross-cutting | Transport |
| **Data** | Cross-cutting | Transport, Domain |
| **Cross-cutting** | (stdlib, third-party) | Transport, Domain, Data |

**Cross-cutting concerns** (`app/core/`) — configuration, logging, OpenAPI
metadata — are dependency-free utilities. They are imported by all layers
but import from none.

### Invariants Enforced by the Codebase

1. **Routes never touch the database.** A route handler parses input
   (validated by `app/schemas/`), calls a service, and shapes output. No
   `session.execute()` in `app/api/routes/`.
2. **Services own the session lifecycle when they need graceful
   degradation.** `HealthService` uses `get_session_factory` (not
   `get_db_session`) so it can translate a failed probe into a clean 503
   instead of a 500.
3. **Models are pure SQLAlchemy.** No Pydantic mixing. `app/models/` is the
   single source of truth for the database schema.
4. **Schemas are pure Pydantic.** `app/schemas/` defines the API contract.
   They may mirror model fields but are separate types — no ORM model is
   returned directly from an endpoint.
5. **Provider integrations are behind interfaces.** The cloud ingestion
   layer and AI layer will expose protocols (`CloudProvider`, `AIProvider`)
   that the domain layer depends on. Concrete implementations live in
   `app/providers/` (planned), not in `app/services/`.

---

## Alternatives Considered

### Layered Architecture (Traditional)

| Characteristic | Assessment |
| -------------- | ---------- |
| **Structure** | Controller → Service → Repository → Database. |
| **Dependency direction** | Top-down. Controllers depend on services depend on repositories. |
| **Problem** | The database schema (repository) shapes the service API, which shapes the controller. Changes ripple upward. The domain is not the centre; the database is. |
| **Testability** | Services are testable with a mock repository, but the repository is tied to the ORM. |

**Verdict:** Rejected. The dependency direction is wrong for a domain-driven
system. The database is a detail, not the centre.

### Modular Monolith (Vertical Slices)

| Characteristic | Assessment |
| -------------- | ---------- |
| **Structure** | Features as top-level modules: `cost/`, `anomaly/`, `recommendation/`, each with their own routes, services, models. |
| **Dependency direction** | Modules are independent. Shared kernel for cross-cutting. |
| **Problem** | Premature modularisation. The domain boundaries are not yet stable (Sprint 0.1). Forcing vertical slices now creates artificial boundaries that will be refactored when ingestion, AI, and auth arrive. |
| **Testability** | Excellent within a slice. Harder across slices. |

**Verdict:** Rejected for now. The horizontal layering (transport/domain/data)
is the right starting point. If the domain grows large enough that a single
`app/services/` becomes unwieldy, vertical slices can be introduced *within*
the domain layer without changing the transport/domain/data dependency rule.

### Hexagonal / Ports and Adapters

| Characteristic | Assessment |
| -------------- | ---------- |
| **Structure** | Domain at the centre. Ports (interfaces) define what the domain needs. Adapters (implementations) plug into ports. |
| **Dependency direction** | All dependencies point inward to the domain. |
| **Problem** | Conceptually identical to clean architecture. The terminology (ports/adapters) is more formal; the practice is the same. |
| **Fit** | This is what the project *is doing* — the provider abstraction (ADR-0005) is a port. The clean architecture label is more familiar to the team. |

**Verdict:** Accepted in spirit. The provider abstraction *is* a port. The
clean architecture label is retained for familiarity.

---

## Consequences

### Positive

- **Domain logic is transport-agnostic.** `HealthService` is used by the
  FastAPI route, but it could be called by a CLI command, a background
  worker, a Kubernetes liveness probe, or a unit test without a FastAPI
  app. This is already demonstrated.
- **Provider swaps are localised.** Adding Azure, AWS, or GCP ingestion
  means implementing a `CloudProvider` protocol. The domain service that
  orchestrates ingestion does not change.
- **AI vendor swaps are localised.** The `AIProvider` protocol (ADR-0005)
  means switching from OpenAI to Gemini is a configuration change plus an
  adapter implementation — no domain logic touched.
- **Testability is high.** Domain services are tested with in-memory fakes
  of the data layer and provider ports. No database, no network, no
  FastAPI required.
- **Future service extraction is a boundary-drawing exercise.** If the
  ingestion pipeline or AI engine needs independent scaling, the domain
  layer is already decoupled from the transport. Extracting it to a
  separate process is a mechanical refactor, not a re-architecture.

### Negative

- **More files for simple features.** A single endpoint requires a route,
  a schema, a service, and possibly a model. This is boilerplate, but it
  is *disciplined* boilerplate — each file has a single responsibility.
- **Indirection can feel unnecessary early.** With only a health endpoint,
  the service layer feels like overhead. The payoff arrives when the
  second, third, and tenth endpoint arrive and the pattern holds.
- **Team discipline required.** A developer in a hurry can import a model
  into a route and "save time." Code review and static analysis (planned:
  `import-linter` or a custom Ruff rule) must enforce the boundary.

### Neutral

- **No framework coupling in the domain.** The domain layer has zero
  FastAPI imports. This is a feature, but it means the domain cannot use
  FastAPI-specific conveniences (e.g., `Depends`) — it must use plain
  Python dependencies.

---

## Future Considerations

- **Static enforcement:** Add `import-linter` or a custom Ruff rule to
  CI that fails if `app/api/` imports from `app/services/` *and* vice
  versa, or if `app/services/` imports from `app/api/`.
- **Vertical slices within domain:** When `app/services/` exceeds ~10
  files, introduce `app/services/cost/`, `app/services/anomaly/`,
  `app/services/recommendation/` as subpackages. The dependency rule
  (domain → data, not transport) remains.
- **CQRS for read-heavy endpoints:** If dashboard queries (Sprint 0.7)
  need denormalised read models, introduce a read-model layer in the data
  layer that the domain service populates asynchronously. The transport
  layer queries the read model; the domain layer writes the write model.
- **Event-driven domain:** If ingestion and recommendation need to be
  decoupled in time, the domain layer can emit domain events that
  background handlers consume. The transport layer remains unaware.

---

## References

- [Clean Architecture — Robert C. Martin](https://blog.cleancoder.com/uncle-bob/2012/08/13/the-clean-architecture.html)
- [ADR-0001: FastAPI](../adr/ADR-0001-fastapi.md) — the transport layer that respects the boundary
- [ADR-0002: PostgreSQL](../adr/ADR-0002-postgresql.md) — the data layer that the domain depends on
- [ADR-0005: AI Provider Abstraction](../adr/ADR-0005-ai-provider-abstraction.md) — the port pattern applied to AI vendors
- `app/api/deps.py` — the dependency injection seam that keeps routes thin
- `app/services/health.py` — the reference implementation of a transport-agnostic service
