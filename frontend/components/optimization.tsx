"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { ApiError, getOptimizationRecommendations, updateOptimizationStatus } from "../lib/api/client";
import { formatMoney, getDateRange } from "../lib/dates";
import type { OptimizationRecommendation, OptimizationStatus } from "../lib/types";

type Focus = { provider?: string; service?: string; region?: string; account_id?: string };

export default function Optimization({ onInvestigate }: { onInvestigate: (filters: Focus) => void }) {
  const range = useMemo(() => getDateRange("30d"), []);
  const [data, setData] = useState<Awaited<ReturnType<typeof getOptimizationRecommendations>> | null>(null);
  const [selected, setSelected] = useState<OptimizationRecommendation | null>(null);
  const [statusFilter, setStatusFilter] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const result = await getOptimizationRecommendations({ ...range, status: statusFilter || undefined, limit: 50 });
      setData(result);
      setSelected((current) => current ? result.recommendations.find((item) => item.recommendation_id === current.recommendation_id) || null : null);
    } catch (exception) {
      setError(exception instanceof ApiError && exception.status === 401 ? "Your session has expired. Please sign in again." : "Unable to load optimization recommendations.");
    } finally {
      setLoading(false);
    }
  }, [range, statusFilter]);

  useEffect(() => { void load(); }, [load]);

  async function changeStatus(status: OptimizationStatus) {
    if (!selected) return;
    try {
      const updated = await updateOptimizationStatus(selected.recommendation_id, status, range);
      setSelected(updated);
      await load();
    } catch {
      setError("Unable to update recommendation status.");
    }
  }

  return (
    <>
      <section className="dashboard-header">
        <div><p className="eyebrow">Deterministic FinOps guidance</p><h1>Cost Optimization</h1><p className="muted">Evidence-backed opportunities for review. No cloud resources are changed automatically.</p></div>
        <select className="filter-select" aria-label="Filter recommendations by status" value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}>
          <option value="">All statuses</option><option value="new">New</option><option value="reviewed">Reviewed</option><option value="dismissed">Dismissed</option><option value="implemented">Implemented</option>
        </select>
      </section>
      {error ? <div className="error-banner" role="alert"><span>{error}</span><button className="ghost-button" onClick={() => void load()}>Try again</button></div> : null}
      {loading ? <div className="dashboard-grid" aria-label="Loading optimization recommendations"><div className="skeleton" /><div className="skeleton" /><div className="skeleton wide" /></div> : data ? <>
        <section className="optimization-summary">
          <article className="metric-card primary"><span className="card-label">Recommendations</span><strong className="metric-value">{data.summary.total_recommendations}</strong><span className="period">{data.summary.high_or_critical} high priority</span></article>
          <article className="metric-card"><span className="card-label">Monthly opportunity</span><strong className="metric-value compact">{data.summary.estimated_monthly_savings === null ? "—" : formatMoney(data.summary.estimated_monthly_savings, "USD")}</strong><span className="metric-note">Scenario estimate, not guaranteed savings</span></article>
          <article className="metric-card"><span className="card-label">Annual opportunity</span><strong className="metric-value compact">{data.summary.estimated_annual_savings === null ? "—" : formatMoney(data.summary.estimated_annual_savings, "USD")}</strong><span className="metric-note">Based on current evidence</span></article>
        </section>
        {data.insufficient_data ? <div className="ai-status">Not enough normalized cost history to produce evidence-backed recommendations for this period.</div> : null}
        {!data.recommendations.length && !data.insufficient_data ? <div className="empty-state">No recommendations match the current filters.</div> : null}
        <section className="optimization-layout">
          <div className="panel"><div className="panel-heading"><div><span className="card-label">Review queue</span><h3>Optimization recommendations</h3></div><span className="currency-badge">{data.rule_version}</span></div><div className="service-list">
            {data.recommendations.map((item) => <button type="button" className="optimization-row" key={item.recommendation_id} onClick={() => setSelected(item)}><div><strong>{item.title}</strong><small>{item.provider} · {item.service} · {item.category.replaceAll("_", " ")}</small></div><div className="optimization-row-meta"><span className={`badge ${item.priority}`}>{item.priority}</span><strong>{item.estimated_monthly_savings === null ? "Review" : formatMoney(item.estimated_monthly_savings, item.savings_currency)}</strong></div></button>)}
          </div></div>
          {selected ? <aside className="panel optimization-detail"><div className="panel-heading"><div><span className="card-label">Recommendation detail</span><h3>{selected.service}</h3></div><button className="ghost-button" onClick={() => setSelected(null)}>Close</button></div><p className="muted">{selected.description}</p><p>{selected.rationale}</p><div className="optimization-actions"><select className="filter-select" aria-label="Recommendation status" value={selected.status} onChange={(event) => void changeStatus(event.target.value as OptimizationStatus)}><option value="new">New</option><option value="reviewed">Reviewed</option><option value="dismissed">Dismissed</option><option value="implemented">Implemented</option></select><button className="ghost-button" onClick={() => onInvestigate({ provider: selected.provider, service: selected.service, region: selected.region || undefined, account_id: selected.account_id || undefined })}>Open in Cost Explorer</button></div><h4>Verified evidence</h4><div className="service-list">{selected.evidence.map((item) => <div className="service-row" key={item.label}><span>{item.label}<small>{item.source}</small></span><strong>{item.value}</strong></div>)}</div><p className="forecast-note">{selected.savings_explanation || "No savings estimate is available from the observed data."}</p></aside> : null}
        </section>
      </> : null}
    </>
  );
}
