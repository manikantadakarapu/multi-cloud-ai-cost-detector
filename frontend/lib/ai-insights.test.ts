import { describe, expect, it } from "vitest";
import { aiExplanationNotice } from "./ai-insights";

describe("AI insight status copy", () => {
  it("hides notices when AI is ready, disabled, empty, or pending", () => {
    expect(aiExplanationNotice("ready")).toBeNull();
    expect(aiExplanationNotice("disabled")).toBeNull();
    expect(aiExplanationNotice("empty")).toBeNull();
    expect(aiExplanationNotice("pending")).toBeNull();
  });

  it("uses a safe fallback for timeout, quota, invalid, and unavailable states", () => {
    expect(aiExplanationNotice("timeout")).toBe(
      "Cost insight available. AI explanation temporarily unavailable.",
    );
    expect(aiExplanationNotice("quota_exceeded")).toContain("temporarily unavailable");
    expect(aiExplanationNotice("invalid")).toContain("temporarily unavailable");
    expect(aiExplanationNotice("unavailable", "Cost insight available. AI explanation temporarily unavailable.")).toContain(
      "temporarily unavailable",
    );
  });
});
