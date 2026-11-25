export interface OverviewKPIs {
  total_units_sold: number;
  total_revenue: number;
  monitored_skus: number;
  healthy_count: number;
  reorder_alerts: number;
  potential_stockouts: number;
  possible_overstock: number;
  recommended_order_units: number;
  avg_fill_rate_pct: number | null;
  is_simulated_inventory: boolean;
}

export interface DailyTrendPoint {
  date: string;
  units_sold: number;
  revenue: number;
}

export interface StatusBreakdownItem {
  status: string;
  count: number;
}

export interface CategorySalesSummary {
  cat_id: string;
  units_sold: number;
  sku_count: number;
}

export interface InventoryItem {
  inventory_id: number;
  item_id: string;
  store_id: string;
  dept_id: string;
  cat_id: string;
  state_id: string;
  on_hand: number;
  on_order: number;
  backorders: number;
  lead_time_days: number;
  review_period_days: number;
  unit_cost: number;
  updated_at: string;
  validation_rmse: number;
  inventory_position: number;
  safety_stock: number;
  lead_time_demand: number;
  review_period_demand: number;
  reorder_point: number;
  target_stock: number;
  recommended_order_qty: number;
  status: "Healthy" | "Reorder required" | "Potential stockout" | "Possible overstock";
  is_reorder_required: boolean;
  is_potential_stockout: boolean;
  is_possible_overstock: boolean;
  alert_reasons: string[];
  is_simulated: boolean;
}

export interface OverviewResponse {
  kpis: OverviewKPIs;
  sales_trend: DailyTrendPoint[];
  status_breakdown: StatusBreakdownItem[];
  category_breakdown: CategorySalesSummary[];
  recent_alerts: InventoryItem[];
}

export interface InventoryListResponse {
  items: InventoryItem[];
  stores: string[];
  categories: string[];
  total: number;
  is_simulated_inventory: boolean;
}

export interface InventoryPatchPayload {
  on_hand?: number;
  on_order?: number;
  backorders?: number;
  lead_time_days?: number;
  review_period_days?: number;
  unit_cost?: number;
  notes?: string;
}

export interface InventoryTransaction {
  transaction_id: number;
  item_id: string;
  store_id: string;
  transaction_type: string;
  quantity: number;
  transaction_date: string;
  notes: string | null;
}

export interface SkuOption {
  item_id: string;
  store_id: string;
  dept_id: string;
  cat_id: string;
}

export interface ForecastHistoryPoint {
  date: string;
  actual_sales: number;
  sell_price: number;
}

export interface HoldoutPoint {
  date: string;
  actual_sales: number;
  lightgbm_pred: number;
  seasonal_naive_pred: number;
}

export interface ForecastPoint {
  forecast_date: string;
  lightgbm_pred: number;
  lightgbm_p95: number | null;
  seasonal_naive_pred: number | null;
}

export interface ForecastsResponse {
  item_id: string;
  store_id: string;
  dept_id: string;
  cat_id: string;
  horizon: 7 | 14 | 28;
  sku_validation_rmse: number;
  disclaimer: string;
  available_items: SkuOption[];
  history: ForecastHistoryPoint[];
  holdout_comparison: HoldoutPoint[];
  forecasts: ForecastPoint[];
}

export interface AnalyticsResponse {
  filters: {
    stores: string[];
    categories: string[];
    min_date: string;
    max_date: string;
  };
  sales_trend: {
    period: string;
    units_sold: number;
    revenue: number;
    avg_price: number;
  }[];
  top_products: {
    item_id: string;
    dept_id: string;
    cat_id: string;
    total_units: number;
    total_revenue: number;
    avg_daily_units: number;
  }[];
  low_demand_products: {
    item_id: string;
    dept_id: string;
    cat_id: string;
    total_units: number;
    total_revenue: number;
    avg_daily_units: number;
  }[];
  store_comparison: {
    store_id: string;
    total_units: number;
    total_revenue: number;
    sku_count: number;
  }[];
  category_comparison: {
    cat_id: string;
    total_units: number;
    total_revenue: number;
    sku_count: number;
  }[];
  weekday_pattern: {
    weekday: string;
    avg_units: number;
    total_units: number;
  }[];
  price_demand: {
    period: string;
    avg_price: number;
    avg_units: number;
  }[];
}

export interface AlertsResponse {
  counts: {
    all: number;
    reorder_required: number;
    potential_stockout: number;
    possible_overstock: number;
  };
  items: InventoryItem[];
  is_simulated_inventory: boolean;
}

export interface MetricSet {
  mae: number;
  rmse: number;
  wmape: number;
  forecast_bias: number;
}

export interface EvaluationResponse {
  generated_at: string;
  split: {
    val_start: string;
    test_start: string;
    test_end: string;
    holdout_days: number;
  };
  horizon_metrics: {
    horizon_days: number;
    samples: number;
    lightgbm: MetricSet;
    seasonal_naive: MetricSet;
  }[];
  category_metrics_h28: {
    cat_id: string;
    lightgbm: MetricSet;
    seasonal_naive: MetricSet;
  }[];
  policy_backtest_28d: {
    unmet_demand_mode: string;
    service_level_z: number;
    review_period_days: number;
    seasonal_naive: {
      skus_evaluated: number;
      total_actual_demand: number;
      total_served_units: number;
      total_lost_sales: number;
      fill_rate_pct: number;
      avg_daily_on_hand_per_sku: number;
      avg_total_daily_on_hand: number;
      holding_cost: number;
      stockout_cost: number;
      total_policy_cost: number;
      stockout_sku_days: number;
      orders_placed: number;
    };
    lightgbm: {
      skus_evaluated: number;
      total_actual_demand: number;
      total_served_units: number;
      total_lost_sales: number;
      fill_rate_pct: number;
      avg_daily_on_hand_per_sku: number;
      avg_total_daily_on_hand: number;
      holding_cost: number;
      stockout_cost: number;
      total_policy_cost: number;
      stockout_sku_days: number;
      orders_placed: number;
    };
    comparison: {
      lost_sales_reduction_units: number;
      lost_sales_reduction_pct: number;
      fill_rate_delta_pct: number;
      avg_on_hand_delta_per_sku: number;
      holding_cost_delta: number;
      stockout_cost_delta: number;
      total_policy_cost_savings: number;
      total_policy_cost_savings_pct: number;
    };
    annual_holding_rate: number;
    stockout_penalty_multiplier: number;
  };
}
