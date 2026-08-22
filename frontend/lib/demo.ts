import type { DashboardInsights, DashboardSummary } from "./types";

type DateRange = { start_date: string; end_date: string };

function datesBetween(startDate: string, endDate: string) {
  const dates: string[] = [];
  const current = new Date(`${startDate}T12:00:00Z`);
  const end = new Date(`${endDate}T12:00:00Z`);
  while (current <= end) {
    dates.push(current.toISOString().slice(0, 10));
    current.setUTCDate(current.getUTCDate() + 1);
  }
  return dates;
}

export function getDemoDashboardData(range: DateRange): {
  summary: DashboardSummary;
  insights: DashboardInsights;
} {
  const dates = datesBetween(range.start_date, range.end_date);
  const trend = dates.map((date, index) => ({
    date,
    cost: (350 + ((index * 83) % 280) + (index % 5) * 42).toFixed(2),
  }));

  return {
    summary: {
      overview: {
        total_cost: "12840.55",
        currency: "USD",
        period_start: range.start_date,
        period_end: range.end_date,
        previous_period_cost: "11260.22",
        absolute_change: "1580.33",
        percentage_change: "14.0",
      },
      providers: [
        { provider: "aws", cost: "7215.35", percentage: "56.2" },
        { provider: "azure", cost: "3595.35", percentage: "28.0" },
        { provider: "gcp", cost: "2029.85", percentage: "15.8" },
      ],
      services: [
        { provider: "aws", service_name: "Amazon EC2", cost: "3420.18", percentage: "26.6" },
        { provider: "azure", service_name: "Virtual Machines", cost: "2110.42", percentage: "16.4" },
        { provider: "aws", service_name: "Amazon S3", cost: "1486.70", percentage: "11.6" },
        { provider: "gcp", service_name: "BigQuery", cost: "1024.65", percentage: "8.0" },
        { provider: "aws", service_name: "Amazon RDS", cost: "879.11", percentage: "6.8" },
      ],
      trend,
      drivers: [],
    },
    insights: {
      insights: [
        {
          type: "cost_increase",
          severity: "high",
          title: "Compute spend increased",
          description: "Compute costs are above the previous period baseline.",
          provider: "aws",
          service: "Amazon EC2",
          impact: "620.40",
          currency: "USD",
        },
        {
          type: "top_cost_driver",
          severity: "medium",
          title: "AWS remains the largest cost center",
          description: "AWS accounts for more than half of the selected period spend.",
          provider: "aws",
          service: null,
          impact: "7215.35",
          currency: "USD",
        },
        {
          type: "cost_decrease",
          severity: "low",
          title: "Object storage costs improved",
          description: "Storage spend is trending below the previous period baseline.",
          provider: "aws",
          service: "Amazon S3",
          impact: "180.25",
          currency: "USD",
        },
      ],
    },
  };
}
