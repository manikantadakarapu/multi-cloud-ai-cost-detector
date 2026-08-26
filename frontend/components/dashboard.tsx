"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ApiError, getDashboardInsights, getDashboardSummary } from "../lib/api/client";
import { aiExplanationNotice } from "../lib/ai-insights";
import { formatDateLabel, formatMoney, formatPercent, getDateRange, titleCaseProvider } from "../lib/dates";
import type { AIInsight, CostInsight, DashboardInsights, DashboardSummary, DatePreset } from "../lib/types";
import CostExplorer from "./explorer";
import Shell from "./shell";

function EmptyState({ message }: { message: string }) { return <div className="empty-state">{message}</div>; }
function LoadingDashboard() { return <div className="dashboard-grid" aria-label="Loading dashboard"><div className="skeleton hero" /><div className="skeleton" /><div className="skeleton wide" /><div className="skeleton tall" /><div className="skeleton tall" /></div>; }

function TrendChart({ points, currency }: { points: DashboardSummary["trend"]; currency: string }) {
  if (!points.length) return <EmptyState message="No cost data available for this period." />;
  const values = points.map((point) => Number(point.cost));
  const max = Math.max(...values, 1);
  const min = Math.min(...values, 0);
  const width = 760;
  const height = 220;
  const pointsPath = points.map((point, index) => {
    const x = points.length === 1 ? width / 2 : (index / (points.length - 1)) * width;
    const y = height - ((Number(point.cost) - min) / Math.max(max - min, 1)) * (height - 28) - 14;
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(" ");
  return <div className="trend-chart"><div className="chart-labels"><span>{formatMoney(max, currency)}</span><span>{formatMoney(min, currency)}</span></div><svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Daily cloud spend trend" preserveAspectRatio="none"><defs><linearGradient id="trend-fill" x1="0" x2="0" y1="0" y2="1"><stop offset="0%" stopColor="#24b49b" stopOpacity=".25" /><stop offset="100%" stopColor="#24b49b" stopOpacity="0" /></linearGradient></defs><polyline points={`0,${height} ${pointsPath} ${width},${height}`} fill="url(#trend-fill)" stroke="none" /><polyline points={pointsPath} fill="none" stroke="#24b49b" strokeWidth="4" strokeLinecap="round" strokeLinejoin="round" /></svg><div className="chart-axis"><span>{formatDateLabel(points[0].date)}</span><span>{formatDateLabel(points[points.length - 1].date)}</span></div></div>;
}

function ProviderBreakdown({ summary }: { summary: DashboardSummary }) {
  const colors = ["#24b49b", "#5578f2", "#eea84c"];
  const gradient = summary.providers.reduce((result, provider, index) => {
    const start = summary.providers.slice(0, index).reduce((sum, item) => sum + Number(item.percentage), 0);
    return `${result}${index ? ", " : ""}${colors[index % colors.length]} ${start}% ${start + Number(provider.percentage)}%`;
  }, "");
  return <div className="provider-layout"><div className="donut" style={{ background: gradient ? `conic-gradient(${gradient})` : "var(--surface-muted)" }}><div className="donut-hole"><strong>{summary.providers.length}</strong><span>providers</span></div></div><div className="provider-list">{summary.providers.length ? summary.providers.map((provider, index) => <div className="provider-row" key={provider.provider}><span className="legend-dot" style={{ background: colors[index % colors.length] }} /><span>{titleCaseProvider(provider.provider)}</span><strong>{formatPercent(provider.percentage)}</strong><small>{formatMoney(provider.cost, summary.overview.currency)}</small></div>) : <EmptyState message="No cost data available for this period." />}</div></div>;
}

function DeterministicInsight({ insight, currency }: { insight: CostInsight; currency: string }) {
  return (
    <article className={`insight-card ${insight.severity}`}>
      <div className="insight-icon">{insight.type === "cost_decrease" ? "↓" : "↑"}</div>
      <div className="insight-content">
        <div className="insight-meta">
          <span className={`severity ${insight.severity}`}>{insight.severity}</span>
          <span>Cost insight</span>
        </div>
        <h4>{insight.title}</h4>
        <p>{insight.description}</p>
        {(insight.provider || insight.service) && (
          <small>
            {insight.provider ? titleCaseProvider(insight.provider) : ""}
            {insight.service ? ` · ${insight.service}` : ""} · Impact {formatMoney(insight.impact, insight.currency || currency)}
          </small>
        )}
      </div>
    </article>
  );
}

function AIExplanation({ insight }: { insight: AIInsight }) {
  return (
    <article className={`insight-card ai-explanation ${insight.severity}`}>
      <div className="insight-icon">AI</div>
      <div className="insight-content">
        <div className="insight-meta">
          <span className={`severity ${insight.severity}`}>{insight.severity}</span>
          <span>Why this matters</span>
        </div>
        <h4>{insight.title}</h4>
        <p>{insight.summary}</p>
        <p>{insight.likely_cause}</p>
        <p>
          <strong>Recommended action:</strong> {insight.recommended_action}
        </p>
      </div>
    </article>
  );
}

function Insights({
  payload,
  currency,
  loading,
  error,
}: {
  payload: DashboardInsights | null;
  currency: string;
  loading: boolean;
  error: string;
}) {
  const insights = payload?.insights ?? [];
  const notice = payload ? aiExplanationNotice(payload.ai_status, payload.ai_message) : null;
  if (!loading && !insights.length && !payload?.ai_insights.length) {
    return <EmptyState message="No significant cost insights for this period." />;
  }
  return (
    <div className="insight-list">
      {insights.map((insight, index) => (
        <DeterministicInsight insight={insight} currency={currency} key={`${insight.type}-${index}`} />
      ))}
      {loading ? <div className="ai-status">AI insight loading</div> : null}
      {!loading && payload?.ai_insights.map((insight, index) => <AIExplanation insight={insight} key={`${insight.service}-${index}`} />)}
      {!loading && (error || notice) ? <div className="ai-status">{error || notice}</div> : null}
    </div>
  );
}
export default function Dashboard() {
  const [activeTab, setActiveTab] = useState<"dashboard" | "explorer">("dashboard");
  const [preset, setPreset] = useState<DatePreset>("30d");
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [insights, setInsights] = useState<DashboardInsights | null>(null);
  const [error, setError] = useState("");
  const [insightsError, setInsightsError] = useState("");
  const [loading, setLoading] = useState(true);
  const [insightsLoading, setInsightsLoading] = useState(true);
  const requestId = useRef(0);
  const range = useMemo(() => getDateRange(preset), [preset]);

  const loadDashboard = useCallback(async () => {
    const currentRequest = ++requestId.current;
    setLoading(true);
    setInsightsLoading(true);
    setError("");
    setInsightsError("");
    try {
      const nextSummary = await getDashboardSummary(range);
      if (currentRequest !== requestId.current) return;
      setSummary(nextSummary);
      setLoading(false);
      try {
        const deterministic = await getDashboardInsights(range, false);
        if (currentRequest !== requestId.current) return;
        setInsights(deterministic);
        const explained = await getDashboardInsights(range, true);
        if (currentRequest !== requestId.current) return;
        setInsights(explained);
      } catch {
        if (currentRequest !== requestId.current) return;
        setInsightsError("Cost insight available. AI explanation temporarily unavailable.");
      }
    } catch (exception) {
      if (currentRequest !== requestId.current) return;
      setError(exception instanceof ApiError && exception.status === 401 ? "Your session has expired. Please sign in again." : "Unable to load cost data. Please try again.");
    } finally {
      if (currentRequest === requestId.current) {
        setLoading(false);
        setInsightsLoading(false);
      }
    }
  }, [range]);

  useEffect(() => { void loadDashboard(); }, [loadDashboard]);

  return (
    <Shell activeTab={activeTab} onTabChange={setActiveTab}>
      <div className="view-tabs">
        <button
          type="button"
          className={`view-tab ${activeTab === "dashboard" ? "active" : ""}`}
          onClick={() => setActiveTab("dashboard")}
        >
          Overview Dashboard
        </button>
        <button
          type="button"
          className={`view-tab ${activeTab === "explorer" ? "active" : ""}`}
          onClick={() => setActiveTab("explorer")}
        >
          Cost Explorer & Drill-Down
        </button>
      </div>

      {activeTab === "explorer" ? (
        <CostExplorer />
      ) : (
        <>
          <section className="dashboard-header" id="dashboard">
            <div>
              <p className="eyebrow">Multi-cloud visibility</p>
              <h1>Good morning, here&apos;s the spend picture.</h1>
              <p className="muted">Track the signals that matter across your cloud estate.</p>
            </div>
            <div className="date-control" aria-label="Dashboard date range">
              {(["7d", "30d", "month"] as DatePreset[]).map((option) => (
                <button
                  key={option}
                  className={preset === option ? "selected" : ""}
                  onClick={() => setPreset(option)}
                >
                  {option === "7d" ? "Last 7 days" : option === "30d" ? "Last 30 days" : "Current month"}
                </button>
              ))}
            </div>
          </section>

          {error ? (
            <div className="error-banner" role="alert">
              <strong>Unable to load cost data.</strong>
              <span>{error}</span>
              <button className="ghost-button" onClick={() => void loadDashboard()}>
                Try again
              </button>
            </div>
          ) : loading ? (
            <LoadingDashboard />
          ) : !summary ? (
            <EmptyState message="No cost data available for this period." />
          ) : (
            <section className="dashboard-grid">
              <article className="metric-card primary">
                <span className="card-label">Total cloud spend</span>
                <strong className="metric-value">{formatMoney(summary.overview.total_cost, summary.overview.currency)}</strong>
                <span className={`change ${Number(summary.overview.absolute_change) >= 0 ? "up" : "down"}`}>
                  {Number(summary.overview.absolute_change) >= 0 ? "↑" : "↓"} {formatPercent(summary.overview.percentage_change)} <small>vs previous period</small>
                </span>
                <span className="period">{summary.overview.period_start} → {summary.overview.period_end}</span>
              </article>
              <article className="metric-card">
                <span className="card-label">Previous period</span>
                <strong className="metric-value compact">{formatMoney(summary.overview.previous_period_cost, summary.overview.currency)}</strong>
                <span className="metric-note">Baseline for comparison</span>
              </article>
              <article className="panel provider-panel">
                <div className="panel-heading">
                  <div>
                    <span className="card-label">Provider distribution</span>
                    <h3>Where spend is landing</h3>
                  </div>
                </div>
                <ProviderBreakdown summary={summary} />
              </article>
              <article className="panel trend-panel">
                <div className="panel-heading">
                  <div>
                    <span className="card-label">Daily trend</span>
                    <h3>Cloud spend over time</h3>
                  </div>
                  <span className="currency-badge">{summary.overview.currency}</span>
                </div>
                <TrendChart points={summary.trend} currency={summary.overview.currency} />
              </article>
              <article className="panel services-panel">
                <div className="panel-heading">
                  <div>
                    <span className="card-label">Top services</span>
                    <h3>Highest-cost services</h3>
                  </div>
                </div>
                {summary.services.length ? (
                  <div className="service-list">
                    {summary.services.slice(0, 5).map((service) => (
                      <div className="service-row" key={`${service.provider}-${service.service_name}`}>
                        <div>
                          <strong>{service.service_name}</strong>
                          <span>{titleCaseProvider(service.provider)} · {formatPercent(service.percentage)} of total</span>
                        </div>
                        <strong>{formatMoney(service.cost, summary.overview.currency)}</strong>
                      </div>
                    ))}
                  </div>
                ) : (
                  <EmptyState message="No cost data available for this period." />
                )}
              </article>
              <article className="panel insights-panel">
                <div className="panel-heading">
                  <div>
                    <span className="card-label">Cost Insights</span>
                    <h3>Signals worth your attention</h3>
                  </div>
                  <span className="insight-badge">{insights?.ai_status === "ready" ? "Measured + AI" : "Rule-based"}</span>
                </div>
                <Insights payload={insights} currency={summary.overview.currency} loading={insightsLoading} error={insightsError} />
              </article>
            </section>
          )}
        </>
      )}
    </Shell>
  );
}
