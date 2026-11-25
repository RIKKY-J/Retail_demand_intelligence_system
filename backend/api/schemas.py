"""Pydantic request and response schemas for the FastAPI REST API."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class OverviewKPIs(BaseModel):
    total_units_sold: int
    total_revenue: float
    monitored_skus: int
    healthy_count: int
    reorder_alerts: int
    potential_stockouts: int
    possible_overstock: int
    recommended_order_units: int
    avg_fill_rate_pct: Optional[float] = None
    is_simulated_inventory: bool = True


class DailyTrendPoint(BaseModel):
    date: str
    units_sold: int
    revenue: float


class StatusBreakdownItem(BaseModel):
    status: str
    count: int


class CategorySalesSummary(BaseModel):
    cat_id: str
    units_sold: int
    sku_count: int


class InventoryItemOut(BaseModel):
    inventory_id: int
    item_id: str
    store_id: str
    dept_id: str
    cat_id: str
    state_id: str
    on_hand: int
    on_order: int
    backorders: int
    lead_time_days: int
    review_period_days: int
    unit_cost: float
    updated_at: str
    validation_rmse: float
    inventory_position: int
    safety_stock: float
    lead_time_demand: float
    review_period_demand: float
    reorder_point: float
    target_stock: float
    recommended_order_qty: int
    status: str
    is_reorder_required: bool
    is_potential_stockout: bool
    is_possible_overstock: bool
    alert_reasons: list[str]
    is_simulated: bool = True


class OverviewResponse(BaseModel):
    kpis: OverviewKPIs
    sales_trend: list[DailyTrendPoint]
    status_breakdown: list[StatusBreakdownItem]
    category_breakdown: list[CategorySalesSummary]
    recent_alerts: list[InventoryItemOut]


class InventoryListResponse(BaseModel):
    items: list[InventoryItemOut]
    stores: list[str]
    categories: list[str]
    total: int
    is_simulated_inventory: bool = True


class InventoryPatchRequest(BaseModel):
    on_hand: Optional[int] = Field(default=None, ge=0)
    on_order: Optional[int] = Field(default=None, ge=0)
    backorders: Optional[int] = Field(default=None, ge=0)
    lead_time_days: Optional[int] = Field(default=None, ge=1, le=90)
    review_period_days: Optional[int] = Field(default=None, ge=1, le=90)
    unit_cost: Optional[float] = Field(default=None, ge=0.0)
    notes: Optional[str] = Field(default=None, max_length=300)


class TransactionOut(BaseModel):
    transaction_id: int
    item_id: str
    store_id: str
    transaction_type: str
    quantity: int
    transaction_date: str
    notes: Optional[str] = None


class SkuOption(BaseModel):
    item_id: str
    store_id: str
    dept_id: str
    cat_id: str


class ForecastHistoryPoint(BaseModel):
    date: str
    actual_sales: int
    sell_price: float


class HoldoutPoint(BaseModel):
    date: str
    actual_sales: int
    lightgbm_pred: float
    seasonal_naive_pred: float


class ForecastPoint(BaseModel):
    forecast_date: str
    lightgbm_pred: float
    lightgbm_p95: Optional[float] = None
    seasonal_naive_pred: Optional[float] = None


class ForecastsResponse(BaseModel):
    item_id: str
    store_id: str
    dept_id: str
    cat_id: str
    horizon: int
    sku_validation_rmse: float
    disclaimer: str
    available_items: list[SkuOption]
    history: list[ForecastHistoryPoint]
    holdout_comparison: list[HoldoutPoint]
    forecasts: list[ForecastPoint]


class AnalyticsFiltersMeta(BaseModel):
    stores: list[str]
    categories: list[str]
    min_date: str
    max_date: str


class AnalyticsTrendPoint(BaseModel):
    period: str
    units_sold: int
    revenue: float
    avg_price: float


class ProductPerformance(BaseModel):
    item_id: str
    dept_id: str
    cat_id: str
    total_units: int
    total_revenue: float
    avg_daily_units: float


class StoreComparisonItem(BaseModel):
    store_id: str
    total_units: int
    total_revenue: float
    sku_count: int


class CategoryComparisonItem(BaseModel):
    cat_id: str
    total_units: int
    total_revenue: float
    sku_count: int


class WeekdayPatternItem(BaseModel):
    weekday: str
    avg_units: float
    total_units: int


class PriceDemandPoint(BaseModel):
    period: str
    avg_price: float
    avg_units: float


class AnalyticsResponse(BaseModel):
    filters: AnalyticsFiltersMeta
    sales_trend: list[AnalyticsTrendPoint]
    top_products: list[ProductPerformance]
    low_demand_products: list[ProductPerformance]
    store_comparison: list[StoreComparisonItem]
    category_comparison: list[CategoryComparisonItem]
    weekday_pattern: list[WeekdayPatternItem]
    price_demand: list[PriceDemandPoint]


class AlertCounts(BaseModel):
    all: int
    reorder_required: int
    potential_stockout: int
    possible_overstock: int


class AlertsResponse(BaseModel):
    counts: AlertCounts
    items: list[InventoryItemOut]
    is_simulated_inventory: bool = True


class MetricSet(BaseModel):
    mae: float
    rmse: float
    wmape: float
    forecast_bias: float


class HorizonMetricRow(BaseModel):
    horizon_days: int
    samples: int
    lightgbm: MetricSet
    seasonal_naive: MetricSet


class CategoryMetricRow(BaseModel):
    cat_id: str
    lightgbm: MetricSet
    seasonal_naive: MetricSet


class BacktestPolicyResult(BaseModel):
    skus_evaluated: int
    total_actual_demand: float
    total_served_units: float
    total_lost_sales: float
    fill_rate_pct: float
    avg_daily_on_hand_per_sku: float
    avg_total_daily_on_hand: float
    holding_cost: float
    stockout_cost: float
    total_policy_cost: float
    stockout_sku_days: int
    orders_placed: int


class BacktestComparison(BaseModel):
    lost_sales_reduction_units: float
    lost_sales_reduction_pct: float
    fill_rate_delta_pct: float
    avg_on_hand_delta_per_sku: float
    holding_cost_delta: float
    stockout_cost_delta: float
    total_policy_cost_savings: float
    total_policy_cost_savings_pct: float


class PolicyBacktestOut(BaseModel):
    unmet_demand_mode: str
    service_level_z: float
    review_period_days: int
    annual_holding_rate: float
    stockout_penalty_multiplier: float
    seasonal_naive: BacktestPolicyResult
    lightgbm: BacktestPolicyResult
    comparison: BacktestComparison


class SplitInfo(BaseModel):
    val_start: str
    test_start: str
    test_end: str
    holdout_days: int


class EvaluationResponse(BaseModel):
    generated_at: str
    split: SplitInfo
    horizon_metrics: list[HorizonMetricRow]
    category_metrics_h28: list[CategoryMetricRow]
    policy_backtest_28d: PolicyBacktestOut
