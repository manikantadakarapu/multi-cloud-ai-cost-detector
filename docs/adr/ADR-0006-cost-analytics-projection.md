# ADR-0006: Cost Analytics as a Normalized Projection

## Status

Accepted — 2026-08-20 (Sprint 1.1)

## Context

The platform needs summaries, provider and service breakdowns, daily trends,
period comparisons, and deterministic cost drivers across AWS, Azure, and GCP.
The provider APIs already return normalized service totals through
`CostResponse`, but trends also require daily points. Adding a separate
analytics database table would introduce ingestion, retention, and currency
conversion concerns before the product has a snapshot/reporting requirement.

## Decision

Analytics is implemented as a read-time projection over normalized provider
responses. The shared `CostResponse` contract now includes optional
`daily_costs`; each provider populates it for daily queries. `AnalyticsService`
loads one daily response per selected provider, performs all monetary
arithmetic with `Decimal`, validates that currencies are compatible, and
returns explicit Pydantic response models.

Analytics reuses `CostAggregatorService` and its Redis-backed provider-response
cache. If Redis is unavailable, the existing cache fallback permits the live
provider request to continue. No new analytics persistence table is created.

## Consequences

- Analytics remains provider-agnostic and avoids N+1 provider calls per metric.
- Results reflect the provider data available at request time and are not an
  immutable historical ledger.
- Mixed currencies are rejected; currency conversion is intentionally outside
  Sprint 1.1 scope.
- Historical snapshots, scheduled reporting, forecasting, and AI-generated
  recommendations remain future work and may justify a dedicated persistence
  model later.
