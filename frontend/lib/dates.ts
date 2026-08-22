import type { DatePreset } from "./types";

const isoDate = (date: Date) => date.toISOString().slice(0, 10);

export function getDateRange(preset: DatePreset, today = new Date()) {
  const end = new Date(today);
  end.setHours(12, 0, 0, 0);
  const start = new Date(end);

  if (preset === "month") {
    start.setDate(1);
  } else {
    start.setDate(start.getDate() - (preset === "7d" ? 6 : 29));
  }

  return { start_date: isoDate(start), end_date: isoDate(end) };
}

export function formatMoney(value: string | number, currency: string) {
  const amount = Number(value);
  if (!Number.isFinite(amount)) return "—";
  return new Intl.NumberFormat(undefined, {
    style: "currency",
    currency,
    maximumFractionDigits: 2,
  }).format(amount);
}

export function formatPercent(value: string | null) {
  if (value === null) return "No prior baseline";
  const amount = Number(value);
  if (!Number.isFinite(amount)) return "—";
  return `${amount >= 0 ? "+" : ""}${amount.toFixed(1)}%`;
}

export function titleCaseProvider(provider: string) {
  return provider === "gcp" ? "GCP" : provider.toUpperCase();
}
