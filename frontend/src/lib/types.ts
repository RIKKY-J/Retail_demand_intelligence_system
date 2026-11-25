export interface ModelMetricRow {
  model: string;
  mae: number;
  rmse: number;
  wmape: number;
}

export interface OverviewResponse {
  kpis: {
    total_units_sold: number;
    monitored_skus: number;
    low_stock_alerts: number;
    healthy_count: number;
    overstock_count: number;
    best_model: string;
    best_model_rmse: number | null;
  };
  daily_sales_trend: {
    date: string;
    units_sold: number;
  }[];
  model_comparison: ModelMetricRow[];
  split: {
    train_end: string;
    test_start: string;
    test_end: string;
    test_days: number;
  };
}

export interface SkuOption {
  item_id: string;
  cat_id: string;
}

export interface ForecastResponse {
  item_id: string;
  cat_id: string;
  best_model: string;
  sku_rmse: number;
  available_items: SkuOption[];
  history_30d: {
    date: string;
    actual_sales: number;
  }[];
  holdout_28d: {
    date: string;
    actual_sales: number;
    predicted_sales: number;
  }[];
  forecast_7d: {
    forecast_date: string;
    predicted_sales: number;
  }[];
}

export interface InventoryItem {
  item_id: string;
  cat_id: string;
  current_stock: number;
  lead_time_days: number;
  safety_stock: number;
  reorder_point: number;
  recommended_order_qty: number;
  status: "Low Stock (Reorder)" | "Healthy" | "Overstock";
  updated_at: string;
}

export interface InventoryListResponse {
  items: InventoryItem[];
  total: number;
}
