import { describe, expect, it } from "vitest";
import { advisorStatusMessage } from "./optimization-advisor";

describe("optimization advisor states", () => {
  it("describes a ready advisor response", () => {
    expect(advisorStatusMessage("ready")).toContain("verified application data");
  });

  it("handles missing data and failures without changing the recommendation", () => {
    expect(advisorStatusMessage("insufficient_data")).toContain("Insufficient");
    expect(advisorStatusMessage("invalid")).toContain("deterministic recommendation");
  });
});
