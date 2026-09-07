"use client";

import { useState } from "react";
import { ApiError, queryCopilot } from "../lib/api/client";
import type { CopilotResponse } from "../lib/types";

const EXAMPLES = [
  "Why did my cloud cost increase this month?",
  "Which budgets are at risk?",
  "What are my biggest optimization opportunities?",
  "What anomalies should I investigate?",
  "What is my forecasted spend?",
];

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
    <section className="dashboard-header"><div><p className="eyebrow">Evidence-constrained assistance</p><h1>FinOps Copilot</h1><p className="muted">Ask about verified costs, anomalies, forecasts, recommendations, and budgets.</p></div></section>
    <section className="copilot-layout">
      <div className="panel copilot-panel"><div className="panel-heading"><div><span className="card-label">Ask a FinOps question</span><h3>What would you like to understand?</h3></div></div><form onSubmit={(event) => { event.preventDefault(); void ask(); }}><textarea aria-label="FinOps Copilot question" value={question} onChange={(event) => setQuestion(event.target.value)} placeholder="Why did my cloud cost increase this month?" maxLength={1000} rows={4} /><button className="primary-button" type="submit" disabled={loading || !question.trim()}>{loading ? "Reviewing verified data…" : "Ask Copilot"}</button></form><div className="copilot-examples"><span className="card-label">Try an example</span>{EXAMPLES.map((example) => <button type="button" className="ghost-button" key={example} onClick={() => { setQuestion(example); void ask(example); }}>{example}</button>)}</div></div>
      {error ? <div className="error-banner" role="alert"><span>{error}</span><button className="ghost-button" onClick={() => void ask()}>Try again</button></div> : null}
      {response ? <section className="panel copilot-response" aria-label="FinOps Copilot response"><div className="panel-heading"><div><span className="card-label">{response.status === "ready" ? "AI-assisted answer" : "Verified fallback"}</span><h3>{response.answer}</h3></div><span className={`badge ${response.status}`}>{response.status}</span></div><div className="copilot-columns"><div><h4>Key findings</h4><ul>{response.key_findings.map((item) => <li key={item}>{item}</li>)}</ul></div><div><h4>Evidence</h4>{response.evidence.length ? <ul>{response.evidence.map((item) => <li key={item}>{item}</li>)}</ul> : <p className="muted">See the referenced dashboard data for evidence.</p>}</div></div>{response.recommended_next_steps.length ? <><h4>Suggested next steps</h4><ul>{response.recommended_next_steps.map((item) => <li key={item}>{item}</li>)}</ul></> : null}{response.limitations.length ? <><h4>Limitations</h4><ul>{response.limitations.map((item) => <li key={item}>{item}</li>)}</ul></> : null}<p className="copilot-confidence">Confidence: {response.confidence} · Intent: {response.intent}</p></section> : null}
    </section>
  </>;
}
