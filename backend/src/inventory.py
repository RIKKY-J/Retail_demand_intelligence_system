"""Inventory optimization math and 28-day policy backtest simulator.

Implements Section 8 of the implementation plan:
- Inventory Position: IP = On-hand + On-order - Backorders
- Forecast-Aware Safety Stock: SS = Z * RMSE_val * sqrt(L)
- Reorder Point: ROP = sum_{d=1..L}(y_hat_d) + SS
- Periodic Review Target Stock & Recommended Order Quantity
- Status Classification (`Potential stockout`, `Reorder required`,
  `Possible overstock`, `Healthy`)
- 28-Day Business Impact Policy Backtest comparing Baseline vs. LightGBM on
  Lost Sales (Stockout Units), Fill Rate (%), and Average On-Hand Inventory
  under an explicit lost-sales retail shelf assumption.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

import numpy as np
import pandas as pd
import yaml

from backend.src.database import REPO_ROOT

CONFIG_PATH = REPO_ROOT / "configs" / "inventory_config.yaml"


def load_inventory_config(config_path: Path = CONFIG_PATH) -> dict[str, Any]:
    with open(config_path, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


@dataclass(frozen=True)
class InventoryPolicyMetrics:
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


def calculate_inventory_position(on_hand: int, on_order: int, backorders: int) -> int:
    """Compute Inventory Position: IP = On-hand + On-order - Backorders."""
    return int(on_hand) + int(on_order) - int(backorders)


def calculate_safety_stock(
    validation_rmse: float,
    lead_time_days: int,
    z_score: float = 1.645,
) -> float:
    """Compute forecast-error-based Safety Stock: SS = Z * RMSE_val * sqrt(L)."""
    if lead_time_days < 0:
        raise ValueError("lead_time_days must be non-negative")
    if validation_rmse < 0:
        raise ValueError("validation_rmse must be non-negative")
    if z_score < 0:
        raise ValueError("z_score must be non-negative")
    return float(z_score * validation_rmse * math.sqrt(lead_time_days))


def _sum_forecast_window(daily_forecasts: Sequence[float], days: int) -> float:
    """Sum `days` of forecasted demand; pads tail with mean forecast if shorter."""
    if days <= 0:
        return 0.0
    arr = [max(0.0, float(v)) for v in daily_forecasts]
    if not arr:
        return 0.0
    if len(arr) >= days:
        return float(sum(arr[:days]))
    mean_val = float(sum(arr) / len(arr))
    return float(sum(arr) + (days - len(arr)) * mean_val)


def compute_replenishment_metrics(
    on_hand: int,
    on_order: int,
    backorders: int,
    lead_time_days: int,
    review_period_days: int,
    daily_forecasts: Sequence[float],
    validation_rmse: float,
    z_score: float = 1.645,
    overstock_multiplier: float = 1.5,
    moq: int = 1,
    pack_size: int = 1,
) -> InventoryPolicyMetrics:
    """Calculate IP, SS, ROP, Target Stock, Order Quantity, and stock status."""
    ip = calculate_inventory_position(on_hand=on_hand, on_order=on_order, backorders=backorders)
    ss = calculate_safety_stock(
        validation_rmse=validation_rmse,
        lead_time_days=lead_time_days,
        z_score=z_score,
    )

    lead_time_demand = _sum_forecast_window(daily_forecasts, lead_time_days)
    review_period_demand = _sum_forecast_window(daily_forecasts, lead_time_days + review_period_days)

    rop = lead_time_demand + ss
    target_stock = review_period_demand + ss

    raw_order = max(0, int(math.ceil(target_stock - ip)))
    if raw_order > 0:
        if pack_size > 1:
            raw_order = int(math.ceil(raw_order / pack_size) * pack_size)
        if moq > 1:
            raw_order = max(raw_order, moq)

    is_potential_stockout = bool(on_hand < lead_time_demand)
    is_reorder_required = bool(ip <= rop)
    is_possible_overstock = bool(target_stock > 0 and on_hand > overstock_multiplier * target_stock)

    # Severity-ordered primary status
    if is_potential_stockout:
        status = "Potential stockout"
    elif is_reorder_required:
        status = "Reorder required"
    elif is_possible_overstock:
        status = "Possible overstock"
    else:
        status = "Healthy"

    return InventoryPolicyMetrics(
        inventory_position=ip,
        safety_stock=round(ss, 2),
        lead_time_demand=round(lead_time_demand, 2),
        review_period_demand=round(review_period_demand, 2),
        reorder_point=round(rop, 2),
        target_stock=round(target_stock, 2),
        recommended_order_qty=raw_order,
        status=status,
        is_reorder_required=is_reorder_required,
        is_potential_stockout=is_potential_stockout,
        is_possible_overstock=is_possible_overstock,
    )


def simulate_policy_backtest_for_sku(
    actual_sales: Sequence[float],
    daily_forecasts: Sequence[float],
    opening_stock: int,
    lead_time_days: int,
    review_period_days: int,
    validation_rmse: float,
    z_score: float = 1.645,
    unit_cost: float = 4.50,
    annual_holding_rate: float = 0.25,
    stockout_penalty_multiplier: float = 0.35,
) -> dict[str, float | int]:
    """Replay a multi-day holdout period day-by-day under a lost-sales policy.

    At the start of day `t`, arriving orders increase available stock. Daily
    demand is served up to available stock; unmet demand becomes Lost Sales.
    At the end of day `t`, if Inventory Position <= ROP, an order of
    `ceil(Target Stock - IP)` is placed to arrive on day `t + lead_time_days`.
    """
    n_days = len(actual_sales)
    if len(daily_forecasts) != n_days:
        raise ValueError("actual_sales and daily_forecasts must have identical length")

    on_hand = int(opening_stock)
    pending_orders: list[tuple[int, int]] = []  # (arrival_day_idx, qty)

    total_actual = 0.0
    total_lost_sales = 0.0
    total_served = 0.0
    closing_stocks: list[int] = []
    stockout_days = 0
    orders_placed = 0

    for t in range(n_days):
        receipts = sum(qty for arr_day, qty in pending_orders if arr_day == t)
        pending_orders = [(arr_day, qty) for arr_day, qty in pending_orders if arr_day > t]

        available = on_hand + receipts
        demand = max(0.0, float(actual_sales[t]))
        closing_stock = max(0, int(round(available - demand)))
        lost_sales = max(0.0, demand - available)
        served = min(demand, float(available))

        if lost_sales > 0:
            stockout_days += 1

        total_actual += demand
        total_lost_sales += lost_sales
        total_served += served
        closing_stocks.append(closing_stock)
        on_hand = closing_stock

        # End-of-day inventory position & replenishment decision using remaining forecasts
        on_order = sum(qty for _, qty in pending_orders)
        future_window = daily_forecasts[t + 1 :] if t + 1 < n_days else [daily_forecasts[-1]]
        metrics = compute_replenishment_metrics(
            on_hand=on_hand,
            on_order=on_order,
            backorders=0,  # Lost-sales retail shelf assumption
            lead_time_days=lead_time_days,
            review_period_days=review_period_days,
            daily_forecasts=future_window,
            validation_rmse=validation_rmse,
            z_score=z_score,
        )

        if metrics.inventory_position <= metrics.reorder_point and metrics.recommended_order_qty > 0:
            pending_orders.append((t + lead_time_days, metrics.recommended_order_qty))
            orders_placed += 1

    fill_rate = (100.0 * total_served / total_actual) if total_actual > 0 else 100.0
    total_on_hand_units = float(sum(closing_stocks))
    avg_on_hand = float(np.mean(closing_stocks)) if closing_stocks else 0.0

    daily_holding_rate = annual_holding_rate / 365.0
    holding_cost = total_on_hand_units * unit_cost * daily_holding_rate
    stockout_cost = total_lost_sales * unit_cost * stockout_penalty_multiplier
    total_policy_cost = holding_cost + stockout_cost

    return {
        "total_actual_demand": round(total_actual, 2),
        "total_served_units": round(total_served, 2),
        "total_lost_sales": round(total_lost_sales, 2),
        "fill_rate_pct": round(fill_rate, 2),
        "total_on_hand_units": round(total_on_hand_units, 2),
        "avg_daily_on_hand": round(avg_on_hand, 2),
        "holding_cost": round(holding_cost, 4),
        "stockout_cost": round(stockout_cost, 4),
        "total_policy_cost": round(total_policy_cost, 4),
        "stockout_days": stockout_days,
        "orders_placed": orders_placed,
    }


def run_28day_policy_backtest(
    baseline_holdout_df: pd.DataFrame,
    lgbm_holdout_df: pd.DataFrame,
    sales_df: pd.DataFrame,
    per_sku_lgbm_rmse: dict[str, float],
    per_sku_baseline_rmse: dict[str, float] | None = None,
    config_path: Path = CONFIG_PATH,
    metrics_json_path: Path | None = None,
) -> dict[str, Any]:
    """Compare 28-day Baseline vs. LightGBM replenishment policies from identical start states."""
    config = load_inventory_config(config_path)
    z_score = float(config["inventory"]["service_level_z"])
    default_lead = int(config["inventory"]["default_lead_time_days"])
    default_review = int(config["inventory"]["default_review_period_days"])
    default_unit_cost = float(config["inventory"]["default_unit_cost"])

    fin_cfg = config.get("financial", {})
    annual_holding_rate = float(fin_cfg.get("annual_holding_rate", 0.25))
    stockout_penalty_mult = float(fin_cfg.get("stockout_penalty_multiplier", 0.35))

    base_df = baseline_holdout_df.copy()
    lgbm_df = lgbm_holdout_df.copy()
    base_df["date"] = pd.to_datetime(base_df["date"])
    lgbm_df["date"] = pd.to_datetime(lgbm_df["date"])

    first_holdout_date = lgbm_df["date"].min()
    pre_holdout = sales_df[sales_df["date"] < first_holdout_date].copy()
    pre_holdout["store_id"] = pre_holdout["store_id"].astype(str)
    pre_holdout["item_id"] = pre_holdout["item_id"].astype(str)
    pre_mean_by_sku = (
        pre_holdout.groupby(["store_id", "item_id"])["sales"].mean().to_dict()
    )
    latest_price_by_sku = (
        pre_holdout.sort_values("date")
        .groupby(["store_id", "item_id"])["sell_price"]
        .last()
        .to_dict()
    )

    merged = (
        lgbm_df[["store_id", "item_id", "date", "sales", "prediction"]]
        .rename(columns={"prediction": "lgbm_pred"})
        .merge(
            base_df[["store_id", "item_id", "date", "prediction"]].rename(
                columns={"prediction": "baseline_pred"}
            ),
            on=["store_id", "item_id", "date"],
            how="inner",
        )
        .sort_values(["store_id", "item_id", "date"])
    )

    def _empty_bucket() -> dict[str, float]:
        return {
            "total_actual_demand": 0.0,
            "total_served_units": 0.0,
            "total_lost_sales": 0.0,
            "avg_on_hand_sum": 0.0,
            "holding_cost": 0.0,
            "stockout_cost": 0.0,
            "total_policy_cost": 0.0,
            "stockout_days": 0,
            "orders_placed": 0,
            "sku_count": 0,
        }

    policy_totals: dict[str, dict[str, float]] = {
        "seasonal_naive": _empty_bucket(),
        "lightgbm": _empty_bucket(),
    }

    for idx, ((store_id, item_id), grp) in enumerate(merged.groupby(["store_id", "item_id"])):
        sku_key = f"{store_id}::{item_id}"
        lead_time = 3 + (idx % 5)  # deterministic 3-7 day supplier lead times matching seeded store
        if lead_time <= 0:
            lead_time = default_lead

        avg_hist = float(pre_mean_by_sku.get((str(store_id), str(item_id)), 1.0))
        retail_price = latest_price_by_sku.get((str(store_id), str(item_id)))
        unit_cost = round(float(retail_price) * 0.65, 2) if retail_price is not None else default_unit_cost

        # Identical starting stock for both policies (covers ~lead_time days, creating real reorder pressure)
        opening_stock = max(1, int(round(avg_hist * lead_time)))

        actual_seq = grp["sales"].to_numpy(dtype=np.float64)
        base_seq = grp["baseline_pred"].to_numpy(dtype=np.float64)
        lgbm_seq = grp["lgbm_pred"].to_numpy(dtype=np.float64)

        lgbm_rmse = float(per_sku_lgbm_rmse.get(sku_key, 1.0))
        base_rmse = (
            float(per_sku_baseline_rmse.get(sku_key, lgbm_rmse))
            if per_sku_baseline_rmse is not None
            else lgbm_rmse
        )

        base_res = simulate_policy_backtest_for_sku(
            actual_sales=actual_seq,
            daily_forecasts=base_seq,
            opening_stock=opening_stock,
            lead_time_days=lead_time,
            review_period_days=default_review,
            validation_rmse=base_rmse,
            z_score=z_score,
            unit_cost=unit_cost,
            annual_holding_rate=annual_holding_rate,
            stockout_penalty_multiplier=stockout_penalty_mult,
        )
        lgbm_res = simulate_policy_backtest_for_sku(
            actual_sales=actual_seq,
            daily_forecasts=lgbm_seq,
            opening_stock=opening_stock,
            lead_time_days=lead_time,
            review_period_days=default_review,
            validation_rmse=lgbm_rmse,
            z_score=z_score,
            unit_cost=unit_cost,
            annual_holding_rate=annual_holding_rate,
            stockout_penalty_multiplier=stockout_penalty_mult,
        )

        for name, res in (("seasonal_naive", base_res), ("lightgbm", lgbm_res)):
            agg = policy_totals[name]
            agg["total_actual_demand"] += float(res["total_actual_demand"])
            agg["total_served_units"] += float(res["total_served_units"])
            agg["total_lost_sales"] += float(res["total_lost_sales"])
            agg["avg_on_hand_sum"] += float(res["avg_daily_on_hand"])
            agg["holding_cost"] += float(res["holding_cost"])
            agg["stockout_cost"] += float(res["stockout_cost"])
            agg["total_policy_cost"] += float(res["total_policy_cost"])
            agg["stockout_days"] += int(res["stockout_days"])
            agg["orders_placed"] += int(res["orders_placed"])
            agg["sku_count"] += 1

    def _finalize(agg: dict[str, float]) -> dict[str, float | int]:
        demand = agg["total_actual_demand"]
        served = agg["total_served_units"]
        skus = max(1, int(agg["sku_count"]))
        return {
            "skus_evaluated": int(agg["sku_count"]),
            "total_actual_demand": round(demand, 2),
            "total_served_units": round(served, 2),
            "total_lost_sales": round(agg["total_lost_sales"], 2),
            "fill_rate_pct": round((100.0 * served / demand) if demand > 0 else 100.0, 2),
            "avg_daily_on_hand_per_sku": round(agg["avg_on_hand_sum"] / skus, 2),
            "avg_total_daily_on_hand": round(agg["avg_on_hand_sum"], 2),
            "holding_cost": round(agg["holding_cost"], 2),
            "stockout_cost": round(agg["stockout_cost"], 2),
            "total_policy_cost": round(agg["total_policy_cost"], 2),
            "stockout_sku_days": int(agg["stockout_days"]),
            "orders_placed": int(agg["orders_placed"]),
        }

    baseline_summary = _finalize(policy_totals["seasonal_naive"])
    lgbm_summary = _finalize(policy_totals["lightgbm"])

    lost_diff = round(baseline_summary["total_lost_sales"] - lgbm_summary["total_lost_sales"], 2)
    lost_reduction_pct = (
        round(100.0 * lost_diff / baseline_summary["total_lost_sales"], 2)
        if baseline_summary["total_lost_sales"] > 0
        else 0.0
    )
    cost_savings = round(baseline_summary["total_policy_cost"] - lgbm_summary["total_policy_cost"], 2)
    cost_savings_pct = (
        round(100.0 * cost_savings / baseline_summary["total_policy_cost"], 2)
        if baseline_summary["total_policy_cost"] > 0
        else 0.0
    )

    backtest_report = {
        "unmet_demand_mode": config["project"]["unmet_demand_mode"],
        "service_level_z": z_score,
        "review_period_days": default_review,
        "annual_holding_rate": annual_holding_rate,
        "stockout_penalty_multiplier": stockout_penalty_mult,
        "seasonal_naive": baseline_summary,
        "lightgbm": lgbm_summary,
        "comparison": {
            "lost_sales_reduction_units": lost_diff,
            "lost_sales_reduction_pct": lost_reduction_pct,
            "fill_rate_delta_pct": round(
                lgbm_summary["fill_rate_pct"] - baseline_summary["fill_rate_pct"], 2
            ),
            "avg_on_hand_delta_per_sku": round(
                lgbm_summary["avg_daily_on_hand_per_sku"]
                - baseline_summary["avg_daily_on_hand_per_sku"],
                2,
            ),
            "holding_cost_delta": round(
                lgbm_summary["holding_cost"] - baseline_summary["holding_cost"], 2
            ),
            "stockout_cost_delta": round(
                lgbm_summary["stockout_cost"] - baseline_summary["stockout_cost"], 2
            ),
            "total_policy_cost_savings": cost_savings,
            "total_policy_cost_savings_pct": cost_savings_pct,
        },
    }

    if metrics_json_path is not None and Path(metrics_json_path).exists():
        with open(metrics_json_path, "r", encoding="utf-8") as fh:
            metrics_doc = json.load(fh)
        metrics_doc["policy_backtest_28d"] = backtest_report
        with open(metrics_json_path, "w", encoding="utf-8") as fh:
            json.dump(metrics_doc, fh, indent=2)

    return backtest_report
