import type { OptimizationAdvisorStatus } from "./types";

export function advisorStatusMessage(status: OptimizationAdvisorStatus) {
  if (status === "ready") return "AI explanation generated from verified application data.";
  if (status === "insufficient_data") return "Insufficient verified data for an AI explanation.";
  return "AI Advisor is unavailable; the deterministic recommendation remains authoritative.";
}
