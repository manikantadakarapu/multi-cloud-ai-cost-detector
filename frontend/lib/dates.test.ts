import { describe, expect, it } from "vitest";
import { formatDateLabel, formatPercent, getDateRange } from "./dates";

describe("dashboard date helpers", () => {
  it("returns an inclusive seven-day range", () => {
    expect(getDateRange("7d", new Date("2026-08-21T12:00:00Z"))).toEqual({
      start_date: "2026-08-15",
      end_date: "2026-08-21",
    });
  });

  it("returns the first day of the current month", () => {
    expect(getDateRange("month", new Date("2026-08-21T12:00:00Z")).start_date).toBe("2026-08-01");
  });

  it("formats a missing comparison baseline safely", () => {
    expect(formatPercent(null)).toBe("No prior baseline");
  });

  it("formats trend dates for chart labels", () => {
    expect(formatDateLabel("2026-08-21")).toBe("Aug 21");
  });
});
