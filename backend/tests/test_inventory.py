"""Unit tests for forecast-aware inventory math and 28-day policy backtest."""

from __future__ import annotations

import math

import pandas as pd
import pytest

from backend.src.data_processing import load_processed_sales
from backend.src.forecasting import run_forecasting_pipeline
from backend.src.inventory import (
    calculate_inventory_position,
    calculate_safety_stock,
    compute_replenishment_metrics,
    run_28day_policy_backtest,
    simulate_policy_backtest_for_sku,
)


def test_inventory_position_formula() -> None:
    """IP = On-hand + On-order - Backorders."""
    assert calculate_inventory_position(on_hand=20, on_order=15, backorders=5) == 30
    assert calculate_inventory_position(on_hand=0, on_order=10, backorders=4) == 6


def test_safety_stock_scales_with_sqrt_lead_time() -> None:
    """Scenario 3: Increasing lead time increases Safety Stock and ROP dynamically."""
    ss_4 = calculate_safety_stock(validation_rmse=2.0, lead_time_days=4, z_score=1.645)
    ss_9 = calculate_safety_stock(validation_rmse=2.0, lead_time_days=9, z_score=1.645)

    assert ss_4 == pytest.approx(1.645 * 2.0 * 2.0)
    assert ss_9 == pytest.approx(1.645 * 2.0 * 3.0)
    assert ss_9 > ss_4

    forecasts = [5.0] * 20
    m_short = compute_replenishment_metrics(
        on_hand=40,
        on_order=0,
        backorders=0,
        lead_time_days=4,
        review_period_days=7,
        daily_forecasts=forecasts,
        validation_rmse=2.0,
    )
    m_long = compute_replenishment_metrics(
        on_hand=40,
        on_order=0,
        backorders=0,
        lead_time_days=9,
        review_period_days=7,
        daily_forecasts=forecasts,
        validation_rmse=2.0,
    )
    assert m_long.safety_stock > m_short.safety_stock
    assert m_long.reorder_point > m_short.reorder_point


def test_inventory_status_classifications() -> None:
    """Scenarios 1 & 2: Verify Healthy, Reorder required, Potential stockout, Overstock."""
    forecasts = [4.0] * 20
    # lead_time=5 -> lead_demand=20; review=7 -> review_demand=48; SS = 1.645*1*sqrt(5) ~= 3.68
    # ROP ~= 23.68, Target Stock ~= 51.68

    # 1. Healthy: On-hand=60, IP=60 > ROP, <= 1.5*Target (~77.5)
    healthy = compute_replenishment_metrics(
        on_hand=60, on_order=0, backorders=0, lead_time_days=5, review_period_days=7,
        daily_forecasts=forecasts, validation_rmse=1.0,
    )
    assert healthy.status == "Healthy"
    assert healthy.recommended_order_qty == 0

    # 2. Reorder required: On-hand=22 (>= lead_demand 20), IP=22 <= ROP (~23.68)
    reorder = compute_replenishment_metrics(
        on_hand=22, on_order=0, backorders=0, lead_time_days=5, review_period_days=7,
        daily_forecasts=forecasts, validation_rmse=1.0,
    )
    assert reorder.status == "Reorder required"
    assert reorder.is_reorder_required is True
    assert reorder.recommended_order_qty == math.ceil(reorder.target_stock - 22)

    # 3. Potential stockout: On-hand=10 < lead_demand (20)
    stockout = compute_replenishment_metrics(
        on_hand=10, on_order=0, backorders=0, lead_time_days=5, review_period_days=7,
        daily_forecasts=forecasts, validation_rmse=1.0,
    )
    assert stockout.status == "Potential stockout"
    assert stockout.is_potential_stockout is True

    # 4. Possible overstock: On-hand=100 > 1.5 * Target Stock (~77.52)
    overstock = compute_replenishment_metrics(
        on_hand=100, on_order=0, backorders=0, lead_time_days=5, review_period_days=7,
        daily_forecasts=forecasts, validation_rmse=1.0,
    )
    assert overstock.status == "Possible overstock"
    assert overstock.is_possible_overstock is True
    assert overstock.recommended_order_qty == 0


def test_demand_spike_increases_rop_and_order_qty() -> None:
    """Scenario 4: Demand forecast spike increases ROP and Recommended Order Quantity."""
    base = compute_replenishment_metrics(
        on_hand=30, on_order=0, backorders=0, lead_time_days=5, review_period_days=7,
        daily_forecasts=[3.0] * 15, validation_rmse=1.0,
    )
    spike = compute_replenishment_metrics(
        on_hand=30, on_order=0, backorders=0, lead_time_days=5, review_period_days=7,
        daily_forecasts=[8.0] * 15, validation_rmse=1.0,
    )
    assert spike.reorder_point > base.reorder_point
    assert spike.recommended_order_qty > base.recommended_order_qty


def test_outstanding_orders_prevent_duplicate_reorders() -> None:
    """Scenario 6: Open on_order raises Inventory Position above Target, preventing duplicate orders."""
    res = compute_replenishment_metrics(
        on_hand=15,
        on_order=50,
        backorders=0,
        lead_time_days=5,
        review_period_days=7,
        daily_forecasts=[4.0] * 15,
        validation_rmse=1.0,
    )
    assert res.inventory_position == 65
    assert res.is_reorder_required is False
    assert res.recommended_order_qty == 0


def test_backtest_receipt_and_lost_sales_mechanics() -> None:
    """Scenarios 5 & 7: Receipts arrive after lead time; excess demand logs Lost Sales."""
    # Opening stock=5, daily actual demand=4, lead_time=2
    # Day 0: avail=5, demand=4 -> closing=1, lost=0 -> triggers order arriving day 2
    # Day 1: avail=1, demand=4 -> closing=0, lost=3 (on_order prevents duplicate order)
    # Day 2: receipt arrives and serves demand
    res = simulate_policy_backtest_for_sku(
        actual_sales=[4.0] * 8,
        daily_forecasts=[4.0] * 8,
        opening_stock=5,
        lead_time_days=2,
        review_period_days=5,
        validation_rmse=1.0,
    )
    assert res["total_actual_demand"] == 32.0
    assert res["total_lost_sales"] >= 3.0
    assert res["total_served_units"] + res["total_lost_sales"] == pytest.approx(32.0)
    assert 0.0 <= res["fill_rate_pct"] <= 100.0
    assert res["orders_placed"] >= 1

    # Verify exact financial cost math:
    # Holding = total_on_hand_units * unit_cost * (annual_rate / 365)
    # Stockout = total_lost_sales * unit_cost * stockout_penalty_multiplier
    expected_holding = res["total_on_hand_units"] * 4.50 * (0.25 / 365.0)
    expected_stockout = res["total_lost_sales"] * 4.50 * 0.35
    assert res["holding_cost"] == pytest.approx(expected_holding, abs=1e-3)
    assert res["stockout_cost"] == pytest.approx(expected_stockout, abs=1e-3)
    assert res["total_policy_cost"] == pytest.approx(expected_holding + expected_stockout, abs=1e-3)


def test_28day_policy_backtest_on_seeded_dataset(tmp_path) -> None:
    """Run full 28-day Baseline vs. LightGBM policy backtest on sample_sales.parquet."""
    pipeline_out = run_forecasting_pipeline(models_dir=tmp_path, persist_to_sqlite=False)
    summary = pipeline_out["summary"]
    holdout = pipeline_out["holdout_predictions"]

    backtest = run_28day_policy_backtest(
        baseline_holdout_df=holdout["seasonal_naive"],
        lgbm_holdout_df=holdout["lightgbm"],
        sales_df=pipeline_out["sales_df"],
        per_sku_lgbm_rmse=summary["per_sku_val_rmse"],
        per_sku_baseline_rmse=summary["per_sku_baseline_val_rmse"],
        metrics_json_path=pipeline_out["metrics_path"],
    )

    base = backtest["seasonal_naive"]
    lgbm = backtest["lightgbm"]

    assert base["skus_evaluated"] == 50
    assert lgbm["skus_evaluated"] == 50
    assert base["total_actual_demand"] == pytest.approx(lgbm["total_actual_demand"])
    assert 0.0 <= base["fill_rate_pct"] <= 100.0
    assert 0.0 <= lgbm["fill_rate_pct"] <= 100.0
    assert lgbm["avg_daily_on_hand_per_sku"] >= 0.0
    assert lgbm["total_policy_cost"] == pytest.approx(
        lgbm["holding_cost"] + lgbm["stockout_cost"], abs=0.02
    )
    assert base["total_policy_cost"] == pytest.approx(
        base["holding_cost"] + base["stockout_cost"], abs=0.02
    )
