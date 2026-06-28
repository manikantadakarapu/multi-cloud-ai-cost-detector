# ADR-0001: FastAPI as the Web Framework

> **Status:** Accepted
>
> **Date:** 2026-06-27 (Sprint 0.1)
>
> **Deciders:** Platform team
>
> **Technical Story:** [MCAICD-1](https://github.com/manikantadakarapu/multi-cloud-ai-cost-detective/issues/1) — Backend foundation

---

## Context

MCAICD needs a web framework that serves as the transport layer for a
multi-cloud cost intelligence platform. The platform will expose REST APIs
for cost ingestion, anomaly detection, and AI-powered recommendations. It
must handle concurrent I/O to cloud provider APIs and AI model endpoints
efficiently, generate accurate OpenAPI documentation for API consumers, and
provide a developer experience that enables rapid iteration without
sacrificing production readiness.

The decision was made at project inception (Sprint 0.1) when the codebase
was empty. The framework choice shapes every subsequent architectural
decision — routing, dependency injection, validation, serialization, and
the async contract that the rest of the stack must honour.

---

## Decision

**Adopt FastAPI as the web framework.**

The application is built on FastAPI 0.111+ with the following commitments:

- **Application factory pattern** (`app/main.py:create_app`) so the ASGI
  app is constructible by both `uvicorn` and test clients.
- **Async-first** — all route handlers, service methods, and database
  operations are `async def`.
- **Pydantic v2** for request/response validation and OpenAPI schema
  generation.
- **Structured lifespan management** for startup/shutdown hooks (logging
  configuration, database engine disposal).
- **OpenAPI metadata** centralised in `app/core/openapi.py` so documentation
  is maintained alongside code, not retrofitted.

---

## Alternatives Considered

### Flask

| Criterion | Assessment |
| --------- | ---------- |
| **Async support** | Requires extensions (`flask-async`, Quart) or manual event-loop management. Not native. |
| **Type safety** | No built-in validation; relies on external libraries (marshmallow, pydantic) with manual integration. |
| **OpenAPI generation** | Not native; requires `flasgger`, `apispec`, or manual YAML. |
| **Developer experience** | Flexible but unopinionated. More boilerplate for the same guarantees. |
| **Performance** | Synchronous by default. Async is a second-class concern. |
| **Ecosystem** | Mature, but the async story is fragmented. |

**Verdict:** Rejected. The async-first requirement and the desire for
first-class type-driven OpenAPI generation make Flask a poor fit.

### Django / Django REST Framework

| Criterion | Assessment |
| --------- | ---------- |
| **Async support** | Native async views since Django 4.1, but the ORM is still synchronous by default. Async ORM is experimental. |
| **Type safety** | DRF serializers are not type-native; mypy integration is partial. |
| **OpenAPI generation** | `drf-spectacular` is excellent, but it reflects DRF internals, not Python types. |
| **Developer experience** | Batteries-included, but the framework weight is high for a stateless API layer. |
| **Performance** | The ORM and middleware stack add latency. Not ideal for a thin transport layer. |
| **Ecosystem** | Excellent for full-stack apps; overkill for an API service. |

**Verdict:** Rejected. The platform is an API service, not a full-stack
application. The ORM weight and the sync-first history are misaligned with
the async SQLAlchemy 2.x choice.

### Express.js (Node.js)

| Criterion | Assessment |
| --------- | ---------- |
| **Async support** | Native (JavaScript is async by default). |
| **Type safety** | Requires TypeScript. Adds a compilation step and a second language. |
| **OpenAPI generation** | Requires manual annotation (`swagger-jsdoc`, `tsoa`). Not type-driven. |
| **Developer experience** | Familiar to JS teams, but the Python ML/AI ecosystem is the platform's domain. |
| **Performance** | Competitive, but the team's expertise and the AI/ML library ecosystem are in Python. |
| **Ecosystem** | Rich, but the cost-analysis and AI provider libraries are Python-first. |

**Verdict:** Rejected. The AI/ML and data-processing ecosystem is
Python-centric. Introducing a second language for the transport layer
adds cognitive load without benefit.

### FastAPI

| Criterion | Assessment |
| --------- | ---------- |
| **Async support** | Native, built on Starlette/ASGI. All handlers can be `async def`. |
| **Type safety** | Pydantic v2 models drive validation, serialization, and OpenAPI. |
| **OpenAPI generation** | Automatic from type hints. Swagger UI and ReDoc included. |
| **Developer experience** | Low boilerplate, high ergonomics. Dependency injection is type-driven. |
| **Performance** | On par with Node.js/Go for I/O-bound workloads. |
| **Ecosystem** | Python-first, integrates with the SQLAlchemy/Pydantic/ML stack. |

**Verdict:** Accepted. FastAPI satisfies every requirement with a single,
coherent stack.

---

## Consequences

### Positive

- **Async everywhere:** The entire call chain — route → service → database
  → external API — is async. No thread-pool executor needed for I/O.
- **Contract-driven development:** Pydantic models are the single source of
  truth for request/response shapes and OpenAPI docs. Schema drift is a
  type error.
- **Developer velocity:** Hot reload (`uvicorn --reload`), automatic docs
  (`/docs`, `/redoc`), and dependency injection by type reduce boilerplate
  to near zero.
- **Testability:** The factory pattern and ASGI transport let tests exercise
  the real app in-memory without binding a port.
- **Production readiness:** Used at Netflix, Uber, Microsoft, and others
  for high-throughput services. The architecture scales horizontally.

### Negative

- **Smaller ecosystem than Flask/Django:** Fewer off-the-shelf admin
  panels, auth packages, and CMS integrations. Not a concern for a pure
  API platform.
- **Pydantic v2 migration:** The v1→v2 transition broke some patterns.
  Locking to `>=2.8.0,<3.0.0` pins the API surface.
- **Starlette dependency:** FastAPI is a thin layer on Starlette. Starlette
  API changes can ripple. Mitigated by pinning FastAPI range.

### Neutral

- **Learning curve:** Developers unfamiliar with type-driven frameworks need
  a brief ramp. The payoff is immediate — the types *are* the docs.

---

## Future Considerations

- **API versioning strategy:** FastAPI's router prefixing (`/api/v1`) is
  the current versioning mechanism. If header-based or content-negotiation
  versioning becomes necessary, a custom middleware or dependency can
  implement it without changing the framework.
- **GraphQL:** If a flexible query layer is needed for the dashboard
  (Sprint 0.7), `strawberry-graphql` integrates with FastAPI and Pydantic.
  This is an additive decision, not a replacement.
- **Edge deployment:** FastAPI runs on any ASGI server. If serverless
  (AWS Lambda, Cloudflare Workers) becomes a target, `mangum` or
  `aws-lambda-powertools` can adapt the app without code changes.

---

## References

- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [Starlette ASGI Framework](https://www.starlette.io/)
- [Pydantic v2 Documentation](https://docs.pydantic.dev/latest/)
- [ADR-0003: Clean Architecture](../adr/ADR-0003-clean-architecture.md) —
  the layering that FastAPI routes respect
- [ADR-0005: AI Provider Abstraction](../adr/ADR-0005-ai-provider-abstraction.md) —
  the async contract that FastAPI enables
