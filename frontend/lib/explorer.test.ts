import { describe, expect, it } from "vitest";
import { formatMoney, formatPercent, titleCaseProvider } from "./dates";

describe("Cost Explorer formatting and helpers", () => {
  it("formats provider names consistently", () => {
    expect(titleCaseProvider("aws")).toBe("AWS");
    expect(titleCaseProvider("azure")).toBe("AZURE");
    expect(titleCaseProvider("gcp")).toBe("GCP");
  });

  it("formats monetary spend amounts and handles edge cases", () => {
    expect(formatMoney(1234.56, "USD")).toContain("1,234.56");
    expect(formatMoney("0.00", "USD")).toContain("0.00");
    expect(formatMoney("invalid", "USD")).toBe("—");
  });

  it("formats percentage rollups cleanly", () => {
    expect(formatPercent("45.678")).toBe("+45.7%");
    expect(formatPercent("-12.34")).toBe("-12.3%");
    expect(formatPercent(null)).toBe("No prior baseline");
  });
});
