"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ApiError, getAnomalies } from "../lib/api/client";
import { formatMoney, formatPercent, getDateRange, titleCaseProvider } from "../lib/dates";
import type { AnomalyResponse, AnomalySeverity, CostAnomaly, DatePreset } from "../lib/types";

const PAGE_SIZE = 20;

function EmptyState({ message }: { message: string }) {
  return <div className="empty-state">{message}</div>;
}

export default function Anomalies({ onInvestigate }: { onInvestigate: (anomaly: CostAnomaly) => void }) {
  const [preset, setPreset] = useState<DatePreset>("30d");
  const [provider, setProvider] = useState("");
  const [accountId, setAccountId] = useState("");
  const [service, setService] = useState("");
  const [region, setRegion] = useState("");
  const [severity, setSeverity] = useState<AnomalySeverity | "">("");
  const [offset, setOffset] = useState(0);
  const [data, setData] = useState<AnomalyResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const requestId = useRef(0);
  const range = useMemo(() => getDateRange(preset), [preset]);

  const load = useCallback(async () => {
    const id = ++requestId.current;
    setLoading(true);
    setError("");
    try {
      const result = await getAnomalies({
        ...range,
        provider: provider || undefined,
        account_id: accountId || undefined,
        service: service || undefined,
        region: region || undefined,
        severity: severity || undefined,
        sort_by: "anomaly_score",
        sort_order: "desc",
        limit: PAGE_SIZE,
        offset,
      });
      if (id === requestId.current) setData(result);
    } catch (err) {
      if (id === requestId.current) {
        setError(err instanceof ApiError && err.status === 401 ? "Your session has expired. Please sign in again." : "Unable to load cost anomalies. Please try again.");
      }
    } finally {
      if (id === requestId.current) setLoading(false);
    }
  }, [accountId, offset, provider, range, region, service, severity]);

  useEffect(() => { void load(); }, [load]);

  const updateFilter = (setter: (value: string) => void, value: string) => {
    setter(value);
    setOffset(0);
  };
  const pageCount = data ? Math.max(1, Math.ceil(data.total / PAGE_SIZE)) : 1;
  const page = data ? Math.floor(data.offset / PAGE_SIZE) + 1 : 1;

  return (
    <div>
      <section className="dashboard-header" id="anomalies">
        <div><p className="eyebrow">Deterministic spend monitoring</p><h1>Cost Anomalies</h1><p className="muted">Explainable statistical signals across your cloud estate.</p></div>
        <div className="date-control" aria-label="Anomaly date range">{(["7d", "30d", "month"] as DatePreset[]).map((option) => <button key={option} className={preset === option ? "selected" : ""} onClick={() => { setPreset(option); setOffset(0); }}>{option === "7d" ? "Last 7 days" : option === "30d" ? "Last 30 days" : "Current month"}</button>)}</div>
      </section>

      <div className="filter-bar" aria-label="Anomaly filters">
        <select aria-label="Filter anomalies by provider" value={provider} onChange={(event) => updateFilter(setProvider, event.target.value)}><option value="">All Providers</option><option value="aws">AWS</option><option value="azure">Azure</option><option value="gcp">GCP</option></select>
        <select aria-label="Filter anomalies by severity" value={severity} onChange={(event) => updateFilter((value) => setSeverity(value as AnomalySeverity | ""), event.target.value)}><option value="">All Severities</option>{(["low", "medium", "high", "critical"] as AnomalySeverity[]).map((value) => <option key={value} value={value}>{value.toUpperCase()}</option>)}</select>
        <input aria-label="Filter anomalies by account" placeholder="Account / project" value={accountId} onChange={(event) => updateFilter(setAccountId, event.target.value)} />
        <input aria-label="Filter anomalies by service" placeholder="Service" value={service} onChange={(event) => updateFilter(setService, event.target.value)} />
        <input aria-label="Filter anomalies by region" placeholder="Region" value={region} onChange={(event) => updateFilter(setRegion, event.target.value)} />
      </div>

      {error ? <div className="error-banner" role="alert"><span>{error}</span><button className="ghost-button" onClick={() => void load()}>Try again</button></div> : null}
      {loading ? <div className="dashboard-grid" aria-label="Loading anomalies"><div className="skeleton" /><div className="skeleton wide" /></div> : !data ? null : <>
        <section className="dashboard-grid anomaly-summary">
          <article className="metric-card"><span className="card-label">Total anomalies</span><strong className="metric-value compact">{data.summary.total}</strong><span className="metric-note">Last {data.baseline_lookback_days} days used as baseline</span></article>
          <article className="metric-card"><span className="card-label">High / critical</span><strong className="metric-value compact">{data.summary.high_or_critical}</strong><span className="metric-note">Prioritized for investigation</span></article>
          <article className="panel"><div className="panel-heading"><div><span className="card-label">Severity distribution</span><h3>Signal strength</h3></div></div><div className="service-list">{Object.entries(data.summary.by_severity).filter(([, count]) => count > 0).map(([level, count]) => <div className="service-row" key={level}><strong className={`severity ${level}`}>{level}</strong><strong>{count}</strong></div>)}</div></article>
          <article className="panel"><div className="panel-heading"><div><span className="card-label">Anomaly trend</span><h3>Signals by day</h3></div></div><div className="service-list">{data.trend.length ? data.trend.map((point) => <div className="service-row" key={point.date}><span>{point.date}</span><strong>{point.count}</strong></div>) : <EmptyState message="No anomaly trend for this period." />}</div></article>
        </section>
        <section className="panel anomaly-list-panel"><div className="panel-heading"><div><span className="card-label">Largest anomalies</span><h3>Investigate abnormal spend</h3></div><span className="currency-badge">Median + MAD</span></div>
          {data.anomalies.length ? <div className="anomaly-list">{data.anomalies.map((anomaly) => <article className={`insight-card ${anomaly.severity}`} key={anomaly.id}><div className="insight-icon">!</div><div className="insight-content"><div className="insight-meta"><span className={`severity ${anomaly.severity}`}>{anomaly.severity}</span><span>{anomaly.date} · score {anomaly.anomaly_score}</span></div><h4>{titleCaseProvider(anomaly.provider)} · {anomaly.service}</h4><p>{formatMoney(anomaly.actual_cost, anomaly.currency)} actual vs {formatMoney(anomaly.expected_cost, anomaly.currency)} expected · {formatMoney(anomaly.deviation_amount, anomaly.currency)} deviation · {formatPercent(anomaly.deviation_percentage)}</p><small>{anomaly.account_name || anomaly.account_id || "Account unavailable"} · {anomaly.region || "Region unavailable"}</small><button className="ghost-button anomaly-action" onClick={() => onInvestigate(anomaly)}>Open in Cost Explorer</button></div></article>)}</div> : <EmptyState message="No significant cost anomalies for this period." />}
          {data.total > PAGE_SIZE ? <div className="pagination"><button className="ghost-button" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}>Previous</button><span>Page {page} of {pageCount}</span><button className="ghost-button" disabled={offset + PAGE_SIZE >= data.total} onClick={() => setOffset(offset + PAGE_SIZE)}>Next</button></div> : null}
        </section>
      </>}
    </div>
  );
}
