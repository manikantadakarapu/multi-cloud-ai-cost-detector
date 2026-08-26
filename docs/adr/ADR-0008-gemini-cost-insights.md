# ADR-0008: Gemini Explanations of Deterministic Cost Events

## Status

Accepted — 2026-08-23 (Sprint 1.5)

## Context

Sprint 1.2 established a deterministic insight contract. The dashboard now
needs a first AI capability: a concise explanation of a meaningful cost
change. Sending raw AWS, Azure, or GCP SDK payloads to an LLM would leak
provider-specific shapes and could include more data than the model needs.
A full multi-provider AI abstraction (ADR-0005) is still larger than this
sprint.

## Decision

Add a small Gemini loop behind `DashboardService` and
`GET /api/v1/dashboard/insights`:

1. Analytics produces a typed `CostEvent`.
2. Only events that cross configurable percentage or absolute thresholds
   are selected.
3. An `AIInsightContext` of facts is sent to Gemini. Raw provider SDK
   responses, credentials, and tokens are never included.
4. Gemini must return JSON. The application validates it, then attaches
   measured cost numbers from the event. The model cannot change money
   values shown to the user.
5. Successful insights are cached in the existing Redis cache. Failures
   are mapped to a safe `ai_status` and never take down the dashboard.

Gemini is the only model in this sprint. ADR-0005 remains the longer-term
vendor-abstraction plan.

## Consequences

- Deterministic insights remain the source of truth and keep working when
  `AI_INSIGHT_ENABLED` is false or Gemini is unavailable.
- The frontend can distinguish measured cost insights from AI explanations.
- Chatbots, agents, RAG, forecasting, and cloud mutations stay out of scope.
