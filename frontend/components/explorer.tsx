"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ApiError, getExplorerData } from "../lib/api/client";
import { formatDateLabel, formatMoney, formatPercent, getDateRange, titleCaseProvider } from "../lib/dates";
import type { CostRecord, DatePreset, DimensionTotal, ExplorerResponse } from "../lib/types";

function EmptyState({ message }: { message: string }) {
  return <div className="empty-state">{message}</div>;
}

function LoadingExplorer() {
  return (
    <div className="dashboard-grid" aria-label="Loading Cost Explorer">
      <div className="skeleton hero" />
      <div className="skeleton" />
      <div className="skeleton wide" />
      <div className="skeleton tall" />
      <div className="skeleton tall" />
    </div>
  );
}

function DimensionBarList({
  items,
  currency,
  onSelect,
  activeKey,
}: {
  items: DimensionTotal[];
  currency: string;
  onSelect?: (key: string) => void;
  activeKey?: string | null;
}) {
  if (!items.length) {
    return <EmptyState message="No breakdown data available." />;
  }
  return (
    <div className="service-list">
      {items.map((item) => (
        <div
          className={`clickable-row ${activeKey === item.key ? "selected-row" : ""}`}
          key={item.key}
          onClick={() => onSelect?.(item.key)}
          role="button"
          tabIndex={0}
        >
          <div style={{ display: "flex", justifyContent: "space-between", fontSize: "12px", marginBottom: "4px" }}>
            <strong>{item.label}</strong>
            <span>
              {formatMoney(item.cost, currency)} <small>({formatPercent(item.percentage)})</small>
            </span>
          </div>
          <div className="bar-track">
            <div className="bar-fill" style={{ width: `${Math.min(Number(item.percentage) || 0, 100)}%` }} />
          </div>
        </div>
      ))}
    </div>
  );
}

function ExplorerTrendChart({
  points,
  currency,
}: {
  points: ExplorerResponse["dimension_totals"]["by_date"];
  currency: string;
}) {
  if (!points.length) return <EmptyState message="No cost data available for this period." />;
  const values = points.map((point) => Number(point.cost));
  const max = Math.max(...values, 1);
  const min = Math.min(...values, 0);
  const width = 760;
  const height = 220;
  const pointsPath = points
    .map((point, index) => {
      const x = points.length === 1 ? width / 2 : (index / (points.length - 1)) * width;
      const y = height - ((Number(point.cost) - min) / Math.max(max - min, 1)) * (height - 28) - 14;
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");

  return (
    <div className="trend-chart">
      <div className="chart-labels">
        <span>{formatMoney(max, currency)}</span>
        <span>{formatMoney(min, currency)}</span>
      </div>
      <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Daily filtered cloud spend trend" preserveAspectRatio="none">
        <defs>
          <linearGradient id="explorer-trend-fill" x1="0" x2="0" y1="0" y2="1">
            <stop offset="0%" stopColor="#24b49b" stopOpacity=".25" />
            <stop offset="100%" stopColor="#24b49b" stopOpacity="0" />
          </linearGradient>
        </defs>
        <polyline points={`0,${height} ${pointsPath} ${width},${height}`} fill="url(#explorer-trend-fill)" stroke="none" />
        <polyline points={pointsPath} fill="none" stroke="#24b49b" strokeWidth="4" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
      <div className="chart-axis">
        <span>{formatDateLabel(points[0].date)}</span>
        <span>{formatDateLabel(points[points.length - 1].date)}</span>
      </div>
    </div>
  );
}

export default function CostExplorer({ initialFilters }: { initialFilters?: { provider?: string; service?: string; region?: string; account_id?: string } }) {
  const [preset, setPreset] = useState<DatePreset>("30d");
  const [provider, setProvider] = useState<string>(initialFilters?.provider || "");
  const [service, setService] = useState<string>(initialFilters?.service || "");
  const [region, setRegion] = useState<string>(initialFilters?.region || "");
  const [accountId, setAccountId] = useState<string>(initialFilters?.account_id || "");
  const [offset, setOffset] = useState<number>(0);
  const limit = 25;

  const [data, setData] = useState<ExplorerResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const requestId = useRef(0);
  const range = useMemo(() => getDateRange(preset), [preset]);

  const loadData = useCallback(async () => {
    const currentRequest = ++requestId.current;
    setLoading(true);
    setError("");
    try {
      const res = await getExplorerData({
        start_date: range.start_date,
        end_date: range.end_date,
        provider: provider || undefined,
        service: service || undefined,
        region: region || undefined,
        account_id: accountId || undefined,
        limit,
        offset,
      });
      if (currentRequest !== requestId.current) return;
      setData(res);
    } catch (err) {
      if (currentRequest !== requestId.current) return;
      setError(
        err instanceof ApiError && err.status === 401
          ? "Your session has expired. Please sign in again."
          : "Unable to load Cost Explorer data. Please try again."
      );
    } finally {
      if (currentRequest === requestId.current) {
        setLoading(false);
      }
    }
  }, [range, provider, service, region, accountId, offset]);

  useEffect(() => {
    void loadData();
  }, [loadData]);

  // Reset pagination offset when filters change
  const handleFilterChange = (setter: (v: string) => void, val: string) => {
    setter(val);
    setOffset(0);
  };

  const clearAllFilters = () => {
    setProvider("");
    setService("");
    setRegion("");
    setAccountId("");
    setOffset(0);
  };

  const hasActiveFilters = Boolean(provider || service || region || accountId);

  return (
    <div>
      <section className="dashboard-header" id="explorer">
        <div>
          <p className="eyebrow">Interactive Spend Investigation</p>
          <h1>Cost Explorer & Drill-Down</h1>
          <p className="muted">Filter, group, and slice your multi-cloud spend across providers, services, and regions.</p>
        </div>
        <div className="date-control" aria-label="Explorer date range">
          {(["7d", "30d", "month"] as DatePreset[]).map((option) => (
            <button
              key={option}
              className={preset === option ? "selected" : ""}
              onClick={() => {
                setPreset(option);
                setOffset(0);
              }}
            >
              {option === "7d" ? "Last 7 days" : option === "30d" ? "Last 30 days" : "Current month"}
            </button>
          ))}
        </div>
      </section>

      {/* Filter Toolbar */}
      <div className="filter-bar">
        <select
          className="filter-select"
          value={provider}
          onChange={(e) => handleFilterChange(setProvider, e.target.value)}
          aria-label="Filter by provider"
        >
          <option value="">All Providers</option>
          {data?.available_filters.providers.map((p) => (
            <option key={p} value={p}>
              {titleCaseProvider(p)}
            </option>
          ))}
        </select>

        <select
          className="filter-select"
          value={service}
          onChange={(e) => handleFilterChange(setService, e.target.value)}
          aria-label="Filter by service"
        >
          <option value="">All Services</option>
          {data?.available_filters.services.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>

        <select
          className="filter-select"
          value={region}
          onChange={(e) => handleFilterChange(setRegion, e.target.value)}
          aria-label="Filter by region"
        >
          <option value="">All Regions</option>
          {data?.available_filters.regions.map((r) => (
            <option key={r} value={r}>
              {r}
            </option>
          ))}
        </select>

        {data?.available_filters.accounts.length ? (
          <select
            className="filter-select"
            value={accountId}
            onChange={(e) => handleFilterChange(setAccountId, e.target.value)}
            aria-label="Filter by account"
          >
            <option value="">All Accounts</option>
            {data.available_filters.accounts.map((a) => (
              <option key={a} value={a}>
                {a}
              </option>
            ))}
          </select>
        ) : null}

        {hasActiveFilters && (
          <button className="ghost-button" onClick={clearAllFilters}>
            Clear Filters
          </button>
        )}
      </div>

      {/* Active Filter Pills */}
      {hasActiveFilters && (
        <div className="filter-pills-row">
          <span style={{ fontSize: "11px", color: "var(--ink-soft)", fontWeight: 700 }}>Active filters:</span>
          {provider && (
            <span className="filter-pill">
              Provider: {titleCaseProvider(provider)}
              <button onClick={() => handleFilterChange(setProvider, "")} aria-label="Remove provider filter">
                ✕
              </button>
            </span>
          )}
          {service && (
            <span className="filter-pill">
              Service: {service}
              <button onClick={() => handleFilterChange(setService, "")} aria-label="Remove service filter">
                ✕
              </button>
            </span>
          )}
          {region && (
            <span className="filter-pill">
              Region: {region}
              <button onClick={() => handleFilterChange(setRegion, "")} aria-label="Remove region filter">
                ✕
              </button>
            </span>
          )}
          {accountId && (
            <span className="filter-pill">
              Account: {accountId}
              <button onClick={() => handleFilterChange(setAccountId, "")} aria-label="Remove account filter">
                ✕
              </button>
            </span>
          )}
        </div>
      )}

      {error ? (
        <div className="error-banner" role="alert">
          <strong>Unable to load explorer data.</strong>
          <span>{error}</span>
          <button className="ghost-button" onClick={() => void loadData()}>
            Try again
          </button>
        </div>
      ) : loading ? (
        <LoadingExplorer />
      ) : !data ? (
        <EmptyState message="No cost records match the selected filters." />
      ) : (
        <>
          {/* Key Metrics */}
          <section className="dashboard-grid" style={{ marginBottom: "20px" }}>
            <article className="metric-card primary">
              <span className="card-label">Filtered Spend</span>
              <strong className="metric-value">{formatMoney(data.overview.total_cost, data.overview.currency)}</strong>
              <span className="period">
                {data.overview.start_date} → {data.overview.end_date}
              </span>
            </article>

            <article className="metric-card">
              <span className="card-label">Matching Records</span>
              <strong className="metric-value compact">{data.overview.record_count}</strong>
              <span className="metric-note">Line items in active period</span>
            </article>

            <article className="metric-card">
              <span className="card-label">Active Cloud Providers</span>
              <strong className="metric-value compact">{data.dimension_totals.by_provider.length}</strong>
              <span className="metric-note">Contributing to filtered spend</span>
            </article>

            <article className="metric-card">
              <span className="card-label">Unique Services</span>
              <strong className="metric-value compact">{data.dimension_totals.by_service.length}</strong>
              <span className="metric-note">Active line item services</span>
            </article>
          </section>

          {/* Breakdowns & Daily Trend Grid */}
          <section className="dashboard-grid">
            <article className="panel services-panel">
              <div className="panel-heading">
                <div>
                  <span className="card-label">By Cloud Provider</span>
                  <h3>Spend by Provider</h3>
                </div>
              </div>
              <DimensionBarList
                items={data.dimension_totals.by_provider}
                currency={data.overview.currency}
                onSelect={(key) => handleFilterChange(setProvider, provider === key ? "" : key)}
                activeKey={provider}
              />
            </article>

            <article className="panel services-panel">
              <div className="panel-heading">
                <div>
                  <span className="card-label">By Cloud Service</span>
                  <h3>Spend by Service</h3>
                </div>
              </div>
              <DimensionBarList
                items={data.dimension_totals.by_service.slice(0, 8)}
                currency={data.overview.currency}
                onSelect={(key) => handleFilterChange(setService, service === key ? "" : key)}
                activeKey={service}
              />
            </article>

            <article className="panel trend-panel">
              <div className="panel-heading">
                <div>
                  <span className="card-label">Daily Filtered Trend</span>
                  <h3>Spend Over Time</h3>
                </div>
                <span className="currency-badge">{data.overview.currency}</span>
              </div>
              <ExplorerTrendChart points={data.dimension_totals.by_date} currency={data.overview.currency} />
            </article>

            <article className="panel provider-panel">
              <div className="panel-heading">
                <div>
                  <span className="card-label">By Region</span>
                  <h3>Spend by Region</h3>
                </div>
              </div>
              <DimensionBarList
                items={data.dimension_totals.by_region.slice(0, 8)}
                currency={data.overview.currency}
                onSelect={(key) => handleFilterChange(setRegion, region === key ? "" : key)}
                activeKey={region}
              />
            </article>
          </section>

          {/* Line-item Records Table */}
          <section className="panel" style={{ marginTop: "20px" }}>
            <div className="panel-heading">
              <div>
                <span className="card-label">Normalized Line Items</span>
                <h3>Cost Line Items</h3>
              </div>
              <span className="currency-badge">
                Showing {data.records.length} of {data.total_records}
              </span>
            </div>

            {data.records.length ? (
              <div className="data-table-container">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Date</th>
                      <th>Provider</th>
                      <th>Account / Project</th>
                      <th>Service</th>
                      <th>Region</th>
                      <th style={{ textAlign: "right" }}>Cost</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.records.map((rec: CostRecord, idx: number) => (
                      <tr key={`${rec.provider}-${rec.service}-${rec.date}-${idx}`}>
                        <td>{rec.date}</td>
                        <td>
                          <span className={`badge ${rec.provider.toLowerCase()}`}>{titleCaseProvider(rec.provider)}</span>
                        </td>
                        <td>{rec.account_name || rec.account_id || "—"}</td>
                        <td>
                          <strong>{rec.service}</strong>
                        </td>
                        <td>{rec.region || "global"}</td>
                        <td style={{ textAlign: "right", fontWeight: 700 }}>{formatMoney(rec.cost, rec.currency)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>

                {/* Pagination */}
                <div className="pagination">
                  <button
                    className="ghost-button"
                    disabled={offset === 0}
                    onClick={() => setOffset(Math.max(0, offset - limit))}
                  >
                    ← Previous
                  </button>
                  <span>
                    Page {Math.floor(offset / limit) + 1} of {Math.ceil(data.total_records / limit) || 1}
                  </span>
                  <button
                    className="ghost-button"
                    disabled={offset + limit >= data.total_records}
                    onClick={() => setOffset(offset + limit)}
                  >
                    Next →
                  </button>
                </div>
              </div>
            ) : (
              <EmptyState message="No records found matching the active filters." />
            )}
          </section>
        </>
      )}
    </div>
  );
}
