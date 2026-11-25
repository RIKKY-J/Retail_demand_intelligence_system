"""Generate realistic M5-formatted sample Parquet data and seed SQLite.

Creates:
1. `data/processed/sample_sales.parquet` — 50 SKUs x 1 store (CA_1) x 400 days.
2. `data/retail_inventory.db` — Seeded `product_metadata`, `inventory`,
   `inventory_transactions`, and `forecast_results` (Seasonal Naive + LightGBM).
3. `data/mock/forecast_results.csv` — 10-SKU Day-1 mock forecast contract.

Run from the repository root:
    python -m backend.src.seed_mock_data
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from backend.src.database import REPO_ROOT, db_session, get_db_path, init_db

CONFIG_PATH = REPO_ROOT / "configs" / "inventory_config.yaml"

# Fixed US retail calendar events aligned with M5 event conventions
CALENDAR_EVENTS: dict[str, tuple[str, str]] = {
    "2015-04-05": ("Easter", "Cultural"),
    "2015-05-25": ("MemorialDay", "National"),
    "2015-07-04": ("IndependenceDay", "National"),
    "2015-09-07": ("LaborDay", "National"),
    "2015-10-31": ("Halloween", "Cultural"),
    "2015-11-26": ("Thanksgiving", "National"),
    "2015-12-25": ("Christmas", "National"),
    "2016-01-01": ("NewYear", "National"),
    "2016-02-07": ("SuperBowl", "Sporting"),
    "2016-02-14": ("ValentinesDay", "Cultural"),
    "2016-03-27": ("Easter", "Cultural"),
}

# 50 SKUs across 3 M5 categories and 7 departments
SKU_BLUEPRINT: list[tuple[str, int]] = [
    ("FOODS_1", 6),
    ("FOODS_2", 6),
    ("FOODS_3", 8),
    ("HOUSEHOLD_1", 8),
    ("HOUSEHOLD_2", 7),
    ("HOBBIES_1", 8),
    ("HOBBIES_2", 7),
]


def load_config(config_path: Path = CONFIG_PATH) -> dict:
    """Load central inventory and forecasting configuration."""
    with open(config_path, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def build_sku_catalog(store_id: str = "CA_1", state_id: str = "CA") -> pd.DataFrame:
    """Create metadata for 50 realistic M5-style SKUs."""
    rows = []
    for dept_id, count in SKU_BLUEPRINT:
        cat_id = dept_id.split("_")[0]
        for idx in range(1, count + 1):
            item_id = f"{dept_id}_{idx:03d}"
            rows.append(
                {
                    "item_id": item_id,
                    "store_id": store_id,
                    "dept_id": dept_id,
                    "cat_id": cat_id,
                    "state_id": state_id,
                }
            )
    return pd.DataFrame(rows)


def generate_sample_sales(
    catalog: pd.DataFrame,
    num_days: int = 400,
    end_date: str = "2016-04-24",
    seed: int = 42,
) -> pd.DataFrame:
    """Generate 400 days of M5-formatted long sales data for 50 SKUs in CA_1."""
    rng = np.random.default_rng(seed)
    end_dt = pd.Timestamp(end_date)
    dates = pd.date_range(end=end_dt, periods=num_days, freq="D")

    # Build calendar lookup
    cal_rows = []
    start_wk_base = 11508
    for day_idx, dt in enumerate(dates, start=1):
        date_str = dt.strftime("%Y-%m-%d")
        event_name, event_type = CALENDAR_EVENTS.get(date_str, (None, None))
        # M5 wday: Saturday=1, Sunday=2, Monday=3 ... Friday=7
        py_wd = dt.weekday()  # Mon=0 .. Sun=6
        m5_wday = ((py_wd + 2) % 7) + 1
        wm_yr_wk = start_wk_base + ((day_idx - 1) // 7)
        cal_rows.append(
            {
                "d": f"d_{day_idx}",
                "date": dt,
                "wm_yr_wk": np.int32(wm_yr_wk),
                "weekday": dt.day_name(),
                "wday": np.int8(m5_wday),
                "month": np.int8(dt.month),
                "year": np.int16(dt.year),
                "event_name_1": event_name,
                "event_type_1": event_type,
                "snap_CA": np.int8(1 if dt.day <= 10 else 0),
                "snap_TX": np.int8(1 if dt.day in (1, 3, 5, 6, 7, 9, 11, 12, 13, 15) else 0),
                "snap_WI": np.int8(1 if dt.day in (2, 3, 5, 6, 8, 9, 11, 12, 14, 15) else 0),
            }
        )
    cal_df = pd.DataFrame(cal_rows)

    # Assign per-SKU demand characteristics (high, medium, slow/intermittent)
    records = []
    for sku_idx, sku in catalog.iterrows():
        item_id = sku["item_id"]
        cat_id = sku["cat_id"]
        dept_id = sku["dept_id"]
        store_id = sku["store_id"]
        state_id = sku["state_id"]

        # Base price by category
        if cat_id == "FOODS":
            base_price = float(np.round(rng.uniform(1.78, 7.98), 2))
            base_rate = float(rng.uniform(1.8, 12.0))
        elif cat_id == "HOUSEHOLD":
            base_price = float(np.round(rng.uniform(3.48, 14.98), 2))
            base_rate = float(rng.uniform(0.8, 6.5))
        else:  # HOBBIES
            base_price = float(np.round(rng.uniform(2.98, 19.98), 2))
            base_rate = float(rng.uniform(0.4, 4.5))

        # Make ~20% of SKUs slow/intermittent movers
        is_intermittent = sku_idx % 5 == 4
        if is_intermittent:
            base_rate *= 0.35

        # Weekly price series (occasional promo markdowns)
        unique_weeks = cal_df["wm_yr_wk"].unique()
        week_prices = {}
        current_price = base_price
        for wk in unique_weeks:
            if rng.random() < 0.08:
                # Temporary 15% promo or small price drift
                promo = rng.choice([0.85, 0.90, 1.0, 1.05], p=[0.35, 0.25, 0.30, 0.10])
                current_price = round(max(0.98, base_price * promo), 2)
            else:
                current_price = base_price
            week_prices[int(wk)] = current_price

        # Simulate daily sales with seasonality, SNAP, promos, and events
        series_id = f"{item_id}_{store_id}_validation"
        for _, c in cal_df.iterrows():
            price = week_prices[int(c["wm_yr_wk"])]
            # Weekend boost (Fri/Sat/Sun -> m5_wday in {1, 2, 7})
            weekend_mult = 1.28 if c["wday"] in (1, 2, 7) else 0.92
            # Annual seasonal wave
            day_of_year = c["date"].dayofyear
            seasonal_mult = 1.0 + 0.15 * math.sin(2.0 * math.pi * day_of_year / 365.0)
            # SNAP effect strongest on FOODS
            snap_mult = 1.18 if (cat_id == "FOODS" and c["snap_CA"] == 1) else 1.0
            # Event uplift
            event_mult = 1.30 if c["event_name_1"] is not None else 1.0
            # Price elasticity
            price_mult = (base_price / price) ** 1.2

            lam = max(0.05, base_rate * weekend_mult * seasonal_mult * snap_mult * event_mult * price_mult)

            if is_intermittent and rng.random() < 0.35:
                units = 0
            else:
                units = int(rng.poisson(lam))

            records.append(
                {
                    "id": series_id,
                    "item_id": item_id,
                    "dept_id": dept_id,
                    "cat_id": cat_id,
                    "store_id": store_id,
                    "state_id": state_id,
                    "d": c["d"],
                    "date": c["date"],
                    "wm_yr_wk": c["wm_yr_wk"],
                    "weekday": c["weekday"],
                    "wday": c["wday"],
                    "month": c["month"],
                    "year": c["year"],
                    "event_name_1": c["event_name_1"],
                    "event_type_1": c["event_type_1"],
                    "snap_CA": c["snap_CA"],
                    "snap_TX": c["snap_TX"],
                    "snap_WI": c["snap_WI"],
                    "sell_price": np.float32(price),
                    "sales": np.int32(units),
                }
            )

    df = pd.DataFrame(records)
    # Downcast string/categorical columns cleanly for compact Parquet storage
    for col in ["item_id", "dept_id", "cat_id", "store_id", "state_id", "weekday"]:
        df[col] = df[col].astype("category")
    return df


def build_mock_forecasts(
    sales_df: pd.DataFrame,
    horizons: list[int],
    baseline_version: str,
    ml_version: str,
    seed: int = 42,
) -> pd.DataFrame:
    """Generate Seasonal Naive and LightGBM mock forecasts for 7, 14, and 28 days."""
    rng = np.random.default_rng(seed + 100)
    last_date = pd.Timestamp(sales_df["date"].max())
    created_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()

    # Compute 28-day trailing weekday averages per SKU for realistic predictions
    recent_cutoff = last_date - timedelta(days=27)
    recent_df = sales_df[sales_df["date"] >= recent_cutoff].copy()
    recent_df["py_wd"] = recent_df["date"].dt.weekday

    # Most recent 7 days for exact seasonal naive (same weekday last week)
    last_week_cutoff = last_date - timedelta(days=6)
    last_week_df = sales_df[sales_df["date"] >= last_week_cutoff].copy()
    last_week_df["py_wd"] = last_week_df["date"].dt.weekday

    naive_lookup = (
        last_week_df.set_index(["item_id", "store_id", "py_wd"])["sales"].to_dict()
    )
    mean_wd_lookup = (
        recent_df.groupby(["item_id", "store_id", "py_wd"], observed=True)["sales"]
        .mean()
        .to_dict()
    )
    overall_mean_lookup = (
        recent_df.groupby(["item_id", "store_id"], observed=True)["sales"]
        .mean()
        .to_dict()
    )

    sku_pairs = (
        sales_df[["item_id", "store_id"]]
        .drop_duplicates()
        .astype(str)
        .to_records(index=False)
    )

    forecast_rows = []
    for item_id, store_id in sku_pairs:
        sku_mean = float(overall_mean_lookup.get((item_id, store_id), 1.0))
        for horizon in horizons:
            for step in range(1, horizon + 1):
                f_date = last_date + timedelta(days=step)
                f_date_str = f_date.strftime("%Y-%m-%d")
                py_wd = f_date.weekday()

                # Baseline: seasonal naive (same weekday last week)
                naive_val = float(naive_lookup.get((item_id, store_id, py_wd), sku_mean))
                naive_pred = round(max(0.0, naive_val), 2)

                forecast_rows.append(
                    {
                        "item_id": item_id,
                        "store_id": store_id,
                        "forecast_date": f_date_str,
                        "prediction": naive_pred,
                        "prediction_p95": None,
                        "horizon": int(horizon),
                        "model_version": baseline_version,
                        "created_at": created_at,
                    }
                )

                # LightGBM mock: 4-week same-weekday mean + SNAP lift + small jitter
                wd_mean = float(mean_wd_lookup.get((item_id, store_id, py_wd), sku_mean))
                snap_lift = 1.12 if (item_id.startswith("FOODS") and f_date.day <= 10) else 1.0
                noise = float(rng.normal(1.0, 0.05))
                ml_pred = round(max(0.0, wd_mean * snap_lift * noise), 2)
                # Realistic 95th percentile upper bound for Tweedie/Poisson count demand
                ml_p95 = round(max(ml_pred * 1.45, ml_pred + 1.645 * math.sqrt(max(ml_pred, 0.3))), 2)

                forecast_rows.append(
                    {
                        "item_id": item_id,
                        "store_id": store_id,
                        "forecast_date": f_date_str,
                        "prediction": ml_pred,
                        "prediction_p95": ml_p95,
                        "horizon": int(horizon),
                        "model_version": ml_version,
                        "created_at": created_at,
                    }
                )

    return pd.DataFrame(forecast_rows)


def seed_sqlite(
    catalog: pd.DataFrame,
    sales_df: pd.DataFrame,
    forecasts_df: pd.DataFrame,
    config: dict,
    db_path: Path | None = None,
) -> Path:
    """Populate SQLite tables cleanly with product metadata, inventory, transactions, and forecasts."""
    resolved_db = init_db(db_path)
    now_iso = datetime.now(timezone.utc).replace(microsecond=0).isoformat()

    inv_cfg = config["inventory"]
    thresh_cfg = config["thresholds"]
    ml_version = config["forecasting"]["ml_model_version"]
    z_score = float(inv_cfg["service_level_z"])
    overstock_mult = float(thresh_cfg["overstock_multiplier"])

    # Latest sell_price per SKU to derive simulated unit_cost (~65% of retail price)
    latest_prices = (
        sales_df.sort_values("date")
        .groupby(["item_id", "store_id"], observed=True)["sell_price"]
        .last()
        .to_dict()
    )
    # Daily RMSE proxy from trailing 28 days for realistic initial stock positioning
    last_date = pd.Timestamp(sales_df["date"].max())
    trailing_28 = sales_df[sales_df["date"] >= last_date - timedelta(days=27)]
    sku_std = (
        trailing_28.groupby(["item_id", "store_id"], observed=True)["sales"]
        .std()
        .fillna(1.0)
        .to_dict()
    )

    ml_h28 = forecasts_df[
        (forecasts_df["horizon"] == 28) & (forecasts_df["model_version"] == ml_version)
    ].sort_values("forecast_date")

    with db_session(resolved_db) as conn:
        # Clear existing seed data in FK-safe order for idempotency
        conn.execute("DELETE FROM inventory_transactions;")
        conn.execute("DELETE FROM forecast_results;")
        conn.execute("DELETE FROM inventory;")
        conn.execute("DELETE FROM product_metadata;")

        # 1. product_metadata
        conn.executemany(
            """
            INSERT INTO product_metadata (item_id, store_id, dept_id, cat_id, state_id)
            VALUES (?, ?, ?, ?, ?)
            """,
            catalog[["item_id", "store_id", "dept_id", "cat_id", "state_id"]].itertuples(
                index=False, name=None
            ),
        )

        # 2. forecast_results
        conn.executemany(
            """
            INSERT INTO forecast_results (
                item_id, store_id, forecast_date, prediction, prediction_p95,
                horizon, model_version, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    row.item_id,
                    row.store_id,
                    row.forecast_date,
                    float(row.prediction),
                    None if pd.isna(row.prediction_p95) else float(row.prediction_p95),
                    int(row.horizon),
                    row.model_version,
                    row.created_at,
                )
                for row in forecasts_df.itertuples(index=False)
            ],
        )

        # 3. inventory & inventory_transactions (round-robin interleaved across categories)
        inv_rows = []
        txn_rows = []
        total_skus = max(1, len(catalog))
        interleaved_catalog = (
            catalog.assign(
                _cat_seq=catalog.groupby("cat_id", sort=True).cumcount(),
            )
            .sort_values(["_cat_seq", "cat_id", "item_id"])
            .drop(columns=["_cat_seq"])
            .reset_index(drop=True)
        )
        for pos, (_, sku) in enumerate(interleaved_catalog.iterrows()):
            item_id = sku["item_id"]
            store_id = sku["store_id"]
            lead_time = 3 + (pos % 5)  # 3 to 7 days
            review_period = int(inv_cfg["default_review_period_days"])
            retail_price = float(latest_prices.get((item_id, store_id), 5.0))
            unit_cost = round(retail_price * 0.65, 2)

            sku_preds = ml_h28[
                (ml_h28["item_id"] == item_id) & (ml_h28["store_id"] == store_id)
            ]["prediction"].to_numpy()
            lead_demand = float(sku_preds[:lead_time].sum()) if len(sku_preds) >= lead_time else 10.0
            review_demand = float(sku_preds[: lead_time + review_period].sum())
            rmse_proxy = max(0.5, float(sku_std.get((item_id, store_id), 1.0)) * 0.8)
            safety_stock = z_score * rmse_proxy * math.sqrt(lead_time)
            rop = lead_demand + safety_stock
            target_stock = review_demand + safety_stock

            # Distribute SKUs proportionally across all 4 alert states from Section 8:
            # < 0.50: Healthy (~50%) | < 0.70: Reorder required (~20%) | < 0.86: Stockout (~16%) | >= 0.86: Overstock (~14%)
            ratio = pos / total_skus
            if ratio < 0.50:
                on_hand = max(1, int(round(target_stock * 1.1)))
                on_order = 0
                backorders = 0
                note = "Seeded initial healthy stock"
            elif ratio < 0.70:
                # IP <= ROP while keeping on_hand >= lead_demand (reorder required, not yet immediate stockout)
                on_hand = max(1, int(math.ceil(lead_demand + 0.25 * safety_stock)))
                if on_hand > int(math.floor(rop)):
                    on_hand = max(1, int(math.floor(rop)))
                on_order = 0
                backorders = 0
                note = "Seeded below reorder point"
            elif ratio < 0.86:
                # On-hand < lead_demand -> Potential stockout
                on_hand = max(0, int(math.floor(lead_demand * 0.45)))
                on_order = int(round(review_demand * 0.3)) if pos % 2 == 0 else 0
                backorders = 2 if on_hand == 0 else 0
                note = "Seeded low stock / potential stockout"
            else:
                # On-hand > 1.5 * Target Stock -> Possible overstock
                on_hand = max(5, int(math.ceil(target_stock * (overstock_mult + 0.45))))
                on_order = 0
                backorders = 0
                note = "Seeded excess stock"

            inv_rows.append(
                (
                    item_id,
                    store_id,
                    on_hand,
                    on_order,
                    backorders,
                    lead_time,
                    review_period,
                    unit_cost,
                    now_iso,
                )
            )

            # Audit log: opening stock + realistic recent transaction sample
            txn_rows.append(
                (
                    item_id,
                    store_id,
                    "opening_stock",
                    on_hand + 4,
                    (last_date - timedelta(days=2)).strftime("%Y-%m-%d"),
                    note,
                )
            )
            txn_rows.append(
                (
                    item_id,
                    store_id,
                    "simulated_sale",
                    -4,
                    last_date.strftime("%Y-%m-%d"),
                    "Initial simulated daily depletion",
                )
            )
            if on_order > 0:
                txn_rows.append(
                    (
                        item_id,
                        store_id,
                        "manual_adjustment",
                        on_order,
                        now_iso,
                        "Open replenishment purchase order seeded",
                    )
                )

        conn.executemany(
            """
            INSERT INTO inventory (
                item_id, store_id, on_hand, on_order, backorders,
                lead_time_days, review_period_days, unit_cost, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            inv_rows,
        )
        conn.executemany(
            """
            INSERT INTO inventory_transactions (
                item_id, store_id, transaction_type, quantity, transaction_date, notes
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            txn_rows,
        )

    return resolved_db


def main() -> None:
    config = load_config()
    store_id = config["project"]["default_store_id"]
    horizons = config["forecasting"]["horizons"]
    baseline_version = config["forecasting"]["baseline_model_version"]
    ml_version = config["forecasting"]["ml_model_version"]

    parquet_path = REPO_ROOT / config["storage"]["processed_sales_path"]
    mock_csv_path = REPO_ROOT / config["storage"]["mock_forecasts_path"]
    db_path = get_db_path(config["storage"]["database_path"])

    parquet_path.parent.mkdir(parents=True, exist_ok=True)
    mock_csv_path.parent.mkdir(parents=True, exist_ok=True)

    catalog = build_sku_catalog(store_id=store_id, state_id="CA")
    sales_df = generate_sample_sales(catalog=catalog, num_days=400)
    sales_df.to_parquet(parquet_path, index=False, engine="pyarrow")

    forecasts_df = build_mock_forecasts(
        sales_df=sales_df,
        horizons=horizons,
        baseline_version=baseline_version,
        ml_version=ml_version,
    )

    # Save 10-SKU Day-1 mock CSV contract in data/mock/forecast_results.csv
    sample_items = catalog["item_id"].head(10).tolist()
    mock_subset = forecasts_df[
        (forecasts_df["item_id"].isin(sample_items)) & (forecasts_df["horizon"] == 28)
    ]
    mock_subset.to_csv(mock_csv_path, index=False)

    seeded_db = seed_sqlite(
        catalog=catalog,
        sales_df=sales_df,
        forecasts_df=forecasts_df,
        config=config,
        db_path=db_path,
    )

    print(f"Generated Parquet dataset: {parquet_path} ({len(sales_df):,} rows)")
    print(f"Generated Day-1 mock CSV: {mock_csv_path} ({len(mock_subset):,} rows)")
    print(f"Seeded SQLite database:   {seeded_db}")


if __name__ == "__main__":
    main()
