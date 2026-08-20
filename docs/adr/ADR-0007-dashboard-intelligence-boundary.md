# ADR-0007: Dashboard and Deterministic Intelligence Boundary

## Status

Accepted — 2026-08-20 (Sprint 1.2)

## Context

The first frontend dashboard needs a stable payload, while future intelligence
work may eventually add AI-generated explanations. Introducing an LLM or
provider-specific intelligence now would make the frontend contract unstable
and bypass the normalized analytics layer.

## Decision

Add `DashboardService` as a composition layer over `AnalyticsService`. It
exposes explicit Pydantic contracts for dashboard summaries and a small
provider-independent `CostInsight` contract. Sprint 1.2 generates only
deterministic insights for cost increases, decreases, and top cost drivers.
Dashboard responses and insights are cached through the existing Redis cache,
with user and query parameters in every key.

## Consequences

- Frontends receive predictable payloads without depending on internal service
  or provider models.
- The deterministic insight layer is testable and can later be replaced or
  enriched behind the same contract.
- No AI dependency, model invocation, database redesign, forecasting, or
  autonomous action is introduced.
