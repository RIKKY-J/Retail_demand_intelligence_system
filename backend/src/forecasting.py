"""Demand forecasting module: Seasonal Naive baseline and Direct LightGBM.

Implements Section 7 of the implementation plan:
- Baseline: Seasonal Naive (7-day lag / weekly same-weekday repeat from cutoff).
- ML Model: Direct multi-horizon LightGBM (`objective="tweedie"`) for h = 7, 14, 28,
  saved as native `.txt` boosters (`model.booster_.save_model(...)`).
- Chronological train / validation / 28-day test holdout evaluation reporting
  MAE, RMSE, WMAPE, and Forecast Bias by horizon and category.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import lightgbm as lgb
import numpy as np
import pandas as pd
import yaml

from backend.src.data_processing import (
    MODEL_FEATURE_COLS,
    build_horizon_features,
    chronological_split_dates,
    load_processed_sales,
)
from backend.src.database import REPO_ROOT, db_session, init_db

CONFIG_PATH = REPO_ROOT / "configs" / "inventory_config.yaml"
DEFAULT_MODELS_DIR = REPO_ROOT / "models"


def load_config(config_path: Path = CONFIG_PATH) -> dict[str, Any]:
    with open(config_path, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def compute_metrics(y_true: np.ndarray, y_pred: np.ndarray) -> dict[str, float]:
    """Compute MAE, RMSE, WMAPE, and Forecast Bias with zero-sum safeguards."""
    y_t = np.asarray(y_true, dtype=np.float64)
    y_p = np.clip(np.asarray(y_pred, dtype=np.float64), 0.0, None)

    errors = y_p - y_t
    abs_errors = np.abs(errors)
    total_actual = float(np.sum(y_t))

    mae = float(np.mean(abs_errors)) if len(y_t) else 0.0
    rmse = float(np.sqrt(np.mean(errors ** 2))) if len(y_t) else 0.0
    wmape = float(np.sum(abs_errors) / total_actual) if total_actual > 0 else 0.0
    bias = float(np.sum(errors) / total_actual) if total_actual > 0 else 0.0

    return {
        "mae": round(mae, 4),
        "rmse": round(rmse, 4),
        "wmape": round(wmape, 4),
        "forecast_bias": round(bias, 4),
    }


def predict_seasonal_naive(
    df: pd.DataFrame,
    cutoff_date: pd.Timestamp,
    horizon: int,
) -> pd.DataFrame:
    """Predict `horizon` days after `cutoff_date` using 7-day lag seasonal naive.

    Each target date `cutoff_date + step` repeats the actual sales from the
    same weekday in the most recent pre-cutoff week (`cutoff_date - 6 .. cutoff_date`).
    """
    cutoff = pd.Timestamp(cutoff_date)
    pre_cutoff = df[df["date"] <= cutoff].copy()
    last_week = pre_cutoff[pre_cutoff["date"] >= cutoff - pd.Timedelta(days=6)].copy()
    last_week["py_wd"] = last_week["date"].dt.weekday

    wd_lookup = (
        last_week.sort_values("date")
        .groupby(["store_id", "item_id", "py_wd"], observed=True)["sales"]
        .last()
        .to_dict()
    )
    fallback_lookup = (
        pre_cutoff.groupby(["store_id", "item_id"], observed=True)["sales"]
        .mean()
        .to_dict()
    )

    future_dates = pd.date_range(start=cutoff + pd.Timedelta(days=1), periods=horizon, freq="D")
    skus = pre_cutoff[["store_id", "item_id", "cat_id", "dept_id"]].drop_duplicates()

    rows = []
    for _, sku in skus.iterrows():
        store_id = str(sku["store_id"])
        item_id = str(sku["item_id"])
        fallback = float(fallback_lookup.get((store_id, item_id), 0.0))
        for f_date in future_dates:
            val = float(wd_lookup.get((store_id, item_id, f_date.weekday()), fallback))
            rows.append(
                {
                    "store_id": store_id,
                    "item_id": item_id,
                    "cat_id": str(sku["cat_id"]),
                    "dept_id": str(sku["dept_id"]),
                    "date": f_date,
                    "horizon": horizon,
                    "prediction": max(0.0, round(val, 4)),
                }
            )
    return pd.DataFrame(rows)


def train_direct_lgbm_model(
    feat_df: pd.DataFrame,
    horizon: int,
    val_start: pd.Timestamp,
    test_start: pd.Timestamp,
    tweedie_variance_power: float = 1.2,
    models_dir: Path = DEFAULT_MODELS_DIR,
    random_state: int = 42,
) -> tuple[lgb.LGBMRegressor, pd.DataFrame, pd.DataFrame]:
    """Train a direct LightGBM (Tweedie) model for a single horizon `h`."""
    # Drop early rows where the full lag window is unavailable
    trainable = feat_df.dropna(subset=["lag_h", "lag_h_plus_7", "lag_h_plus_21"]).copy()

    train_df = trainable[trainable["date"] < val_start]
    val_df = trainable[(trainable["date"] >= val_start) & (trainable["date"] < test_start)]
    test_end = test_start + pd.Timedelta(days=horizon - 1)
    test_df = trainable[(trainable["date"] >= test_start) & (trainable["date"] <= test_end)].copy()

    X_train = train_df[MODEL_FEATURE_COLS]
    y_train = train_df["sales"].astype(np.float32)
    X_val = val_df[MODEL_FEATURE_COLS]
    y_val = val_df["sales"].astype(np.float32)

    model = lgb.LGBMRegressor(
        objective="tweedie",
        tweedie_variance_power=tweedie_variance_power,
        n_estimators=400,
        learning_rate=0.05,
        num_leaves=31,
        min_child_samples=20,
        subsample_for_bin=50000,
        colsample_bytree=0.85,
        subsample=0.85,
        subsample_freq=1,
        random_state=random_state,
        n_jobs=-1,
        verbose=-1,
    )

    model.fit(
        X_train,
        y_train,
        eval_X=X_val,
        eval_y=y_val,
        eval_metric="rmse",
        callbacks=[lgb.early_stopping(stopping_rounds=40, verbose=False)],
    )

    models_dir.mkdir(parents=True, exist_ok=True)
    model_path = models_dir / f"lgbm_h{horizon}.txt"
    model.booster_.save_model(str(model_path))

    val_out = val_df[["store_id", "item_id", "cat_id", "dept_id", "date", "sales"]].copy()
    val_out["prediction"] = np.clip(model.predict(X_val), 0.0, None)

    test_out = test_df[["store_id", "item_id", "cat_id", "dept_id", "date", "sales"]].copy()
    test_out["prediction"] = np.clip(model.predict(test_df[MODEL_FEATURE_COLS]), 0.0, None)
    test_out["horizon"] = horizon

    return model, val_out, test_out


def predict_future_with_booster(
    sales_df: pd.DataFrame,
    horizon: int,
    model_path: Path,
    cutoff_date: pd.Timestamp | None = None,
) -> pd.DataFrame:
    """Generate direct future forecasts for dates `cutoff + 1 .. cutoff + horizon`.

    Constructs future calendar/price scaffold rows for the next `horizon` days
    without touching any actual sales after `cutoff_date`, then scores with the
    saved native LightGBM `.txt` booster.
    """
    cutoff = pd.Timestamp(cutoff_date) if cutoff_date is not None else pd.Timestamp(sales_df["date"].max())
    hist = sales_df[sales_df["date"] <= cutoff].copy()

    # Latest known price and metadata per SKU
    latest_meta = (
        hist.sort_values("date")
        .groupby(["store_id", "item_id"], observed=True)
        .last()
        .reset_index()
    )

    future_dates = pd.date_range(start=cutoff + pd.Timedelta(days=1), periods=horizon, freq="D")
    scaffold_rows = []
    for _, sku in latest_meta.iterrows():
        for f_date in future_dates:
            scaffold_rows.append(
                {
                    "id": sku["id"],
                    "item_id": str(sku["item_id"]),
                    "dept_id": str(sku["dept_id"]),
                    "cat_id": str(sku["cat_id"]),
                    "store_id": str(sku["store_id"]),
                    "state_id": str(sku["state_id"]),
                    "date": f_date,
                    "year": np.int16(f_date.year),
                    "wm_yr_wk": np.int32(sku.get("wm_yr_wk", 0) or 0),
                    "sell_price": np.float32(sku["sell_price"]),
                    "sales": np.int32(0),  # placeholder only; shifted out by >= horizon
                    "snap_CA": np.int8(1 if f_date.day <= 10 else 0),
                    "snap_TX": np.int8(0),
                    "snap_WI": np.int8(0),
                    "event_name_1": "None",
                }
            )

    future_scaffold = pd.DataFrame(scaffold_rows)
    combined = pd.concat([hist, future_scaffold], ignore_index=True)
    feat_df = build_horizon_features(combined, horizon=horizon)

    target_rows = feat_df[feat_df["date"] > cutoff].copy()
    booster = lgb.Booster(model_file=str(model_path))
    preds = np.clip(booster.predict(target_rows[MODEL_FEATURE_COLS]), 0.0, None)
    target_rows["prediction"] = np.round(preds, 4)
    target_rows["horizon"] = horizon
    return target_rows[["store_id", "item_id", "cat_id", "dept_id", "date", "horizon", "prediction"]]


def run_forecasting_pipeline(
    parquet_path: str | Path | None = None,
    models_dir: str | Path | None = None,
    config_path: Path = CONFIG_PATH,
    persist_to_sqlite: bool = True,
    db_path: Path | None = None,
) -> dict[str, Any]:
    """Train h=7/14/28 LightGBM models, evaluate against Seasonal Naive, and save metrics."""
    config = load_config(config_path)
    horizons: list[int] = [int(h) for h in config["forecasting"]["horizons"]]
    tweedie_power = float(config["forecasting"]["tweedie_variance_power"])
    holdout_days = int(config["forecasting"]["backtest_holdout_days"])
    baseline_version = config["forecasting"]["baseline_model_version"]
    ml_version = config["forecasting"]["ml_model_version"]

    resolved_models_dir = Path(models_dir) if models_dir is not None else DEFAULT_MODELS_DIR
    if not resolved_models_dir.is_absolute():
        resolved_models_dir = REPO_ROOT / resolved_models_dir

    sales_df = load_processed_sales(parquet_path)
    val_start, test_start, max_date = chronological_split_dates(
        sales_df, test_days=holdout_days, val_days=holdout_days
    )
    cutoff_date = test_start - pd.Timedelta(days=1)

    horizon_metrics: dict[str, Any] = {}
    category_metrics_h28: dict[str, Any] = {}
    per_sku_val_rmse: dict[str, float] = {}
    per_sku_baseline_val_rmse: dict[str, float] = {}
    holdout_predictions: dict[str, pd.DataFrame] = {}

    # Baseline validation RMSE on val window (using cutoff before val_start)
    val_cutoff = val_start - pd.Timedelta(days=1)
    baseline_val_df = predict_seasonal_naive(sales_df, cutoff_date=val_cutoff, horizon=holdout_days)
    actual_val_slice = sales_df[(sales_df["date"] >= val_start) & (sales_df["date"] < test_start)][
        ["store_id", "item_id", "date", "sales"]
    ].copy()
    actual_val_slice["store_id"] = actual_val_slice["store_id"].astype(str)
    actual_val_slice["item_id"] = actual_val_slice["item_id"].astype(str)
    baseline_val_merged = baseline_val_df.merge(
        actual_val_slice, on=["store_id", "item_id", "date"], how="inner"
    )
    for (s_id, i_id), grp in baseline_val_merged.groupby(["store_id", "item_id"]):
        m = compute_metrics(grp["sales"].to_numpy(), grp["prediction"].to_numpy())
        per_sku_baseline_val_rmse[f"{s_id}::{i_id}"] = m["rmse"]

    for h in horizons:
        feat_df = build_horizon_features(sales_df, horizon=h)
        _, val_out, test_out = train_direct_lgbm_model(
            feat_df=feat_df,
            horizon=h,
            val_start=val_start,
            test_start=test_start,
            tweedie_variance_power=tweedie_power,
            models_dir=resolved_models_dir,
        )

        # Baseline holdout forecast for horizon h from exact same cutoff
        base_test_df = predict_seasonal_naive(sales_df, cutoff_date=cutoff_date, horizon=h)
        test_out_key = test_out.copy()
        test_out_key["store_id"] = test_out_key["store_id"].astype(str)
        test_out_key["item_id"] = test_out_key["item_id"].astype(str)
        merged = test_out_key.merge(
            base_test_df[["store_id", "item_id", "date", "prediction"]].rename(
                columns={"prediction": "baseline_pred"}
            ),
            on=["store_id", "item_id", "date"],
            how="inner",
        )

        lgbm_m = compute_metrics(merged["sales"].to_numpy(), merged["prediction"].to_numpy())
        base_m = compute_metrics(merged["sales"].to_numpy(), merged["baseline_pred"].to_numpy())
        horizon_metrics[f"h{h}"] = {
            "horizon_days": h,
            "samples": int(len(merged)),
            "lightgbm": lgbm_m,
            "seasonal_naive": base_m,
        }

        if h == holdout_days:
            holdout_predictions["lightgbm"] = merged[
                ["store_id", "item_id", "cat_id", "dept_id", "date", "sales", "prediction"]
            ].copy()
            holdout_predictions["seasonal_naive"] = merged[
                ["store_id", "item_id", "cat_id", "dept_id", "date", "sales", "baseline_pred"]
            ].rename(columns={"baseline_pred": "prediction"}).copy()

            # Per-SKU LightGBM validation RMSE for forecast-aware Safety Stock
            val_out_str = val_out.copy()
            val_out_str["store_id"] = val_out_str["store_id"].astype(str)
            val_out_str["item_id"] = val_out_str["item_id"].astype(str)
            for (s_id, i_id), grp in val_out_str.groupby(["store_id", "item_id"]):
                m = compute_metrics(grp["sales"].to_numpy(), grp["prediction"].to_numpy())
                per_sku_val_rmse[f"{s_id}::{i_id}"] = m["rmse"]

            # Category breakdown on 28-day holdout
            for cat_id, grp in merged.groupby("cat_id"):
                category_metrics_h28[str(cat_id)] = {
                    "lightgbm": compute_metrics(grp["sales"].to_numpy(), grp["prediction"].to_numpy()),
                    "seasonal_naive": compute_metrics(
                        grp["sales"].to_numpy(), grp["baseline_pred"].to_numpy()
                    ),
                }

    # Optionally update SQLite forecast_results with real trained booster future forecasts
    if persist_to_sqlite:
        resolved_db = init_db(db_path or config["storage"]["database_path"])
        now_iso = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        rows_to_insert = []
        for h in horizons:
            lgbm_future = predict_future_with_booster(
                sales_df=sales_df,
                horizon=h,
                model_path=resolved_models_dir / f"lgbm_h{h}.txt",
                cutoff_date=max_date,
            )
            base_future = predict_seasonal_naive(sales_df, cutoff_date=max_date, horizon=h)

            for row in lgbm_future.itertuples(index=False):
                sku_key = f"{row.store_id}::{row.item_id}"
                sku_rmse = per_sku_val_rmse.get(sku_key, 1.0)
                p95 = round(float(row.prediction) + 1.645 * sku_rmse, 4)
                rows_to_insert.append(
                    (
                        str(row.item_id),
                        str(row.store_id),
                        pd.Timestamp(row.date).strftime("%Y-%m-%d"),
                        float(row.prediction),
                        p95,
                        int(h),
                        ml_version,
                        now_iso,
                    )
                )

            for row in base_future.itertuples(index=False):
                rows_to_insert.append(
                    (
                        str(row.item_id),
                        str(row.store_id),
                        pd.Timestamp(row.date).strftime("%Y-%m-%d"),
                        float(row.prediction),
                        None,
                        int(h),
                        baseline_version,
                        now_iso,
                    )
                )

        meta_rows = (
            sales_df[["item_id", "store_id", "dept_id", "cat_id", "state_id"]]
            .drop_duplicates()
            .astype(str)
            .itertuples(index=False, name=None)
        )

        with db_session(resolved_db) as conn:
            conn.executemany(
                """
                INSERT OR IGNORE INTO product_metadata (
                    item_id, store_id, dept_id, cat_id, state_id
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                list(meta_rows),
            )
            conn.execute("DELETE FROM forecast_results;")
            conn.executemany(
                """
                INSERT INTO forecast_results (
                    item_id, store_id, forecast_date, prediction, prediction_p95,
                    horizon, model_version, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                rows_to_insert,
            )

    summary = {
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "split": {
            "val_start": val_start.strftime("%Y-%m-%d"),
            "test_start": test_start.strftime("%Y-%m-%d"),
            "test_end": max_date.strftime("%Y-%m-%d"),
            "holdout_days": holdout_days,
        },
        "horizon_metrics": horizon_metrics,
        "category_metrics_h28": category_metrics_h28,
        "per_sku_val_rmse": per_sku_val_rmse,
        "per_sku_baseline_val_rmse": per_sku_baseline_val_rmse,
    }

    metrics_path = resolved_models_dir / "model_metrics.json"
    with open(metrics_path, "w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=2)

    return {
        "summary": summary,
        "holdout_predictions": holdout_predictions,
        "sales_df": sales_df,
        "metrics_path": metrics_path,
    }
