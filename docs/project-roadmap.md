# Project Roadmap

> **Purpose**
> This document is the canonical product and engineering roadmap for the
> Multi-Cloud AI Cost Detective (MCAICD) platform. It communicates the vision,
> the sprint cadence, the milestone plan, and the decision boundaries that
> govern what is built and when.
>
> **Audience**
> Engineering managers, staff engineers, contributors, recruiters, and
> hiring managers who need to understand where the project is headed and how
> the near-term work ladders up to the long-term vision.
>
> **Last Updated:** 2026-08-23 (Sprint 1.5)
>
> **Status legend:** ✅ Complete · 🚧 In Progress · ⏳ Planned · 🔭 Future

---

## Table of Contents

- [Vision](#vision)
- [Project Goals](#project-goals)
- [Sprint Cadence](#sprint-cadence)
- [Current Sprint Status](#current-sprint-status)
- [Roadmap Overview](#roadmap-overview)
- [Planned Milestones](#planned-milestones)
- [Feature Timeline](#feature-timeline)
- [Future Enhancements](#future-enhancements)
- [Long-term Vision](#long-term-vision)
- [Non-Goals](#non-goals)
- [Change Log](#change-log)

---

## Vision

> **Become the de-facto open platform that gives every cloud engineering team
> a single, honest view of where their AI spend is going — across AWS, Azure,
> and GCP — and the AI-driven recommendations to bring it back under control.**

Cloud cost tooling today is fragmented along provider boundaries. Each cloud
ships its own billing console, its own tagging model, and its own anomaly
alerts. Teams that run workloads on more than one provider end up
reconciling spreadsheets, missing cross-cloud cost drift, and reacting to
surprise bills weeks after the damage is done.

MCAICD closes that gap. It ingests billing and usage data from every major
cloud, normalises it into a single schema, applies anomaly detection to
surface unexpected spend in near real time, and layers an AI recommendation
engine on top to suggest concrete, actionable optimisations — not dashboards
that require a human analyst to interpret.

---

## Project Goals

| # | Goal | Why it matters |
| - | ---- | -------------- |
| 1 | **Provider-agnostic ingestion** | One pipeline, three clouds. Cost data normalised into a unified schema so cross-cloud analysis is a first-class operation, not an export-and-reconcile afterthought. |
| 2 | **AI-driven recommendations** | Move from "you spent more" to "here is exactly what to turn off, resize, or commit to, and how much you will save." |
| 3 | **Production-grade engineering** | Clean architecture, typed contracts, migration-managed schema, Docker-first development, structured observability. The platform must be operable, not just demonstrable. |
| 4 | **Open and extensible** | A clean provider abstraction and a documented ADR trail so contributors can add a cloud or an AI provider without touching core logic. |
| 5 | **Self-hostable** | No vendor lock-in on the platform itself. Teams own their data, their keys, and their deployment topology. |

---

## Sprint Cadence

MCAICD follows a two-week sprint cadence with numbered sprints. Sprint `0.x`
sprints build the foundation; sprint `1.0` marks the first production-ready
release.

```mermaid
gantt
    title MCAICD Sprint Timeline (indicative)
    dateFormat  YYYY-MM-DD
    axisFormat  %b %d

    section Foundation
    Sprint 0.1 Backend Foundation       :done, s01, 2026-06-14, 14d
    Sprint 0.2 Docs & Architecture      :done, s02, 2026-06-28, 14d
    Sprint 0.3 Authentication           :done, s03, after s02, 14d

    section Core Platform
    Sprint 0.4-0.7 Cloud & Cost APIs     :done, s04, after s03, 28d
    Sprint 0.5 AI Analysis Engine       :s05, after s04, 14d
    Sprint 0.6 REST APIs                :s06, after s05, 14d

    section Surface & Ops
    Sprint 0.8 Frontend Dashboard       :s07, after s06, 21d
    Sprint 0.9 Deployment               :s09, after s07, 14d

    section Release
    Sprint 1.0 API Security              :done, s10, after s04, 14d
```

> Dates are indicative and adjusted at sprint planning. The graph reflects
> sequencing dependencies, not hard calendar commitments.

---

## Current Sprint Status

### Sprint 1.0 — Authentication & API Security ✅ Complete

**Focus:** Protect the complete cost API surface with local JWT Bearer
authentication and harden the authentication endpoints.

| Deliverable | Status |
| ----------- | ------ |
| JWT protection on all cost endpoints | ✅ Delivered |
| Auth endpoint rate limiting | ✅ Delivered |
| Refresh-token validation on logout | ✅ Delivered |
| Authentication tests and quality-gate formatting | ✅ Delivered |
| README and architecture updates | ✅ Delivered |

**Exit criteria:** unauthenticated cost requests are rejected, authentication
abuse controls are active, logout rejects invalid refresh tokens, and the
implementation is documented.

---

### Sprint 1.1 — Cost Analytics & Intelligence Foundation ✅ Complete

**Focus:** Build deterministic, currency-aware analytics over normalized
multi-cloud cost responses without introducing premature analytics persistence.

| Deliverable | Status |
| ----------- | ------ |
| Daily cost points in the shared provider contract | ✅ Delivered |
| Authenticated summary, breakdown, trend, comparison, and driver APIs | ✅ Delivered |
| Decimal arithmetic and mixed-currency validation | ✅ Delivered |
| Analytics tests, ADR, architecture, README, and changelog updates | ✅ Delivered |

**Exit criteria:** analytics endpoints are authenticated, responses use
explicit schemas, provider calls are reused through the existing cache path,
and tests plus quality gates pass.

---

### Sprint 1.2 — Frontend Readiness & Intelligence Contracts ✅ Complete

**Focus:** Stabilize the dashboard API and establish a deterministic insight
boundary for future intelligence services.

| Deliverable | Status |
| ----------- | ------ |
| Frontend-oriented dashboard summary contract | ✅ Delivered |
| Deterministic insight schema and rule generation | ✅ Delivered |
| Authenticated dashboard endpoints with Redis reuse | ✅ Delivered |
| Focused tests, OpenAPI, ADR, and documentation | ✅ Delivered |

**Exit criteria:** the frontend can consume explicit summary and insight
payloads without provider-specific knowledge, and no AI/LLM implementation is
introduced.

---

### Sprint 1.3 — Frontend MVP ✅ Complete

**Focus:** Deliver a small dashboard that consumes the Sprint 1.2 contracts
without expanding the backend surface.

| Deliverable | Status |
| ----------- | ------ |
| Next.js App Router foundation and responsive dashboard shell | ✅ Delivered |
| JWT login, logout, token refresh, and centralized typed API client | ✅ Delivered |
| Overview, provider breakdown, daily trend, top services, and insights | ✅ Delivered |
| Date presets plus loading, error, and empty states | ✅ Delivered |
| Frontend lint, typecheck, tests, and production build | ✅ Delivered |
| Frontend setup documentation and changelog updates | ✅ Delivered |

**Exit criteria:** the dashboard runs against the existing backend APIs, uses
live response data, and passes frontend and backend quality gates without
adding AI/LLM, forecasting, or new backend architecture.

---

### Sprint 1.5 — Intelligent Cost Insights ✅ Complete

**Focus:** Generate a concise Gemini explanation of meaningful deterministic
cost events and display it in the existing dashboard.

| Deliverable | Status |
| ----------- | ------ |
| Typed cost events and threshold selection | ✅ Delivered |
| Facts-only Gemini context and structured validation | ✅ Delivered |
| Redis-cached AI insights with dashboard-safe failure states | ✅ Delivered |
| Cost Insights UI distinguishing measured facts from AI explanations | ✅ Delivered |

**Exit criteria:** a meaningful cost change can be explained by Gemini, and
the dashboard remains available when AI is disabled or fails.

AI insights explain deterministic cost events. They do not independently
query or modify cloud resources.

---

### Sprint 1.6 — Cost Explorer & Drill-Down ✅ Complete

**Focus:** Deliver a provider-independent Cost Explorer service and interactive
drill-down UI allowing users to filter, slice, and investigate multi-cloud spend.

| Deliverable | Status |
| ----------- | ------ |
| Normalized `CostRecord`, `ExplorerQuery`, and `ExplorerResponse` schemas | ✅ Delivered |
| Multi-dimensional `CostExplorerService` with automated rollups | ✅ Delivered |
| Authenticated `GET /api/v1/explorer` endpoint with rate limiting | ✅ Delivered |
| Redis query caching with SHA-256 query digests and graceful fallback | ✅ Delivered |
| Interactive drill-down UI with filters, breakdowns, trend chart, and line items | ✅ Delivered |
| Architecture documentation, ADR-0009, and full test suite | ✅ Delivered |

**Exit criteria:** authenticated users can explore and filter multi-cloud spend
across providers, services, regions, accounts, and dates with sub-second drill-down.

---
### Sprint 0.1 — Backend Foundation ✅ Complete

Shipped the production backend foundation. The full changelog entry is in
[`CHANGELOG.md`](../CHANGELOG.md) under `[0.1.0]`.

Highlights:

- FastAPI application factory with lifespan management.
- Async SQLAlchemy 2.x engine, session factory, and declarative base with
  naming conventions.
- Alembic migration setup with autogenerate and an async `env.py`.
- Pydantic v2 Settings configuration with `.env` loading and a
  `database_url_source` diagnostic field.
- Structured JSON logging with a custom `JsonFormatter`.
- Production health endpoint (`GET /api/v1/health`) with a live `SELECT 1`
  probe and HTTP 503 degradation.
- Service root endpoint (`GET /`) for discovery.
- Rich OpenAPI / Swagger metadata.
- Docker Compose for local PostgreSQL 16.
- Test scaffold with `pytest`, `pytest-asyncio`, and an httpx ASGI client.

---

## Roadmap Overview

| Sprint | Status | Description |
| ------ | ------ | ----------- |
| 0.1 | ✅ Complete | Backend foundation — FastAPI app factory, async SQLAlchemy 2.x, PostgreSQL, Alembic, structured logging, health endpoint. |
| 0.2 | ✅ Complete | Engineering documentation & architecture — ADRs, architecture doc, development workflow, roadmap. |
| 0.3 | ✅ Complete | Authentication foundation — local JWT registration, login, refresh, logout, and `/me`. Azure AD, Google Login, and RBAC remain future work. |
| 0.4 | ✅ Complete | Cloud integrations — AWS Cost Explorer, Azure Cost Management, and GCP Billing integration with normalized responses and tests. |
| 0.5 | ⏳ Planned | AI analysis engine — anomaly detection, idle resource detection, recommendation generation. |
| 0.6 | ⏳ Planned | REST APIs — cost query, anomaly, recommendation, and reporting endpoints with pagination and filtering. |
| 0.7 | ✅ Complete | Provider-independent cost aggregation — unified `/api/v1/costs` endpoint, provider dispatch, shared schema, registry, caching, and rate limiting. |
| 0.8 | ⏳ Planned | Frontend dashboard — React/Next.js, cost breakdowns, anomaly feed, recommendation inbox. |
| 0.9 | ⏳ Planned | Deployment — Dockerfile for the app, Kubernetes manifests, Helm chart, Terraform IaC. |
| 1.0 | ✅ Complete | Authentication & API Security — JWT Bearer protection, auth rate limiting, logout validation, tests, and documentation. |
| 1.1 | ✅ Complete | Cost Analytics & Intelligence Foundation — daily normalization, analytics APIs, Decimal calculations, currency validation, cost drivers, and documentation. |
| 1.2 | ✅ Complete | Frontend Readiness & Intelligence Contracts — dashboard summary, deterministic insights, explicit schemas, cache reuse, and documentation. |
| 1.3 | ✅ Complete | Frontend MVP — Next.js dashboard shell, JWT integration, live analytics views, date presets, responsive states, and quality gates. |
| 1.4 | ✅ Complete | Live dashboard integration — frontend consumes live backend cost data. |
| 1.5 | ✅ Complete | Intelligent cost insights — Gemini explanations of selected deterministic cost events with dashboard fallback. |

---

## Planned Milestones

### Milestone M1 — Foundation Locked (Sprint 0.1) ✅

The backend is runnable, the database is wired, migrations are in place, and
a health probe proves the stack end-to-end. This milestone exists so that
every subsequent sprint starts from a green build, not a whiteboard.

**Evidence:** `pytest` passes; `GET /api/v1/health` returns `healthy` against
a live PostgreSQL; `alembic upgrade head` runs cleanly.

### Milestone M2 — Engineering Readiness (Sprint 0.2) ✅

The repository is contributor-ready: a new engineer can clone, read the ADRs,
understand the architecture, and start a focused task within a single
session. This is the gate that must clear before authentication work begins,
because authentication will touch every layer and the decisions need to be
recorded first.

**Evidence:** `docs/` populated; five ADRs accepted; README links to all
documentation.

### Milestone M3 — Authenticated API Surface (Sprint 0.3 / 1.0) ✅

The platform has a real identity boundary. Local JWT Bearer tokens gate all
cost endpoints, auth endpoints are rate-limited, and logout validates the
submitted refresh token. Azure AD, Google Login, and RBAC remain future work.

**Evidence:** protected endpoints return 401 without a token; JWT flow tests
pass; invalid logout tokens are rejected;
the auth rate-limit behavior is covered by tests.

### Milestone M4 — Unified Cost API (Sprint 0.4 / 0.7) ✅

The platform exposes AWS, Azure, and GCP cost data through normalized provider
contracts and a provider-independent aggregation endpoint.

**Evidence:** provider integrations, registry dispatch, normalized responses,
cache behavior, and endpoint error paths are covered by tests.

### Milestone M5 — AI Recommendations (Sprint 0.5)

The platform stops being a cost mirror and starts being a cost advisor. The
anomaly engine flags unexpected spend; the recommendation engine produces
ranked, actionable suggestions backed by the AI provider abstraction.

**Evidence:** anomaly detection surfaces a seeded spike; the recommendation
endpoint returns ordered suggestions with estimated savings.

### Milestone M6 — Public API (Sprint 0.6)

The platform exposes a versioned, documented, paginated REST surface that
external integrations and the future dashboard can consume.

**Evidence:** `/api/v1` cost, anomaly, and recommendation endpoints are live;
OpenAPI spec is complete; integration tests cover happy and error paths.

### Milestone M7 — Operator Surface (Sprint 0.7 + 0.8)

Engineering and finance teams can use a real UI: dashboards for cost
breakdowns, an anomaly feed, and a recommendation inbox, with real-time
WebSocket push for live anomalies.

**Evidence:** dashboard renders real cost data; WebSocket channel delivers a
seeded anomaly event; alerting rules fire to configured channels.

### Milestone M8 — Production Deployment (Sprint 0.9)

The platform will run in Kubernetes with IaC-provisioned infrastructure,
CI/CD, load testing, and a security review. Sprint 1.0 authentication work is
complete, but deployment and general availability remain planned.

**Evidence:** Helm chart deploys to a staging cluster; Terraform provisions
the cloud backing; load tests meet the SLO; security review passes.

---

## Feature Timeline

```mermaid
graph LR
    S01[Sprint 0.1<br/>Backend Foundation] --> S02[Sprint 0.2<br/>Docs & ADRs]
    S02 --> S03[Sprint 0.3<br/>Authentication<br/>JWT · Azure AD · Google]
    S03 --> S04[Sprint 0.4<br/>Cloud Integrations<br/>Azure · AWS · GCP]
    S04 --> S05[Sprint 0.5<br/>AI Analysis Engine]
    S05 --> S06[Sprint 0.6<br/>REST APIs]
    S06 --> S07[Sprint 0.7<br/>Frontend Dashboard]
    S07 --> S08[Sprint 0.8<br/>Real-time Monitoring]
    S08 --> S09[Sprint 0.9<br/>Deployment<br/>K8s · Helm · Terraform]
    S09 --> S10(((Sprint 1.0<br/>Production Release)))
```

The timeline is strictly sequential up to Sprint 0.6 because each layer is
the input to the next: you cannot detect anomalies without ingested cost
data, and you cannot expose recommendations without a detection engine.
From Sprint 0.7 onward some parallelisation is possible (dashboard and
real-time monitoring share a frontend) but the roadmap keeps them ordered
to preserve review focus.

---

## Future Enhancements

Beyond Sprint 1.0, the platform is expected to grow along these axes. None
of these are committed sprints — they are the candidate backlog.

- **Multi-tenant isolation** — per-organisation data partitions so the
  platform can be offered as a hosted service, not just self-hosted.
- **FinOps collaboration** — approval workflows for recommendations so a
  platform engineer can accept, defer, or reject a suggestion and the
  outcome feeds back into the model.
- **Predictive budgeting** — forward-looking budget forecasts derived from
  historical spend trajectories, not just rear-looking anomaly detection.
- **Reserved-instance / commitment optimiser** — a dedicated analyser that
  recommends committed-use purchases across providers.
- **Carbon cost attribution** — surface the carbon footprint of cloud spend
  alongside the dollar cost, using provider sustainability APIs.
- **Terraform / IaC drift integration** — correlate cost anomalies with
  infrastructure changes so a spike is traceable to a merged PR.
- **Plugin marketplace** — a stable extension contract so third parties can
  ship custom cost analysers without forking the core.

---

## Long-term Vision

The north star is a platform that a platform engineering team can drop in
next to their existing observability stack and get, within a day, a single
view of cloud spend across every provider they run — with AI doing the
first pass of triage so the team spends its time acting on recommendations,
not building spreadsheets.

Three properties define that future state:

1. **Provider-agnostic by default.** Adding a fourth cloud is a
   provider-adapter contribution, not a platform re-architecture. The ADR
   trail (see [ADR-0005](adr/ADR-0005-ai-provider-abstraction.md)) is the
   contract that protects this.
2. **AI as a colleague, not a dashboard.** The platform's output is a ranked
   list of actions with estimated savings and rollback notes — not a chart
   that requires a human to decide what it means.
3. **Ownable.** No SaaS dependency on the platform itself. Teams self-host,
   own their keys, and keep their billing data inside their own boundary.

---

## Non-Goals

Being explicit about what MCAICD is **not** trying to be keeps scope honest:

- **Not a general-purpose FinOps suite.** The focus is AI cost detection and
  recommendation, not procurement, invoicing, or chargeback workflows.
- **Not a cloud management platform.** MCAICD does not provision, scale, or
  terminate resources. It recommends; the operator acts.
- **Not a replacement for provider billing consoles.** The platform
  ingests and normalises billing data; the provider console remains the
  source of truth for invoice-level detail.
- **Not a real-time streaming cost pipeline.** Sprint 0.8 adds real-time
  *anomaly* monitoring, not real-time *cost* ingestion. Billing data is
  inherently lagged by the provider's own refresh cadence.

---

## Change Log

| Date | Sprint | Change |
| ---- | ------ | ------ |
| 2026-06-27 | 0.1 | Initial roadmap published with backend foundation complete. |
| 2026-06-28 | 0.2 | Roadmap restructured into sprint-based plan; added milestones, timeline, non-goals, and long-term vision. |
| 2026-07-12 | 1.0 | Updated completed sprints through API security and documented the remaining AI, API, frontend, and deployment work. |
