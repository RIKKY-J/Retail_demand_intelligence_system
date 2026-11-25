import type {
  ForecastResponse,
  InventoryItem,
  InventoryListResponse,
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
    throw new Error(`API ${res.status} on ${path}: ${text}`);
  }
  return res.json() as Promise<T>;
}

export function fetchOverview(): Promise<OverviewResponse> {
  return apiFetch<OverviewResponse>("/api/overview");
}

export function fetchForecast(itemId?: string): Promise<ForecastResponse> {
  const qs = itemId ? `?item_id=${encodeURIComponent(itemId)}` : "";
  return apiFetch<ForecastResponse>(`/api/forecast${qs}`);
}

export function fetchInventory(): Promise<InventoryListResponse> {
  return apiFetch<InventoryListResponse>("/api/inventory");
}

export function patchInventory(
  itemId: string,
  payload: { current_stock?: number; lead_time_days?: number }
): Promise<InventoryItem> {
  return apiFetch<InventoryItem>(`/api/inventory/${encodeURIComponent(itemId)}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}
