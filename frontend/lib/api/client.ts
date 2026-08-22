import type { AuthResponse, DashboardInsights, DashboardSummary, TokenResponse } from "../types";

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

  const response = await fetch(`${API_PREFIX}${path}`, { ...init, headers });
  if (response.status === 401 && retry && typeof window !== "undefined") {
    const refreshed = await refreshAccessToken();
    if (refreshed) return request<T>(path, init, false);
    clearAuth();
  }
  if (!response.ok) {
    let message = "Unable to complete the request.";
    try {
      const body = (await response.json()) as { detail?: string };
      message = body.detail || message;
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

export function getDashboardInsights(params: { start_date: string; end_date: string }) {
  const query = new URLSearchParams(params);
  return request<DashboardInsights>(`/dashboard/insights?${query.toString()}`);
}
