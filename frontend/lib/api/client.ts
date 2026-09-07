import type { Alert, AlertEvaluationResult, AnomalyExplanation, AnomalyResponse, AuthResponse, Budget, BudgetEvaluation, CopilotResponse, DashboardInsights, DashboardSummary, ExplorerResponse, ForecastResponse, OptimizationAdvisor, OptimizationResponse, OptimizationRecommendation, OptimizationStatus, TokenResponse } from "../types";

const API_BASE_URL = (process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000").replace(/\/$/, "");
const API_PREFIX = `${API_BASE_URL}/api/v1`;

const ACCESS_TOKEN_KEY = "mcaicd_access_token";
const REFRESH_TOKEN_KEY = "mcaicd_refresh_token";
const USER_KEY = "mcaicd_user";

export class ApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

function getErrorMessage(detail: unknown): string {
  if (typeof detail === "string" && detail) return detail;
  if (Array.isArray(detail)) {
    const messages = detail.map((item) => {
      if (typeof item === "string") return item;
      if (item && typeof item === "object" && "msg" in item) return String(item.msg);
      return "Invalid request.";
    });
    if (messages.length) return messages.join(" ");
  }
  return "Unable to complete the request.";
}

export function getAccessToken() {
  return typeof window === "undefined" ? null : window.localStorage.getItem(ACCESS_TOKEN_KEY);
}

export function getStoredUser() {
  if (typeof window === "undefined") return null;
  const value = window.localStorage.getItem(USER_KEY);
  if (!value) return null;
  try {
    return JSON.parse(value) as AuthResponse["user"];
  } catch {
    return null;
  }
}

export function storeAuth(auth: AuthResponse) {
  window.localStorage.setItem(ACCESS_TOKEN_KEY, auth.tokens.access_token);
  window.localStorage.setItem(REFRESH_TOKEN_KEY, auth.tokens.refresh_token);
  window.localStorage.setItem(USER_KEY, JSON.stringify(auth.user));
}

export function clearAuth() {
  window.localStorage.removeItem(ACCESS_TOKEN_KEY);
  window.localStorage.removeItem(REFRESH_TOKEN_KEY);
  window.localStorage.removeItem(USER_KEY);
}

async function refreshAccessToken(): Promise<string | null> {
  const refreshToken = window.localStorage.getItem(REFRESH_TOKEN_KEY);
  if (!refreshToken) return null;
  const response = await fetch(`${API_PREFIX}/auth/refresh`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh_token: refreshToken }),
  });
  if (!response.ok) return null;
  const tokens = (await response.json()) as TokenResponse;
  window.localStorage.setItem(ACCESS_TOKEN_KEY, tokens.access_token);
  window.localStorage.setItem(REFRESH_TOKEN_KEY, tokens.refresh_token);
  return tokens.access_token;
}

async function request<T>(path: string, init: RequestInit = {}, retry = true): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set("Content-Type", "application/json");
  const token = getAccessToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);

  let response: Response;
  try {
    response = await fetch(`${API_PREFIX}${path}`, { ...init, headers });
  } catch {
    throw new ApiError(
      `Cannot reach the backend at ${API_BASE_URL}. Start the FastAPI server and try again.`,
      0,
    );
  }
  if (response.status === 401 && retry && typeof window !== "undefined") {
    const refreshed = await refreshAccessToken();
    if (refreshed) return request<T>(path, init, false);
    clearAuth();
  }
  if (!response.ok) {
    let message = "Unable to complete the request.";
    try {
      const body = (await response.json()) as { detail?: unknown };
      message = getErrorMessage(body.detail);
    } catch {
      // Keep the safe generic message when the backend response is not JSON.
    }
    throw new ApiError(message, response.status);
  }
  return (await response.json()) as T;
}

export function login(email: string, password: string) {
  return request<AuthResponse>("/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
}

export function register(fullName: string, email: string, password: string) {
  return request<AuthResponse>("/auth/register", {
    method: "POST",
    body: JSON.stringify({ full_name: fullName, email, password }),
  });
}

export function logout() {
  const refreshToken = typeof window === "undefined" ? null : window.localStorage.getItem(REFRESH_TOKEN_KEY);
  return request<{ message: string }>("/auth/logout", {
    method: "POST",
    body: JSON.stringify({ refresh_token: refreshToken || "" }),
  });
}

export function getDashboardSummary(params: { start_date: string; end_date: string }) {
  const query = new URLSearchParams(params);
  return request<DashboardSummary>(`/dashboard/summary?${query.toString()}`);
}

export function getDashboardInsights(
  params: { start_date: string; end_date: string },
  includeAi = true,
) {
  const query = new URLSearchParams({
    ...params,
    include_ai: includeAi ? "true" : "false",
  });
  return request<DashboardInsights>(`/dashboard/insights?${query.toString()}`);
}

export function getExplorerData(params: {
  start_date: string;
  end_date: string;
  provider?: string;
  account_id?: string;
  service?: string;
  region?: string;
  limit?: number;
  offset?: number;
}) {
  const query = new URLSearchParams({
    start_date: params.start_date,
    end_date: params.end_date,
  });
  if (params.provider) query.set("provider", params.provider);
  if (params.account_id) query.set("account_id", params.account_id);
  if (params.service) query.set("service", params.service);
  if (params.region) query.set("region", params.region);
  if (params.limit !== undefined) query.set("limit", String(params.limit));
  if (params.offset !== undefined) query.set("offset", String(params.offset));

  return request<ExplorerResponse>(`/explorer?${query.toString()}`);
}

export function getAnomalies(params: {
  start_date: string;
  end_date: string;
  provider?: string;
  account_id?: string;
  service?: string;
  region?: string;
  severity?: string;
  sort_by?: string;
  sort_order?: string;
  limit?: number;
  offset?: number;
}) {
  const query = new URLSearchParams({ start_date: params.start_date, end_date: params.end_date });
  for (const key of ["provider", "account_id", "service", "region", "severity", "sort_by", "sort_order"] as const) {
    const value = params[key];
    if (value) query.set(key, value);
  }
  if (params.limit !== undefined) query.set("limit", String(params.limit));
  if (params.offset !== undefined) query.set("offset", String(params.offset));
  return request<AnomalyResponse>(`/anomalies?${query.toString()}`);
}

export function explainAnomaly(anomalyId: string, params: {
  start_date: string;
  end_date: string;
  provider?: string;
  account_id?: string;
  service?: string;
  region?: string;
  severity?: string;
}) {
  return request<AnomalyExplanation>(`/anomalies/${encodeURIComponent(anomalyId)}/explanation`, {
    method: "POST",
    body: JSON.stringify(params),
  });
}

export function getForecast(params: { start_date: string; end_date: string; horizon_days: number; provider?: string; account_id?: string; service?: string; region?: string; currency?: string; dimension?: string }) {
  const query = new URLSearchParams({ start_date: params.start_date, end_date: params.end_date, horizon_days: String(params.horizon_days) });
  for (const key of ["provider", "account_id", "service", "region", "currency", "dimension"] as const) {
    const value = params[key];
    if (value) query.set(key, value);
  }
  return request<ForecastResponse>(`/forecast?${query.toString()}`);
}

export function getOptimizationRecommendations(params: {
  start_date: string;
  end_date: string;
  provider?: string;
  account_id?: string;
  service?: string;
  region?: string;
  category?: string;
  priority?: string;
  status?: string;
  sort_by?: string;
  sort_order?: string;
  limit?: number;
  offset?: number;
}) {
  const query = new URLSearchParams({ start_date: params.start_date, end_date: params.end_date });
  for (const key of ["provider", "account_id", "service", "region", "category", "priority", "status", "sort_by", "sort_order"] as const) {
    const value = params[key];
    if (value) query.set(key, value);
  }
  if (params.limit !== undefined) query.set("limit", String(params.limit));
  if (params.offset !== undefined) query.set("offset", String(params.offset));
  return request<OptimizationResponse>(`/optimization/recommendations?${query.toString()}`);
}

export function getOptimizationRecommendation(id: string, params: { start_date: string; end_date: string }) {
  const query = new URLSearchParams(params);
  return request<OptimizationRecommendation>(`/optimization/recommendations/${encodeURIComponent(id)}?${query.toString()}`);
}

export function updateOptimizationStatus(id: string, status: OptimizationStatus, params: { start_date: string; end_date: string }) {
  return request<OptimizationRecommendation>(`/optimization/recommendations/${encodeURIComponent(id)}/status`, {
    method: "PATCH",
    body: JSON.stringify({ status, ...params }),
  });
}

export function explainOptimizationRecommendation(id: string, params: { start_date: string; end_date: string }) {
  return request<OptimizationAdvisor>(`/optimization/recommendations/${encodeURIComponent(id)}/advisor`, {
    method: "POST",
    body: JSON.stringify(params),
  });
}

export function getAlerts() {
  return request<Alert[]>("/alerts");
}

export function createAlert(payload: Omit<Alert, "id" | "user_id" | "last_triggered_at" | "created_at" | "updated_at">) {
  return request<Alert>("/alerts", { method: "POST", body: JSON.stringify(payload) });
}

export function updateAlert(id: string, payload: Partial<Pick<Alert, "name" | "alert_type" | "provider" | "account_id" | "service" | "region" | "threshold" | "percentage" | "severity" | "enabled" | "cooldown_minutes">>) {
  return request<Alert>(`/alerts/${encodeURIComponent(id)}`, { method: "PATCH", body: JSON.stringify(payload) });
}

export function deleteAlert(id: string) {
  return request<void>(`/alerts/${encodeURIComponent(id)}`, { method: "DELETE" });
}

export function evaluateAlerts(params: { start_date: string; end_date: string }) {
  return request<AlertEvaluationResult[]>("/alerts/evaluate", { method: "POST", body: JSON.stringify(params) });
}

export function getBudgets() {
  return request<Budget[]>("/budgets");
}

export function createBudget(payload: Omit<Budget, "id" | "user_id" | "created_at" | "updated_at">) {
  return request<Budget>("/budgets", { method: "POST", body: JSON.stringify(payload) });
}

export function updateBudget(id: string, payload: Partial<Omit<Budget, "id" | "user_id" | "created_at" | "updated_at">>) {
  return request<Budget>(`/budgets/${encodeURIComponent(id)}`, { method: "PATCH", body: JSON.stringify(payload) });
}

export function deleteBudget(id: string) {
  return request<void>(`/budgets/${encodeURIComponent(id)}`, { method: "DELETE" });
}

export function getBudgetEvaluation(id: string) {
  return request<BudgetEvaluation>(`/budgets/${encodeURIComponent(id)}/evaluation`);
}

export function queryCopilot(question: string) {
  return request<CopilotResponse>("/copilot/query", {
    method: "POST",
    body: JSON.stringify({ question }),
  });
}
