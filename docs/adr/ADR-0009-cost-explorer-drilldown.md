# ADR-0009: Provider-Independent Cost Explorer & Drill-Down Architecture

## Status

Accepted

## Date

2026-08-27 (Sprint 1.6)

## Context

Following Sprint 1.5 (Intelligent Cost Insights), users could view aggregate overview cards, deterministic insights, and Gemini explanations on the main dashboard. However, users could not drill down into specific dimensions of spend — such as investigating which AWS/Azure/GCP services, regions, or accounts/projects contributed to total costs within custom date ranges.

The application required a provider-independent Cost Explorer capability that supports:
1. Multi-dimensional filtering across provider, account/subscription/project, service, region, and date range.
2. Multi-dimensional aggregations / rollups (`by_provider`, `by_service`, `by_region`, `by_account`, `by_date`).
3. Sliced line-item records with pagination.
4. Fast response times backed by deterministic Redis query caching.
5. Interactive UI drill-down allowing seamless transitions:
   `Total Spend → Provider → Service → Region → Daily Trend`.

## Decisions

1. **Provider-Agnostic Cost Explorer Contract (`app/schemas/explorer.py`)**:
   - `CostRecord`: Represents a normalized line item (`date`, `provider`, `account_id`, `account_name`, `service`, `region`, `cost`, `currency`).
   - `ExplorerQuery`: Encapsulates date range, optional filters, pagination limits, and offset.
   - `ExplorerResponse`: Returns structured `overview`, paginated `records`, pre-computed `dimension_totals` (`by_provider`, `by_service`, `by_region`, `by_account`, `by_date`), and discovered `available_filters`.

2. **Layered Aggregation & Adaptive Extraction (`CostExplorerService`)**:
   - Provider implementations return rich line items via `get_explorer_records` when available.
   - If a provider adapter implements only standard `get_costs()`, `CostExplorerService` automatically synthesizes normalized line items from `services` and `daily_costs`, ensuring full backward compatibility.
   - Filtering and multi-dimensional rollup calculations occur in the service layer using exact decimal arithmetic.

3. **Deterministic Cache Strategy**:
   - Cache keys are generated deterministically using SHA-256 digests over the query JSON: `explorer:{user_scope}:{query_hash}`.
   - Responses are cached in Redis with a 1-hour TTL (`3600s`).
   - Cache failures degrade silently to live provider queries without disrupting the user experience.

4. **Security and Secret Isolation**:
   - All Explorer routes require JWT authentication (`Depends(get_current_active_user)`).
   - Rate limiting is enforced using `@enforce_cost_rate_limit`.
   - Provider credentials and raw vendor payloads are never logged or exposed to the client.

5. **Frontend Drill-Down UX**:
   - Added `CostExplorer` component into the shell with a top-level tab switcher between "Overview Dashboard" and "Cost Explorer & Drill-Down".
   - Clicking any bar or row in a breakdown panel (e.g. clicking "AmazonEC2" or "us-east-1") applies the filter immediately and updates all other breakdowns and the daily trend chart.
   - Active filter pills provide instant visibility and one-click removal of active drill-down filters.

## Consequences

- **Positive**: Users gain granular multi-cloud visibility with fast sub-second drill-down performance.
- **Positive**: Decoupled schema protects the frontend from cloud SDK changes.
- **Neutral**: Providers with coarse granularity (e.g. missing regional detail in legacy billing exports) default gracefully to `"global"` without errors.
- **Compliance**: Preserves existing authentication, rate limiting, and zero-leakage security invariants.
