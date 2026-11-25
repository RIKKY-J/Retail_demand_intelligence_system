"""Unit tests for data processing, leakage prevention, and demand forecasting."""

from __future__ import annotations

from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd
import pytest

from backend.src.data_processing import (
    build_horizon_features,
    chronological_split_dates,
    load_processed_sales,
)
from backend.src.forecasting import (
    compute_metrics,
    predict_seasonal_naive,
    run_forecasting_pipeline,
)


def test_sell_price_nan_filtered_before_features() -> None:
    """Rows with NaN sell_price must be dropped BEFORE lag/rolling calculation."""
    dates = pd.date_range("2016-01-01", periods=30, freq="D")
    df = pd.DataFrame(
        {
            "id": "TEST_ITEM_CA_1_validation",
            "item_id": "TEST_ITEM",
            "dept_id": "FOODS_1",
            "cat_id": "FOODS",
            "store_id": "CA_1",
            "state_id": "CA",
            "date": dates,
            # First 10 days unstocked (NaN price, 0 sales); next 20 days stocked at sales=5
            "sell_price": [np.nan] * 10 + [3.99] * 20,
            "sales": [0] * 10 + [5] * 20,
        }
    )

    feat = build_horizon_features(df, horizon=7)
    assert len(feat) == 20
    assert feat["sell_price"].isna().sum() == 0

    # Day index 17 of the 20 stocked days (i.e. 18th stocked day) has >= 10 prior stocked days
    # so 7-day rolling mean shifted by 7 must equal exactly 5.0 (no contamination from unstocked 0s).
    assert np.isclose(feat.iloc[-1]["rolling_mean_7_shift_h"], 5.0)
    assert np.isclose(feat.iloc[-1]["lag_h"], 5.0)


def test_float32_downcasting_on_sample_parquet() -> None:
    """All float columns in engineered features must be downcast to float32."""
    df = load_processed_sales()
    feat = build_horizon_features(df, horizon=7)
    float64_cols = feat.select_dtypes(include=["float64"]).columns.tolist()
    assert float64_cols == []
    assert feat["sell_price"].dtype == np.float32


@pytest.mark.parametrize("horizon", [7, 14, 28])
def test_zero_data_leakage_across_horizons(horizon: int) -> None:
    """Perturbing sales after cutoff (t - h) must not alter features at target date t."""
    df = load_processed_sales()
    target_date = pd.Timestamp(df["date"].max())
    cutoff_date = target_date - pd.Timedelta(days=horizon)

    orig_feat = build_horizon_features(df, horizon=horizon)
    orig_target = orig_feat[orig_feat["date"] == target_date].sort_values(["store_id", "item_id"])

    # Corrupt all sales strictly after cutoff_date (including target_date itself)
    perturbed = df.copy()
    mask_after_cutoff = perturbed["date"] > cutoff_date
    perturbed.loc[mask_after_cutoff, "sales"] = 9999

    pert_feat = build_horizon_features(perturbed, horizon=horizon)
    pert_target = pert_feat[pert_feat["date"] == target_date].sort_values(["store_id", "item_id"])

    leakage_sensitive_cols = [
        "lag_h",
        "lag_h_plus_7",
        "lag_h_plus_21",
        "rolling_mean_7_shift_h",
        "rolling_mean_28_shift_h",
        "rolling_std_28_shift_h",
        "price_change_4w",
    ]
    for col in leakage_sensitive_cols:
        assert np.allclose(
            orig_target[col].to_numpy(dtype=np.float64),
            pert_target[col].to_numpy(dtype=np.float64),
            equal_nan=True,
        ), f"Leakage detected in column {col} for horizon={horizon}"


def test_seasonal_naive_no_future_leakage() -> None:
    """Seasonal Naive forecasts after cutoff must ignore post-cutoff actuals."""
    df = load_processed_sales()
    cutoff = pd.Timestamp(df["date"].max()) - pd.Timedelta(days=28)

    pred_clean = predict_seasonal_naive(df, cutoff_date=cutoff, horizon=28)

    perturbed = df.copy()
    perturbed.loc[perturbed["date"] > cutoff, "sales"] = 8888
    pred_perturbed = predict_seasonal_naive(perturbed, cutoff_date=cutoff, horizon=28)

    assert np.allclose(pred_clean["prediction"].to_numpy(), pred_perturbed["prediction"].to_numpy())


def test_chronological_splits_strictly_ordered() -> None:
    """Train, validation, and 28-day test dates must never overlap."""
    df = load_processed_sales()
    val_start, test_start, max_date = chronological_split_dates(df, test_days=28, val_days=28)

    assert val_start < test_start <= max_date
    assert (max_date - test_start).days + 1 == 28
    assert (test_start - val_start).days == 28


def test_compute_metrics_accuracy_and_zero_guard() -> None:
    """Verify MAE, RMSE, WMAPE, Forecast Bias formulas and zero-sum safeguard."""
    y_true = np.array([10.0, 0.0, 5.0, 5.0])
    y_pred = np.array([12.0, 2.0, 4.0, 6.0])
    m = compute_metrics(y_true, y_pred)

    # errors = [+2, +2, -1, +1]; abs = [2, 2, 1, 1] -> MAE = 1.5
    assert m["mae"] == pytest.approx(1.5)
    # sq = [4, 4, 1, 1] -> mean = 2.5 -> sqrt = 1.5811
    assert m["rmse"] == pytest.approx(np.sqrt(2.5), abs=1e-4)
    # sum(abs) = 6, sum(y) = 20 -> WMAPE = 0.30
    assert m["wmape"] == pytest.approx(0.3)
    # sum(err) = +4, sum(y) = 20 -> Bias = +0.20
    assert m["forecast_bias"] == pytest.approx(0.2)

    zero_m = compute_metrics(np.zeros(4), np.zeros(4))
    assert zero_m == {"mae": 0.0, "rmse": 0.0, "wmape": 0.0, "forecast_bias": 0.0}


def test_end_to_end_lgbm_training_and_native_save(tmp_path: Path) -> None:
    """Train h=7/14/28 LightGBM Tweedie models on sample Parquet and persist future forecasts."""
    db_file = tmp_path / "test_inventory.db"
    result = run_forecasting_pipeline(
        models_dir=tmp_path,
        persist_to_sqlite=True,
        db_path=db_file,
    )
    summary = result["summary"]

    for h in (7, 14, 28):
        model_file = tmp_path / f"lgbm_h{h}.txt"
        assert model_file.exists()
        booster = lgb.Booster(model_file=str(model_file))
        assert booster.num_trees() > 0

        h_metrics = summary["horizon_metrics"][f"h{h}"]
        assert h_metrics["lightgbm"]["mae"] >= 0.0
        assert h_metrics["lightgbm"]["rmse"] >= 0.0
        assert h_metrics["seasonal_naive"]["mae"] >= 0.0

    assert (tmp_path / "model_metrics.json").exists()
    expected_skus = result["sales_df"]["item_id"].nunique()
    assert expected_skus > 0
    assert len(summary["per_sku_val_rmse"]) == expected_skus
    assert db_file.exists()


def test_real_m5_pipeline_with_synthetic_raw_csvs(tmp_path: Path) -> None:
    """Verify run_real_m5_pipeline balances categories, filters NaN prices, trains, and seeds DB."""
    import sqlite3
    from backend.src.run_real_m5_pipeline import run_pipeline

    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    num_days = 150
    dates = pd.date_range("2015-10-01", periods=num_days, freq="D")
    d_cols = [f"d_{i}" for i in range(1, num_days + 1)]

    cal_df = pd.DataFrame(
        {
            "date": dates.strftime("%Y-%m-%d"),
            "wm_yr_wk": [11535 + (i // 7) for i in range(num_days)],
            "weekday": dates.day_name(),
            "wday": [((d.weekday() + 2) % 7) + 1 for d in dates],
            "month": dates.month,
            "year": dates.year,
            "d": d_cols,
            "event_name_1": [None] * num_days,
            "event_type_1": [None] * num_days,
            "snap_CA": [1 if d.day <= 10 else 0 for d in dates],
            "snap_TX": [0] * num_days,
            "snap_WI": [0] * num_days,
        }
    )
    cal_df.to_csv(raw_dir / "calendar.csv", index=False)

    # 9 items in CA_1 (3 per category) + 1 item in TX_1 (must be filtered out)
    items = []
    for cat in ("FOODS", "HOBBIES", "HOUSEHOLD"):
        for idx in range(1, 4):
            items.append((f"{cat}_1_{idx:03d}_CA_1_validation", f"{cat}_1_{idx:03d}", f"{cat}_1", cat, "CA_1", "CA"))
    items.append(("FOODS_1_999_TX_1_validation", "FOODS_1_999", "FOODS_1", "FOODS", "TX_1", "TX"))

    rng = np.random.default_rng(7)
    sales_rows = []
    price_rows = []
    unique_wks = cal_df["wm_yr_wk"].unique()

    for row_id, item_id, dept_id, cat_id, store_id, state_id in items:
        row = {
            "id": row_id,
            "item_id": item_id,
            "dept_id": dept_id,
            "cat_id": cat_id,
            "store_id": store_id,
            "state_id": state_id,
        }
        for i, d_col in enumerate(d_cols):
            row[d_col] = int(rng.poisson(3.0))
        sales_rows.append(row)

        # Leave first week unstocked (omitted from sell_prices) to verify NaN price filtering
        for wk in unique_wks[1:]:
            price_rows.append(
                {
                    "store_id": store_id,
                    "item_id": item_id,
                    "wm_yr_wk": int(wk),
                    "sell_price": 4.99,
                }
            )

    pd.DataFrame(sales_rows).to_csv(raw_dir / "sales_train_validation.csv", index=False)
    pd.DataFrame(price_rows).to_csv(raw_dir / "sell_prices.csv", index=False)

    out_parquet = tmp_path / "m5_sales.parquet"
    out_models = tmp_path / "models"
    out_db = tmp_path / "m5.db"

    res = run_pipeline(
        raw_dir=raw_dir,
        output_parquet=out_parquet,
        store_id="CA_1",
        max_items=6,
        tail_days=145,
        models_dir=out_models,
        db_path=out_db,
    )

    assert out_parquet.exists()
    assert res["sku_count"] == 6
    assert res["category_counts"] == {"FOODS": 2, "HOBBIES": 2, "HOUSEHOLD": 2}
    for h in (7, 14, 28):
        assert (out_models / f"lgbm_h{h}.txt").exists()

    conn = sqlite3.connect(out_db)
    inv_cnt = conn.execute("SELECT COUNT(*) FROM inventory").fetchone()[0]
    conn.close()
    assert inv_cnt == 6
