"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { ApiError, createAlert, deleteAlert, evaluateAlerts, getAlerts, updateAlert } from "../lib/api/client";
import { getDateRange } from "../lib/dates";
import type { Alert, AlertSeverity, AlertType } from "../lib/types";

type Draft = {
  name: string;
  alert_type: AlertType;
  provider: string;
  account_id: string;
  service: string;
  region: string;
  threshold: string;
  percentage: string;
  severity: AlertSeverity;
  cooldown_minutes: string;
  enabled: boolean;
};

const emptyDraft: Draft = {
  name: "",
  alert_type: "cost_threshold",
  provider: "",
  account_id: "",
  service: "",
  region: "",
  threshold: "",
  percentage: "",
  severity: "medium",
  cooldown_minutes: "360",
  enabled: true,
};

function toDraft(alert: Alert): Draft {
  return {
    name: alert.name,
    alert_type: alert.alert_type,
    provider: alert.provider || "",
    account_id: alert.account_id || "",
    service: alert.service || "",
    region: alert.region || "",
    threshold: alert.threshold || "",
    percentage: alert.percentage || "",
    severity: alert.severity,
    cooldown_minutes: String(alert.cooldown_minutes),
    enabled: alert.enabled,
  };
}

export default function Alerts() {
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [draft, setDraft] = useState<Draft>(emptyDraft);
  const [editing, setEditing] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [evaluation, setEvaluation] = useState("");
  const range = useMemo(() => getDateRange("30d"), []);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      setAlerts(await getAlerts());
    } catch (exception) {
      setError(exception instanceof ApiError && exception.status === 401 ? "Your session has expired. Please sign in again." : "Unable to load alerts.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  function setField<K extends keyof Draft>(key: K, value: Draft[K]) {
    setDraft((current) => ({ ...current, [key]: value }));
  }

  async function save(event: React.FormEvent) {
    event.preventDefault();
    setSaving(true);
    setError("");
    const payload = {
      ...draft,
      provider: draft.provider || undefined,
      account_id: draft.account_id || undefined,
      service: draft.service || undefined,
      region: draft.region || undefined,
      threshold: draft.threshold || undefined,
      percentage: draft.percentage || undefined,
      cooldown_minutes: Number(draft.cooldown_minutes),
    };
    try {
      if (editing) await updateAlert(editing, payload);
      else await createAlert(payload as Parameters<typeof createAlert>[0]);
      setDraft(emptyDraft);
      setEditing(null);
      await load();
    } catch (exception) {
      setError(exception instanceof ApiError ? exception.message : "Unable to save alert.");
    } finally {
      setSaving(false);
    }
  }

  async function toggle(alert: Alert) {
    try {
      await updateAlert(alert.id, { enabled: !alert.enabled });
      await load();
    } catch { setError("Unable to update alert state."); }
  }

  async function remove(alert: Alert) {
    if (!window.confirm(`Delete alert '${alert.name}'?`)) return;
    try {
      await deleteAlert(alert.id);
      await load();
    } catch { setError("Unable to delete alert."); }
  }

  async function evaluate() {
    setEvaluation("Evaluating enabled alerts…");
    try {
      const results = await evaluateAlerts(range);
      const triggered = results.filter((item) => item.status === "triggered").length;
      setEvaluation(`${triggered} alert${triggered === 1 ? "" : "s"} triggered; evaluation completed.`);
      await load();
    } catch { setEvaluation("Alert evaluation failed. Review the backend logs and configuration."); }
  }

  return (
    <>
      <section className="dashboard-header"><div><p className="eyebrow">Deterministic spend monitoring</p><h1>Cost Alerts</h1><p className="muted">Receive email notifications when configured cost conditions are met.</p></div><button className="ghost-button" onClick={() => void evaluate()}>Evaluate now</button></section>
      {error ? <div className="error-banner" role="alert"><span>{error}</span><button className="ghost-button" onClick={() => void load()}>Try again</button></div> : null}
      {evaluation ? <div className="ai-status">{evaluation}</div> : null}
      <section className="alerts-layout">
        <div className="panel"><div className="panel-heading"><div><span className="card-label">Alert list</span><h3>Your configured alerts</h3></div><span className="currency-badge">{alerts.length}</span></div>{loading ? <div className="empty-state">Loading alerts…</div> : alerts.length ? <div className="service-list">{alerts.map((alert) => <div className="alert-row" key={alert.id}><div><strong>{alert.name}</strong><small>{alert.alert_type.replaceAll("_", " ")} · {alert.provider || "all providers"} · {alert.service || "all services"}</small><small>{alert.last_triggered_at ? `Last triggered ${alert.last_triggered_at}` : "Not triggered yet"}</small></div><div className="alert-row-actions"><span className={`badge ${alert.severity}`}>{alert.severity}</span><button className="ghost-button" onClick={() => { setEditing(alert.id); setDraft(toDraft(alert)); }}>Edit</button><button className="ghost-button" onClick={() => void toggle(alert)}>{alert.enabled ? "Disable" : "Enable"}</button><button className="ghost-button danger-button" onClick={() => void remove(alert)}>Delete</button></div></div>)}</div> : <div className="empty-state">No alerts configured yet.</div>}</div>
        <form className="panel alert-form" onSubmit={(event) => void save(event)}><div className="panel-heading"><div><span className="card-label">{editing ? "Edit alert" : "Create alert"}</span><h3>{editing ? "Update condition" : "New cost alert"}</h3></div>{editing ? <button type="button" className="ghost-button" onClick={() => { setEditing(null); setDraft(emptyDraft); }}>Cancel</button> : null}</div><label>Alert name<input value={draft.name} onChange={(event) => setField("name", event.target.value)} required maxLength={160} /></label><label>Alert type<select value={draft.alert_type} onChange={(event) => setField("alert_type", event.target.value as AlertType)}><option value="cost_threshold">Daily cost threshold</option><option value="cost_increase">Cost increase percentage</option><option value="anomaly">Deterministic anomaly</option><option value="forecast_threshold">Forecast threshold</option></select></label><label>Provider<select value={draft.provider} onChange={(event) => setField("provider", event.target.value)}><option value="">All providers</option><option value="aws">AWS</option><option value="azure">Azure</option><option value="gcp">GCP</option></select></label>{draft.alert_type === "cost_increase" ? <label>Increase percentage<input type="number" min="0.01" step="0.01" value={draft.percentage} onChange={(event) => setField("percentage", event.target.value)} required /></label> : null}{draft.alert_type !== "anomaly" && draft.alert_type !== "cost_increase" ? <label>Threshold<input type="number" min="0.01" step="0.01" value={draft.threshold} onChange={(event) => setField("threshold", event.target.value)} required /></label> : null}<label>Service scope<input value={draft.service} onChange={(event) => setField("service", event.target.value)} placeholder="Optional service filter" /></label><label>Account/project scope<input value={draft.account_id} onChange={(event) => setField("account_id", event.target.value)} placeholder="Optional account filter" /></label><label>Region scope<input value={draft.region} onChange={(event) => setField("region", event.target.value)} placeholder="Optional region filter" /></label><label>Severity<select value={draft.severity} onChange={(event) => setField("severity", event.target.value as AlertSeverity)}><option value="low">Low</option><option value="medium">Medium</option><option value="high">High</option><option value="critical">Critical</option></select></label><label>Cooldown minutes<input type="number" min="0" max="43200" value={draft.cooldown_minutes} onChange={(event) => setField("cooldown_minutes", event.target.value)} required /></label><label className="checkbox-label"><input type="checkbox" checked={draft.enabled} onChange={(event) => setField("enabled", event.target.checked)} /> Enabled</label><button className="primary-button" type="submit" disabled={saving}>{saving ? "Saving…" : editing ? "Save changes" : "Create alert"}</button></form>
      </section>
    </>
  );
}
