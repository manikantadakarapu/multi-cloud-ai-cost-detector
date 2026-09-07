"use client";

import { useEffect, useState } from "react";
import { ApiError, createBudget, deleteBudget, getBudgetEvaluation, getBudgets, updateBudget } from "../lib/api/client";
import { formatMoney, formatPercent } from "../lib/dates";
import type { Budget, BudgetEvaluation, BudgetScope, BudgetStatus } from "../lib/types";

type Draft = {
  name: string; scope: BudgetScope; provider: string; account_id: string;
  service: string; region: string; amount: string; currency: string;
  warning_threshold: string; critical_threshold: string; enabled: boolean;
};

const emptyDraft: Draft = {
  name: "", scope: "total", provider: "", account_id: "", service: "", region: "",
  amount: "", currency: "USD", warning_threshold: "80", critical_threshold: "90", enabled: true,
};

function statusLabel(status: BudgetStatus) {
  return status === "unavailable" ? "Unavailable" : status[0].toUpperCase() + status.slice(1);
}

export default function Budgets() {
  const [budgets, setBudgets] = useState<Budget[]>([]);
  const [evaluations, setEvaluations] = useState<Record<string, BudgetEvaluation>>({});
  const [draft, setDraft] = useState<Draft>(emptyDraft);
  const [editing, setEditing] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  async function load() {
    setLoading(true); setError("");
    try {
      const next = await getBudgets();
      setBudgets(next);
      const results = await Promise.all(next.map(async (budget) => {
        try { return [budget.id, await getBudgetEvaluation(budget.id)] as const; }
        catch { return null; }
      }));
      setEvaluations(Object.fromEntries(results.filter((item): item is readonly [string, BudgetEvaluation] => item !== null)));
    } catch (exception) {
      setError(exception instanceof ApiError && exception.status === 401 ? "Your session has expired. Please sign in again." : "Unable to load budgets.");
    } finally { setLoading(false); }
  }

  useEffect(() => { void load(); }, []);

  function setField<K extends keyof Draft>(field: K, value: Draft[K]) {
    setDraft((current) => ({ ...current, [field]: value }));
  }

  async function save(event: React.FormEvent) {
    event.preventDefault(); setSaving(true); setError("");
    const payload = {
      name: draft.name, scope: draft.scope, provider: draft.provider || null,
      account_id: draft.account_id || null, service: draft.service || null, region: draft.region || null,
      period: "monthly" as const, amount: draft.amount, currency: draft.currency,
      warning_threshold: draft.warning_threshold, critical_threshold: draft.critical_threshold, enabled: draft.enabled,
    };
    try {
      if (editing) await updateBudget(editing, payload);
      else await createBudget(payload);
      setDraft(emptyDraft); setEditing(null); await load();
    } catch (exception) { setError(exception instanceof ApiError ? exception.message : "Unable to save budget."); }
    finally { setSaving(false); }
  }

  async function toggle(budget: Budget) {
    try { await updateBudget(budget.id, { enabled: !budget.enabled }); await load(); }
    catch { setError("Unable to update budget state."); }
  }

  async function remove(budget: Budget) {
    if (!window.confirm(`Delete budget '${budget.name}'?`)) return;
    try { await deleteBudget(budget.id); await load(); }
    catch { setError("Unable to delete budget."); }
  }

  function beginEdit(budget: Budget) {
    setEditing(budget.id);
    setDraft({ name: budget.name, scope: budget.scope, provider: budget.provider || "", account_id: budget.account_id || "", service: budget.service || "", region: budget.region || "", amount: budget.amount, currency: budget.currency, warning_threshold: budget.warning_threshold, critical_threshold: budget.critical_threshold, enabled: budget.enabled });
  }

  return <>
    <section className="dashboard-header"><div><p className="eyebrow">Deterministic spend controls</p><h1>Cost Budgets</h1><p className="muted">Compare verified spend with monthly budgets and forecast guardrails.</p></div><button className="ghost-button" onClick={() => void load()}>Refresh evaluations</button></section>
    {error ? <div className="error-banner" role="alert"><span>{error}</span><button className="ghost-button" onClick={() => void load()}>Try again</button></div> : null}
    <section className="budgets-layout">
      <div className="panel"><div className="panel-heading"><div><span className="card-label">Budget list</span><h3>Your monthly guardrails</h3></div><span className="currency-badge">{budgets.length}</span></div>{loading ? <div className="empty-state">Loading budgets…</div> : budgets.length ? <div className="budget-list">{budgets.map((budget) => { const evaluation = evaluations[budget.id]; const utilization = evaluation?.actual_utilization ? Number(evaluation.actual_utilization) : 0; return <article className="budget-card" key={budget.id}><div className="budget-card-header"><div><strong>{budget.name}</strong><small>{budget.provider || "All providers"} · {budget.scope} · {budget.period}</small></div><span className={`badge ${evaluation?.actual_status || "unavailable"}`}>{evaluation ? `${statusLabel(evaluation.actual_status)} · ${evaluation.evaluation_period}` : "Evaluation unavailable"}</span></div>{evaluation ? <><div className="budget-amounts"><strong>{formatMoney(evaluation.actual_spend, budget.currency)} / {formatMoney(budget.amount, budget.currency)}</strong><span>{formatPercent(evaluation.actual_utilization)} used</span></div><div className="budget-progress"><span style={{ width: `${Math.min(utilization, 100)}%` }} /></div><div className="budget-details"><span>Remaining {formatMoney(evaluation.actual_remaining, budget.currency)}</span><span>Forecast {evaluation.forecast_spend === null ? "Unavailable" : formatMoney(evaluation.forecast_spend, budget.currency)}</span><span className={`status-text ${evaluation.forecast_status}`}>Forecast {statusLabel(evaluation.forecast_status)}</span></div><p className="budget-reason">{evaluation.reason}</p></> : <div className="empty-state">Evaluation unavailable.</div>}<div className="alert-row-actions"><button className="ghost-button" onClick={() => beginEdit(budget)}>Edit</button><button className="ghost-button" onClick={() => void toggle(budget)}>{budget.enabled ? "Disable" : "Enable"}</button><button className="ghost-button danger-button" onClick={() => void remove(budget)}>Delete</button></div></article>; })}</div> : <div className="empty-state">No budgets configured yet.</div>}</div>
      <form className="panel budget-form" onSubmit={(event) => void save(event)}><div className="panel-heading"><div><span className="card-label">{editing ? "Edit budget" : "Create budget"}</span><h3>{editing ? "Update guardrail" : "New monthly budget"}</h3></div>{editing ? <button type="button" className="ghost-button" onClick={() => { setEditing(null); setDraft(emptyDraft); }}>Cancel</button> : null}</div><label>Budget name<input value={draft.name} onChange={(event) => setField("name", event.target.value)} required maxLength={160} /></label><label>Scope<select value={draft.scope} onChange={(event) => setField("scope", event.target.value as BudgetScope)}><option value="total">All spend</option><option value="provider">Provider</option><option value="account">Account/project</option><option value="service">Service</option><option value="region">Region</option></select></label><label>Provider<select value={draft.provider} onChange={(event) => setField("provider", event.target.value)}><option value="">All providers</option><option value="aws">AWS</option><option value="azure">Azure</option><option value="gcp">GCP</option></select></label><label>Account/project<input value={draft.account_id} onChange={(event) => setField("account_id", event.target.value)} placeholder="Optional filter" /></label><label>Service<input value={draft.service} onChange={(event) => setField("service", event.target.value)} placeholder="Optional filter" /></label><label>Region<input value={draft.region} onChange={(event) => setField("region", event.target.value)} placeholder="Optional filter" /></label><label>Monthly amount<input type="number" min="0.01" step="0.01" value={draft.amount} onChange={(event) => setField("amount", event.target.value)} required /></label><label>Currency<input value={draft.currency} onChange={(event) => setField("currency", event.target.value.toUpperCase())} maxLength={3} required /></label><div className="budget-thresholds"><label>Warning %<input type="number" min="0" max="100" step="0.01" value={draft.warning_threshold} onChange={(event) => setField("warning_threshold", event.target.value)} required /></label><label>Critical %<input type="number" min="0.01" max="100" step="0.01" value={draft.critical_threshold} onChange={(event) => setField("critical_threshold", event.target.value)} required /></label></div><label className="checkbox-label"><input type="checkbox" checked={draft.enabled} onChange={(event) => setField("enabled", event.target.checked)} /> Enabled</label><button className="primary-button" type="submit" disabled={saving}>{saving ? "Saving…" : editing ? "Save changes" : "Create budget"}</button></form>
    </section>
  </>;
}
