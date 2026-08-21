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

export type DashboardInsights = { insights: CostInsight[] };
