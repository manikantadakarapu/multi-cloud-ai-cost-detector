"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { ApiError, getForecast } from "../lib/api/client";
import { formatDateLabel, formatMoney, formatPercent } from "../lib/dates";
import type { ForecastResponse } from "../lib/types";

function EmptyState({ message }: { message: string }) {
  return <div className="empty-state">{message}</div>;
}

function ForecastChart({ data }: { data: ForecastResponse }) {
  const result = data.forecasts[0];
  const forecastPoints = result?.daily_forecast || [];
  const historicalPoints = result?.historical_daily || [];
  if (!result || !forecastPoints.length) return <EmptyState message="No forecast chart is available." />;
  const max = Math.max(...forecastPoints.map((point) => Number(point.upper_bound)), ...historicalPoints.map((point) => Number(point.cost)), 1);
  const width = 760;
  const height = 220;
  const path = (field: "forecast_cost" | "lower_bound" | "upper_bound") => forecastPoints.map((point, index) => {
    const x = forecastPoints.length === 1 ? width / 2 : (index / (forecastPoints.length - 1)) * width;
    const y = height - (Number(point[field]) / max) * (height - 24) - 12;
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(" ");
  const actualPath = historicalPoints.map((point, index) => {
    const x = historicalPoints.length === 1 ? 0 : (index / (historicalPoints.length + forecastPoints.length - 1)) * width;
    const y = height - (Number(point.cost) / max) * (height - 24) - 12;
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(" ");
  const forecastPath = path("forecast_cost");
  const offset = historicalPoints.length && forecastPoints.length ? ((historicalPoints.length - 1) / (historicalPoints.length + forecastPoints.length - 1)) * width : 0;
  const shifted = forecastPath.split(" ").map((point) => { const [x, y] = point.split(","); return `${(Number(x) * (forecastPoints.length - 1) / Math.max(forecastPoints.length - 1, 1) + offset).toFixed(1)},${y}`; }).join(" ");
  return <div className="trend-chart"><div className="chart-labels"><span>{formatMoney(max, result.currency)}</span><span>$0.00</span></div><svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Historical actual and deterministic cloud cost forecast" preserveAspectRatio="none"><polyline points={actualPath} fill="none" stroke="#24b49b" strokeWidth="4" strokeLinecap="round" strokeLinejoin="round" /><polyline points={shifted} fill="none" stroke="#b9d9d2" strokeWidth="18" strokeLinecap="round" strokeLinejoin="round" /><polyline points={shifted} fill="none" stroke="#5578f2" strokeWidth="4" strokeLinecap="round" strokeLinejoin="round" /></svg><div className="chart-axis"><span>{formatDateLabel(historicalPoints[0]?.date || forecastPoints[0].date)}</span><span>{formatDateLabel(forecastPoints[forecastPoints.length - 1].date)}</span></div><p className="chart-legend"><span className="legend-line historical" /> Historical actual <span className="legend-line actual" /> Forecast <span className="legend-line range" /> Confidence range</p></div>;
}

export default function Forecast({ range, onExplore }: { range: { start_date: string; end_date: string }; onExplore: (filters: { provider?: string; service?: string; account_id?: string; region?: string }) => void }) {
  const [horizon, setHorizon] = useState(7);
  const [data, setData] = useState<ForecastResponse | null>(null);
  const [providerData, setProviderData] = useState<ForecastResponse | null>(null);
  const [serviceData, setServiceData] = useState<ForecastResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const params = { ...range, horizon_days: horizon };
      const [total, providers, services] = await Promise.all([
        getForecast(params),
        getForecast({ ...params, dimension: "provider" }),
        getForecast({ ...params, dimension: "service" }),
      ]);
      setData(total);
      setProviderData(providers);
      setServiceData(services);
    } catch (err) {
      setError(err instanceof ApiError && err.status === 401 ? "Your session has expired. Please sign in again." : "Unable to load the cost forecast.");
    } finally {
      setLoading(false);
    }
  }, [range, horizon]);
  useEffect(() => { void load(); }, [load]);
  const total = useMemo(() => data?.forecasts.find((item) => item.dimension === "total") || data?.forecasts[0], [data]);
  return <section className="panel forecast-panel" aria-label="Cost Forecast"><div className="panel-heading"><div><span className="card-label">Deterministic planning</span><h3>Cost Forecast</h3><p className="muted">A robust statistical projection from normalized historical spend.</p></div><div className="date-control" aria-label="Forecast horizon">{[7, 14, 30].map((value) => <button key={value} className={horizon === value ? "selected" : ""} onClick={() => setHorizon(value)}>{value} days</button>)}</div></div>{error ? <div className="error-banner" role="alert">{error}<button className="ghost-button" onClick={() => void load()}>Try again</button></div> : loading ? <div className="dashboard-grid" aria-label="Loading forecast"><div className="skeleton" /><div className="skeleton wide" /></div> : !data || data.status !== "ready" ? <EmptyState message={data?.message || "Not enough reliable history to produce a forecast."} /> : <><div className="forecast-summary"><div><span>Current comparable spend</span><strong>{formatMoney(data.summary.current_spend, total?.currency || "USD")}</strong></div><div><span>Projected spend</span><strong>{formatMoney(data.summary.projected_spend, total?.currency || "USD")}</strong></div><div><span>Projected change</span><strong>{data.summary.projected_change_percentage === null ? "—" : formatPercent(data.summary.projected_change_percentage)}</strong></div><div><span>Confidence</span><strong>{data.summary.confidence || "unknown"}</strong></div></div><ForecastChart data={data} /><div className="forecast-breakdown"><div><h4>By provider</h4>{providerData?.forecasts.map((item) => <button className="forecast-row" key={item.forecast_id} onClick={() => onExplore({ provider: item.provider || item.dimension_value })}><span>{item.dimension_value}</span><strong>{formatMoney(item.projected_cost, item.currency)}</strong></button>)}</div><div><h4>By service</h4>{serviceData?.forecasts.map((item) => <button className="forecast-row" key={item.forecast_id} onClick={() => onExplore({ service: item.service || item.dimension_value })}><span>{item.dimension_value}</span><strong>{formatMoney(item.projected_cost, item.currency)}</strong></button>)}</div></div><p className="forecast-note">{data.data_quality.excluded_anomaly_dates.length ? `${data.data_quality.excluded_anomaly_dates.length} anomalous day(s) were excluded from the baseline.` : "No extreme historical observations were excluded."} Data points used: {data.summary.data_points_used}.</p></>}</section>;
}
