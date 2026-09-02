export type DatePreset = "7d" | "30d" | "month";

export type TokenResponse = {
  access_token: string;
  refresh_token: string;
  token_type: "bearer";
  expires_in: number;
};

export type User = {
  id: string;
  email: string;
  full_name: string;
  is_active: boolean;
};

export type AuthResponse = {
  user: User;
  tokens: TokenResponse;
};

export type ProviderCost = {
  provider: string;
  cost: string;
  percentage: string;
};

export type ServiceCost = {
  provider: string;
  service_name: string;
  cost: string;
  percentage: string;
};

export type TrendPoint = {
  date: string;
  cost: string;
};

export type CostDriver = {
  category: "provider" | "service";
  name: string;
  provider: string | null;
  current_cost: string;
  previous_cost: string;
  absolute_change: string;
  percentage_change: string | null;
};

export type DashboardSummary = {
  overview: {
    total_cost: string;
    currency: string;
    period_start: string;
    period_end: string;
    previous_period_cost: string;
    absolute_change: string;
    percentage_change: string | null;
  };
  providers: ProviderCost[];
  services: ServiceCost[];
  trend: TrendPoint[];
  drivers: CostDriver[];
};

export type CostInsight = {
  type: "cost_increase" | "cost_decrease" | "top_cost_driver";
  severity: "low" | "medium" | "high";
  title: string;
  description: string;
  provider: string | null;
  service: string | null;
  impact: string;
  currency: string;
};

export type AIInsightStatus =
  | "ready"
  | "pending"
  | "disabled"
  | "empty"
  | "unavailable"
  | "quota_exceeded"
  | "timeout"
  | "invalid";

export type AIInsight = {
  title: string;
  summary: string;
  severity: "low" | "medium" | "high";
  likely_cause: string;
  recommended_action: string;
  event_type: "cost_increase" | "cost_decrease";
  provider: string | null;
  service: string | null;
  current_cost: string;
  previous_cost: string;
  absolute_change: string;
  percentage_change: string | null;
  currency: string;
  period_start: string;
  period_end: string;
  source: string;
};

export type DashboardInsights = {
  insights: CostInsight[];
  ai_insights: AIInsight[];
  ai_status: AIInsightStatus;
  ai_message: string | null;
};

export type AnomalySeverity = "normal" | "low" | "medium" | "high" | "critical";
export type CostAnomaly = {
  id: string;
  provider: string;
  account_id: string | null;
  account_name: string | null;
  service: string;
  region: string | null;
  date: string;
  actual_cost: string;
  expected_cost: string;
  deviation_amount: string;
  deviation_percentage: string | null;
  anomaly_score: string;
  severity: AnomalySeverity;
  detection_method: string;
  baseline_period: string;
  currency: string;
  created_at: string;
};
export type AnomalyResponse = {
  anomalies: CostAnomaly[];
  total: number;
  limit: number;
  offset: number;
  summary: { total: number; high_or_critical: number; by_severity: Record<AnomalySeverity, number> };
  trend: { date: string; count: number }[];
  start_date: string;
  end_date: string;
  baseline_lookback_days: number;
  detector_version: string;
};
export type CostRecord = {
  date: string;
  provider: string;
  account_id: string | null;
  account_name: string | null;
  service: string;
  region: string | null;
  cost: string;
  currency: string;
};

export type DimensionTotal = {
  key: string;
  label: string;
  cost: string;
  percentage: string;
  currency: string;
  record_count: number;
};

export type DailyCostRecord = {
  date: string;
  cost: string;
  currency: string;
};

export type DimensionBreakdowns = {
  by_provider: DimensionTotal[];
  by_service: DimensionTotal[];
  by_region: DimensionTotal[];
  by_account: DimensionTotal[];
  by_date: DailyCostRecord[];
};

export type ExplorerOverview = {
  total_cost: string;
  currency: string;
  record_count: number;
  start_date: string;
  end_date: string;
};

export type AvailableFilters = {
  providers: string[];
  accounts: string[];
  services: string[];
  regions: string[];
};

export type ExplorerResponse = {
  overview: ExplorerOverview;
  records: CostRecord[];
  dimension_totals: DimensionBreakdowns;
  available_filters: AvailableFilters;
  total_records: number;
  limit: number;
  offset: number;
};
