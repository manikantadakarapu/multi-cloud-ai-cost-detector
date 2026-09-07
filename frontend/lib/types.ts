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
export type ExplanationStatus = "ready" | "disabled" | "unavailable" | "timeout" | "invalid" | "not_found";
export type AnomalyExplanation = {
  anomaly: CostAnomaly;
  context: {
    context_version: string;
    evidence: { label: string; value: string; status: "verified" | "derived" | "unknown" }[];
    daily_costs: { date: string; cost: string }[];
    service_changes: { value: string; current_cost: string; baseline_cost: string; change_amount: string; change_percentage: string | null; share_of_increment: string | null }[];
    region_changes: { value: string; current_cost: string; baseline_cost: string; change_amount: string; change_percentage: string | null; share_of_increment: string | null }[];
    provider_changes: { value: string; current_cost: string; baseline_cost: string; change_amount: string; change_percentage: string | null; share_of_increment: string | null }[];
    unknowns: string[];
  };
  status: ExplanationStatus;
  summary: string | null;
  likely_causes: { cause: string; evidence: string; confidence: "low" | "medium" | "high" }[];
  impact: string | null;
  investigation_steps: string[];
  confidence: "low" | "medium" | "high" | null;
  limitations: string[];
  generated_at: string | null;
  model: string | null;
  prompt_version: string;
  fallback_message: string | null;
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
export type ForecastStatus = "ready" | "insufficient_data" | "empty";
export type ForecastDimension = "total" | "provider" | "service" | "account" | "region";
export type DailyForecast = { date: string; actual_cost: string | null; forecast_cost: string; lower_bound: string; upper_bound: string };
export type ForecastResult = {
  forecast_id: string;
  dimension: ForecastDimension;
  dimension_value: string;
  provider: string | null;
  account_id: string | null;
  service: string | null;
  region: string | null;
  forecast_start: string;
  forecast_end: string;
  horizon_days: number;
  currency: string;
  historical_cost: string;
  projected_cost: string;
  daily_forecast: DailyForecast[];
  historical_daily: { date: string; cost: string }[];
  lower_bound: string;
  upper_bound: string;
  methodology: string;
  confidence: "low" | "medium" | "high";
  data_points_used: number;
  generated_at: string;
  excluded_anomaly_dates: string[];
  missing_dates: string[];
  accuracy: { observations: number; mean_absolute_error: string; mean_absolute_percentage_error: string | null } | null;
};
export type ForecastResponse = {
  status: ForecastStatus;
  query: { start_date: string; end_date: string; horizon_days: number; provider?: string | null; account_id?: string | null; service?: string | null; region?: string | null; dimension: ForecastDimension };
  summary: { current_spend: string; projected_spend: string; projected_change_percentage: string | null; average_historical_daily_cost: string; projected_daily_average: string; confidence: "low" | "medium" | "high" | null; data_points_used: number };
  forecasts: ForecastResult[];
  data_quality: { available_observations: number; required_observations: number; missing_dates: string[]; duplicate_records_removed: number; excluded_anomaly_dates: string[]; warnings: string[] };
  methodology_version: string;
  message: string | null;
};

export type OptimizationCategory = "cost_growth" | "high_cost_service" | "storage" | "network";
export type OptimizationPriority = "low" | "medium" | "high" | "critical";
export type OptimizationConfidence = "low" | "medium" | "high";
export type OptimizationStatus = "new" | "reviewed" | "dismissed" | "implemented";
export type OptimizationEvidence = { label: string; value: string; source: string };
export type OptimizationRecommendation = {
  recommendation_id: string;
  provider: string;
  account_id: string | null;
  service: string;
  region: string | null;
  resource_identifier: string | null;
  category: OptimizationCategory;
  title: string;
  description: string;
  rationale: string;
  evidence: OptimizationEvidence[];
  priority: OptimizationPriority;
  current_cost: string;
  estimated_monthly_savings: string | null;
  estimated_annual_savings: string | null;
  savings_currency: string;
  savings_period: string;
  savings_explanation: string | null;
  confidence: OptimizationConfidence;
  status: OptimizationStatus;
  detection_method: string;
  rule_version: string;
  created_at: string;
};
export type OptimizationResponse = {
  recommendations: OptimizationRecommendation[];
  total: number;
  limit: number;
  offset: number;
  summary: {
    total_recommendations: number;
    high_or_critical: number;
    estimated_monthly_savings: string | null;
    estimated_annual_savings: string | null;
    by_category: Record<string, number>;
    by_provider: Record<string, number>;
  };
  query: Record<string, unknown>;
  rule_version: string;
  insufficient_data: boolean;
  message: string | null;
};
export type OptimizationAdvisorStatus = "ready" | "disabled" | "unavailable" | "timeout" | "invalid" | "insufficient_data";
export type OptimizationAdvisor = {
  recommendation: OptimizationRecommendation;
  context: {
    context_version: string;
    recommendation: OptimizationRecommendation;
    historical_cost: string | null;
    cost_trend: { date: string; cost: string }[];
    related_anomalies: CostAnomaly[];
    forecast: ForecastResult | null;
    explorer: { record_count: number; total_cost: string; currency: string | null; daily_costs: { date: string; cost: string }[] } | null;
    data_freshness: string | null;
    missing_data: string[];
  };
  status: OptimizationAdvisorStatus;
  summary: string | null;
  why_it_matters: string | null;
  evidence_summary: string | null;
  tradeoffs: string[];
  suggested_next_steps: string[];
  expected_impact: string | null;
  confidence: "low" | "medium" | "high" | null;
  limitations: string[];
  generated_at: string | null;
  model: string | null;
  prompt_version: string;
  fallback_message: string | null;
};
