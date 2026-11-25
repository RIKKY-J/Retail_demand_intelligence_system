"""Train and compare 4 forecasting models, save the best model, and seed SQLite.

Models compared on a strict 28-day chronological test holdout:
1. 7-Day Moving Average (baseline)
2. Linear Regression (scikit-learn)
3. Random Forest Regressor (scikit-learn)
4. LightGBM Regressor (default MSE objective)

Outputs:
- `models/model.pkl`      Best model bundle (selected by lowest 28-day RMSE)
- `models/metrics.json`   4-model MAE/RMSE/WMAPE table, per-SKU RMSE, 28d holdout
- `data/forecasts.csv`    Next 7-day demand forecast per SKU
- `data/inventory.db`     Single-table SQLite `inventory` table
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from lightgbm import LGBMRegressor
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import LinearRegression

from backend.inventory import DB_PATH, calculate_reorder_point, calculate_safety_stock

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_CSV = REPO_ROOT / "data" / "m5_subset.csv"
FORECASTS_CSV = REPO_ROOT / "data" / "forecasts.csv"
MODEL_PKL = REPO_ROOT / "models" / "model.pkl"
METRICS_JSON = REPO_ROOT / "models" / "metrics.json"

FEATURE_COLS = [
    "item_code",
    "cat_code",
    "lag_7",
    "lag_14",
    "rolling_mean_7",
    "rolling_mean_28",
    "day_of_week",
    "month",
    "sell_price",
    "snap_CA",
]


def compute_metrics(y_true: np.ndarray, y_pred: np.ndarray) -> dict[str, float]:
    """Calculate MAE, RMSE, and WMAPE with predictions clipped at >= 0."""
    y_t = np.asarray(y_true, dtype=np.float64)
    y_p = np.clip(np.asarray(y_pred, dtype=np.float64), 0.0, None)

    abs_err = np.abs(y_p - y_t)
    mae = float(np.mean(abs_err))
    rmse = float(np.sqrt(np.mean((y_p - y_t) ** 2)))
    total_actual = float(np.sum(y_t))
    wmape = float(np.sum(abs_err) / total_actual) if total_actual > 0 else 0.0

    return {
        "mae": round(mae, 4),
        "rmse": round(rmse, 4),
        "wmape": round(wmape, 4),
    }


def generate_next_7_days_forecast(
    df: pd.DataFrame,
    best_model_name: str,
    best_model,
    item_map: dict[str, int],
    cat_map: dict[str, int],
) -> pd.DataFrame:
    """Forecast the next 7 days after `max_date` using 7-day-shifted features."""
    max_date = pd.Timestamp(df["date"].max())
    rows = []

    for item_id, grp in df.groupby("item_id"):
        grp = grp.sort_values("date")
        cat_id = str(grp["cat_id"].iloc[0])
        latest_price = float(grp["sell_price"].iloc[-1])

        # Lookup sales by date for exact lag_7 and lag_14
        sales_by_date = dict(zip(grp["date"], grp["sales"]))
        last_sales = grp["sales"].to_numpy(dtype=np.float64)

        for step in range(1, 8):
            f_date = max_date + timedelta(days=step)
            lag_7_date = f_date - timedelta(days=7)
            lag_14_date = f_date - timedelta(days=14)

            lag_7 = float(sales_by_date.get(lag_7_date, last_sales[-7] if len(last_sales) >= 7 else last_sales.mean()))
            lag_14 = float(sales_by_date.get(lag_14_date, last_sales[-14] if len(last_sales) >= 14 else last_sales.mean()))

            # Window ending at lag_7_date (strictly historical, no future leakage)
            hist_up_to_lag7 = grp[grp["date"] <= lag_7_date]["sales"].to_numpy(dtype=np.float64)
            rm_7 = float(np.mean(hist_up_to_lag7[-7:])) if len(hist_up_to_lag7) > 0 else lag_7
            rm_28 = float(np.mean(hist_up_to_lag7[-28:])) if len(hist_up_to_lag7) > 0 else lag_7

            if best_model_name == "7-Day Moving Average":
                pred = max(0.0, rm_7)
            else:
                feat_row = pd.DataFrame(
                    [
                        {
                            "item_code": item_map[item_id],
                            "cat_code": cat_map[cat_id],
                            "lag_7": lag_7,
                            "lag_14": lag_14,
                            "rolling_mean_7": rm_7,
                            "rolling_mean_28": rm_28,
                            "day_of_week": f_date.weekday(),
                            "month": f_date.month,
                            "sell_price": latest_price,
                            "snap_CA": 1 if f_date.day <= 10 else 0,
                        }
                    ]
                )
                pred = float(np.clip(best_model.predict(feat_row[FEATURE_COLS])[0], 0.0, None))

            rows.append(
                {
                    "item_id": item_id,
                    "cat_id": cat_id,
                    "forecast_date": f_date.strftime("%Y-%m-%d"),
                    "predicted_sales": round(pred, 2),
                    "model_name": best_model_name,
                }
            )

    return pd.DataFrame(rows)


def seed_inventory_db(
    df: pd.DataFrame,
    forecasts_df: pd.DataFrame,
    per_sku_rmse: dict[str, float],
    db_path: Path = DB_PATH,
) -> None:
    """Seed single-table SQLite DB with balanced Low Stock, Healthy, and Overstock SKUs."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    now_iso = datetime.now(timezone.utc).replace(microsecond=0).isoformat()

    catalog = (
        df[["item_id", "cat_id"]]
        .drop_duplicates()
        .sort_values(["cat_id", "item_id"])
        .reset_index(drop=True)
    )
    # Round-robin interleave across categories so statuses are balanced in FOODS/HOBBIES/HOUSEHOLD
    catalog["_cat_seq"] = catalog.groupby("cat_id").cumcount()
    catalog = catalog.sort_values(["_cat_seq", "cat_id", "item_id"]).reset_index(drop=True)

    total = len(catalog)
    rows_to_insert = []
    for pos, row in catalog.iterrows():
        item_id = str(row["item_id"])
        cat_id = str(row["cat_id"])
        lead_time = 3 + (pos % 5)  # 3 to 7 days

        sku_fc = forecasts_df[forecasts_df["item_id"] == item_id]["predicted_sales"].tolist()
        sku_rmse = per_sku_rmse.get(item_id, 1.0)
        ss = calculate_safety_stock(sku_rmse, lead_time)
        rop = calculate_reorder_point(sku_fc, lead_time, ss)

        ratio = pos / max(1, total)
        if ratio < 0.30:
            # Low Stock (Reorder): current_stock <= reorder_point
            current_stock = max(0, int(np.floor(rop * 0.55)))
        elif ratio < 0.80:
            # Healthy: reorder_point < current_stock <= 2.0 * reorder_point
            current_stock = max(1, int(np.ceil(rop * 1.35)))
        else:
            # Overstock: current_stock > 2.0 * reorder_point
            current_stock = max(5, int(np.ceil(rop * 2.40)) + 2)

        rows_to_insert.append((item_id, cat_id, current_stock, lead_time, now_iso))

    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS inventory (
                item_id TEXT PRIMARY KEY,
                cat_id TEXT NOT NULL,
                current_stock INTEGER NOT NULL,
                lead_time_days INTEGER NOT NULL,
                updated_at TEXT NOT NULL
            );
            """
        )
        conn.execute("DELETE FROM inventory;")
        conn.executemany(
            """
            INSERT INTO inventory (item_id, cat_id, current_stock, lead_time_days, updated_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            rows_to_insert,
        )
        conn.commit()
    finally:
        conn.close()
    print(f"Seeded {len(rows_to_insert)} SKUs into SQLite DB: {db_path}")


def run_training() -> dict:
    """Train 4 models, evaluate on 28-day holdout, save artifacts, and seed SQLite."""
    df = pd.read_csv(DATA_CSV)
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values(["item_id", "date"]).reset_index(drop=True)

    # Deterministic integer encoding for item_id and cat_id
    items = sorted(df["item_id"].unique().tolist())
    cats = sorted(df["cat_id"].unique().tolist())
    item_map = {v: i for i, v in enumerate(items)}
    cat_map = {v: i for i, v in enumerate(cats)}
    df["item_code"] = df["item_id"].map(item_map)
    df["cat_code"] = df["cat_id"].map(cat_map)

    # Strict chronological split: last 28 days = test set
    max_date = df["date"].max()
    test_start = max_date - pd.Timedelta(days=27)
    train_df = df[df["date"] < test_start].copy()
    test_df = df[df["date"] >= test_start].copy()

    X_train, y_train = train_df[FEATURE_COLS], train_df["sales"].to_numpy()
    X_test, y_test = test_df[FEATURE_COLS], test_df["sales"].to_numpy()

    models = {
        "Linear Regression": LinearRegression(),
        "Random Forest": RandomForestRegressor(
            n_estimators=50, max_depth=12, random_state=42, n_jobs=-1
        ),
        "LightGBM": LGBMRegressor(random_state=42, verbose=-1),
    }

    comparison = []
    predictions_by_model: dict[str, np.ndarray] = {}

    # 1. Baseline: 7-Day Moving Average
    ma_preds = np.clip(test_df["rolling_mean_7"].to_numpy(), 0.0, None)
    predictions_by_model["7-Day Moving Average"] = ma_preds
    comparison.append(
        {"model": "7-Day Moving Average", **compute_metrics(y_test, ma_preds)}
    )

    # 2-4. Standard ML Models
    trained_objects: dict[str, object] = {}
    for name, est in models.items():
        est.fit(X_train, y_train)
        preds = np.clip(est.predict(X_test), 0.0, None)
        predictions_by_model[name] = preds
        trained_objects[name] = est
        comparison.append({"model": name, **compute_metrics(y_test, preds)})

    # Select best model by lowest RMSE
    best_row = min(comparison, key=lambda r: r["rmse"])
    best_name = best_row["model"]
    best_estimator = trained_objects.get(best_name)
    best_preds = predictions_by_model[best_name]

    MODEL_PKL.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(
        {
            "model_name": best_name,
            "model": best_estimator,
            "feature_cols": FEATURE_COLS,
            "item_map": item_map,
            "cat_map": cat_map,
        },
        MODEL_PKL,
    )

    # Per-SKU RMSE and 28-day holdout comparison series using the best model
    test_eval = test_df[["item_id", "date", "sales"]].copy()
    test_eval["predicted_sales"] = np.round(best_preds, 2)

    per_sku_rmse: dict[str, float] = {}
    holdout_series: dict[str, list[dict]] = {}
    for item_id, grp in test_eval.groupby("item_id"):
        grp = grp.sort_values("date")
        m = compute_metrics(grp["sales"].to_numpy(), grp["predicted_sales"].to_numpy())
        per_sku_rmse[str(item_id)] = m["rmse"]
        holdout_series[str(item_id)] = [
            {
                "date": pd.Timestamp(r.date).strftime("%Y-%m-%d"),
                "actual_sales": int(r.sales),
                "predicted_sales": float(r.predicted_sales),
            }
            for r in grp.itertuples(index=False)
        ]

    # Next 7-day forecast
    forecasts_df = generate_next_7_days_forecast(
        df=df,
        best_model_name=best_name,
        best_model=best_estimator,
        item_map=item_map,
        cat_map=cat_map,
    )
    FORECASTS_CSV.parent.mkdir(parents=True, exist_ok=True)
    forecasts_df.to_csv(FORECASTS_CSV, index=False)

    metrics_payload = {
        "best_model": best_name,
        "split": {
            "train_end": (test_start - pd.Timedelta(days=1)).strftime("%Y-%m-%d"),
            "test_start": test_start.strftime("%Y-%m-%d"),
            "test_end": max_date.strftime("%Y-%m-%d"),
            "test_days": 28,
        },
        "model_comparison": comparison,
        "per_sku_rmse": per_sku_rmse,
        "holdout_series": holdout_series,
    }
    with open(METRICS_JSON, "w", encoding="utf-8") as fh:
        json.dump(metrics_payload, fh, indent=2)

    seed_inventory_db(df=df, forecasts_df=forecasts_df, per_sku_rmse=per_sku_rmse)

    print("\n=== 4-MODEL EVALUATION (28-DAY TEST SET) ===")
    for row in comparison:
        marker = " <-- BEST" if row["model"] == best_name else ""
        print(
            f"  {row['model']:22s} | MAE={row['mae']:.4f} | "
            f"RMSE={row['rmse']:.4f} | WMAPE={row['wmape']:.4f}{marker}"
        )
    return metrics_payload


if __name__ == "__main__":
    run_training()
