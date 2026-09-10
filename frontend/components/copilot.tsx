"use client";

import { useState } from "react";
import { ApiError, queryCopilot } from "../lib/api/client";
import type { CopilotResponse } from "../lib/types";

const EXAMPLES = ["Why did my cloud cost increase this month?", "Which budgets are at risk?", "What are my biggest optimization opportunities?", "What anomalies should I investigate?", "What is my forecasted spend?"];

export default function Copilot() {
  const [question, setQuestion] = useState("");
  const [response, setResponse] = useState<CopilotResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function ask(value = question) {
    const next = value.trim();
    if (!next) return;
    setQuestion(next); setLoading(true); setError("");
    try { setResponse(await queryCopilot(next)); }
    catch (exception) { setResponse(null); setError(exception instanceof ApiError ? exception.message : "Unable to query FinOps Copilot."); }
    finally { setLoading(false); }
  }

  return <>
    <section className="dashboard-header copilot-header"><div><p className="eyebrow">Intelligence / verified answers</p><h1>FinOps Copilot</h1><p className="muted">A focused workspace for understanding spend, anomalies, forecasts, recommendations, and budgets.</p></div><div className="context-indicator"><span className="status-dot" /><div><strong>Connected context</strong><small>Current workspace data</small></div></div></section>
    <section className="copilot-layout">
      <div className="panel copilot-panel"><div className="panel-heading"><div><span className="card-label">Ask a FinOps question</span><h3>What would you like to understand?</h3></div><span className="currency-badge">Evidence only</span></div><form onSubmit={(event) => { event.preventDefault(); void ask(); }}><textarea aria-label="FinOps Copilot question" value={question} onChange={(event) => setQuestion(event.target.value)} placeholder="Ask about a verified cost signal..." maxLength={1000} rows={4} /><div className="composer-footer"><span className="field-help">Answers are grounded in data available to this workspace.</span><button className="primary-button" type="submit" disabled={loading || !question.trim()}>{loading ? "Reviewing data…" : "Ask Copilot"}</button></div></form><div className="copilot-examples"><span className="card-label">Suggested questions</span>{EXAMPLES.map((example) => <button type="button" className="suggestion-chip" key={example} onClick={() => { setQuestion(example); void ask(example); }}>{example}</button>)}</div></div>
      {error ? <div className="error-banner" role="alert"><strong>Copilot unavailable</strong><span>{error}</span><button className="ghost-button" onClick={() => void ask()}>Try again</button></div> : null}
      {response ? <section className="panel copilot-response" aria-label="FinOps Copilot response"><div className="response-status"><span className={`badge ${response.status}`}>{response.status === "ready" ? "Verified answer" : "Fallback answer"}</span><span className="copilot-confidence">Confidence: {response.confidence} · Intent: {response.intent}</span></div><h2>{response.answer}</h2><div className="copilot-columns"><div className="response-block"><h4>Key findings</h4>{response.key_findings.length ? <ul>{response.key_findings.map((item) => <li key={item}>{item}</li>)}</ul> : <p className="muted">No findings were returned for this question.</p>}</div><div className="response-block evidence-block"><h4>Evidence</h4>{response.evidence.length ? <ul>{response.evidence.map((item) => <li key={item}>{item}</li>)}</ul> : <p className="muted">See the referenced dashboard data for evidence.</p>}</div></div>{response.recommended_next_steps.length ? <div className="response-block"><h4>Suggested next steps</h4><ul>{response.recommended_next_steps.map((item) => <li key={item}>{item}</li>)}</ul></div> : null}{response.limitations.length ? <div className="response-limitations"><h4>Limitations</h4><ul>{response.limitations.map((item) => <li key={item}>{item}</li>)}</ul></div> : null}<p className="response-footnote">Generated from the current workspace context · {response.generated_at ? new Date(response.generated_at).toLocaleString() : "Timestamp unavailable"}</p></section> : null}
    </section>
  </>;
}
