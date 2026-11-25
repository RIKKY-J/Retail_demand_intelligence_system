import type {
  AlertsResponse,
  AnalyticsResponse,
  EvaluationResponse,
  ForecastsResponse,
  InventoryItem,
  InventoryListResponse,
  InventoryPatchPayload,
  InventoryTransaction,
  OverviewResponse,
} from "./types";

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    cache: "no-store",
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
  });

  if (!res.ok) {
    const text = await res.text();
    throw new Error(`API error ${res.status} on ${path}: ${text}`);
  }
  return res.json() as Promise<T>;
}

export function fetchOverview(storeId?: string, days = 90): Promise<OverviewResponse> {
  const params = new URLSearchParams({ days: String(days) });
  if (storeId) params.set("store_id", storeId);
  return apiFetch<OverviewResponse>(`/api/overview?${params.toString()}`);
}

export function fetchInventory(filters?: {
  store_id?: string;
  cat_id?: string;
  status?: string;
  search?: string;
}): Promise<InventoryListResponse> {
  const params = new URLSearchParams();
  if (filters?.store_id) params.set("store_id", filters.store_id);
  if (filters?.cat_id) params.set("cat_id", filters.cat_id);
  if (filters?.status) params.set("status", filters.status);
  if (filters?.search) params.set("search", filters.search);
  const qs = params.toString();
  return apiFetch<InventoryListResponse>(`/api/inventory${qs ? `?${qs}` : ""}`);
}

export function patchInventoryItem(
  storeId: string,
  itemId: string,
  payload: InventoryPatchPayload
): Promise<InventoryItem> {
  return apiFetch<InventoryItem>(`/api/inventory/${storeId}/${itemId}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export function fetchItemTransactions(
  storeId: string,
  itemId: string,
  limit = 15
): Promise<InventoryTransaction[]> {
  return apiFetch<InventoryTransaction[]>(
    `/api/inventory/${storeId}/${itemId}/transactions?limit=${limit}`
  );
}

export function fetchForecasts(params: {
  store_id?: string;
  item_id?: string;
  horizon?: 7 | 14 | 28;
  history_days?: number;
}): Promise<ForecastsResponse> {
  const qs = new URLSearchParams();
  if (params.store_id) qs.set("store_id", params.store_id);
  if (params.item_id) qs.set("item_id", params.item_id);
  if (params.horizon) qs.set("horizon", String(params.horizon));
  if (params.history_days) qs.set("history_days", String(params.history_days));
  return apiFetch<ForecastsResponse>(`/api/forecasts?${qs.toString()}`);
}

export function fetchAnalytics(params?: {
  store_id?: string;
  cat_id?: string;
  start_date?: string;
  end_date?: string;
  granularity?: "daily" | "weekly" | "monthly";
}): Promise<AnalyticsResponse> {
  const qs = new URLSearchParams();
  if (params?.store_id) qs.set("store_id", params.store_id);
  if (params?.cat_id) qs.set("cat_id", params.cat_id);
  if (params?.start_date) qs.set("start_date", params.start_date);
  if (params?.end_date) qs.set("end_date", params.end_date);
  if (params?.granularity) qs.set("granularity", params.granularity);
  const s = qs.toString();
  return apiFetch<AnalyticsResponse>(`/api/analytics${s ? `?${s}` : ""}`);
}

export function fetchAlerts(params?: {
  store_id?: string;
  cat_id?: string;
  alert_type?: "all" | "reorder" | "stockout" | "overstock";
}): Promise<AlertsResponse> {
  const qs = new URLSearchParams();
  if (params?.store_id) qs.set("store_id", params.store_id);
  if (params?.cat_id) qs.set("cat_id", params.cat_id);
  if (params?.alert_type) qs.set("alert_type", params.alert_type);
  const s = qs.toString();
  return apiFetch<AlertsResponse>(`/api/alerts${s ? `?${s}` : ""}`);
}

export function fetchEvaluation(): Promise<EvaluationResponse> {
  return apiFetch<EvaluationResponse>("/api/evaluation");
}
