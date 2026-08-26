import type { AIInsightStatus } from "./types";

export function aiExplanationNotice(status: AIInsightStatus, message?: string | null) {
  if (status === "ready" || status === "disabled" || status === "empty" || status === "pending") {
    return null;
  }
  return message || "Cost insight available. AI explanation temporarily unavailable.";
}
