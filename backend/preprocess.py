"""Preprocess real Kaggle M5 CSVs into a clean 60-SKU dataset (`data/m5_subset.csv`).

Steps:
1. Read `sales_train_validation.csv`, `calendar.csv`, and `sell_prices.csv` from `data/raw/`.
2. Filter to store `CA_1` and select 60 balanced SKUs (20 FOODS, 20 HOBBIES, 20 HOUSEHOLD).
3. Keep the most recent 365 days, melt wide -> long, merge calendar and prices.
4. Drop rows where `sell_price` is NaN (unstocked weeks) BEFORE feature engineering.
5. Engineer simple 7-day-shifted features (zero leakage) and save `data/m5_subset.csv`.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = REPO_ROOT / "data" / "raw"
OUTPUT_CSV = REPO_ROOT / "data" / "m5_subset.csv"


def select_balanced_skus(
    sales_wide: pd.DataFrame,
    store_id: str = "CA_1",
    per_category: int = 20,
) -> pd.DataFrame:
    """Filter to `store_id` and pick `per_category` SKUs from FOODS, HOBBIES, HOUSEHOLD."""
    store_df = sales_wide[sales_wide["store_id"] == store_id].copy()
    chunks = []
    for cat in ("FOODS", "HOBBIES", "HOUSEHOLD"):
        cat_rows = store_df[store_df["cat_id"] == cat].sort_values("item_id")
        chunks.append(cat_rows.head(per_category))
    return pd.concat(chunks, ignore_index=True)


def run_preprocessing(
    raw_dir: Path = RAW_DIR,
    output_csv: Path = OUTPUT_CSV,
    store_id: str = "CA_1",
    per_category: int = 20,
    num_days: int = 365,
) -> pd.DataFrame:
    """Load raw M5 CSVs, clean unstocked rows, build lag/rolling features, and save CSV."""
    print("Loading raw M5 CSV files from data/raw/...")
    sales_wide = pd.read_csv(raw_dir / "sales_train_validation.csv")
    calendar = pd.read_csv(raw_dir / "calendar.csv")
    prices = pd.read_csv(raw_dir / "sell_prices.csv")

    subset_wide = select_balanced_skus(
        sales_wide, store_id=store_id, per_category=per_category
    )

    id_cols = ["item_id", "dept_id", "cat_id", "store_id", "state_id"]
    day_cols = [c for c in subset_wide.columns if c.startswith("d_")][-num_days:]

    print(
        f"Melting {len(subset_wide)} SKUs x {len(day_cols)} days into long format..."
    )
    df = subset_wide.melt(
        id_vars=id_cols,
        value_vars=day_cols,
        var_name="d",
        value_name="sales",
    )

    # Merge calendar dates/SNAP and weekly selling prices
    cal_cols = ["d", "date", "wm_yr_wk", "snap_CA"]
    df = df.merge(calendar[cal_cols], on="d", how="left")
    df["date"] = pd.to_datetime(df["date"])
    df = df.merge(prices, on=["store_id", "item_id", "wm_yr_wk"], how="left")

    # Critical M5 rule: drop unstocked periods (NaN sell_price) BEFORE computing lags
    before_rows = len(df)
    df = df.dropna(subset=["sell_price"]).copy()
    print(f"Dropped {before_rows - len(df)} unstocked rows with NaN sell_price.")

    df = df.sort_values(["item_id", "date"]).reset_index(drop=True)

    # 7-day-shifted features prevent future data leakage for 7-day forecasting
    grp = df.groupby("item_id")["sales"]
    df["lag_7"] = grp.shift(7)
    df["lag_14"] = grp.shift(14)
    df["rolling_mean_7"] = (
        df.groupby("item_id")["lag_7"]
        .transform(lambda s: s.rolling(window=7, min_periods=1).mean())
    )
    df["rolling_mean_28"] = (
        df.groupby("item_id")["lag_7"]
        .transform(lambda s: s.rolling(window=28, min_periods=1).mean())
    )

    df["day_of_week"] = df["date"].dt.dayofweek.astype(np.int8)
    df["month"] = df["date"].dt.month.astype(np.int8)
    df["sell_price"] = df["sell_price"].astype(float).round(2)
    df["snap_CA"] = df["snap_CA"].fillna(0).astype(np.int8)

    # Drop initial rows without complete lag_14 history so all ML models train cleanly
    df = df.dropna(subset=["lag_7", "lag_14"]).reset_index(drop=True)
    for col in ("lag_7", "lag_14", "rolling_mean_7", "rolling_mean_28"):
        df[col] = df[col].round(4)

    keep_cols = [
        "item_id",
        "dept_id",
        "cat_id",
        "store_id",
        "date",
        "sales",
        "lag_7",
        "lag_14",
        "rolling_mean_7",
        "rolling_mean_28",
        "day_of_week",
        "month",
        "sell_price",
        "snap_CA",
    ]
    df = df[keep_cols]

    output_csv.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_csv, index=False)
    print(
        f"Saved {output_csv} ({len(df):,} rows, {df['item_id'].nunique()} SKUs, "
        f"{df['date'].min().date()} to {df['date'].max().date()})."
    )
    return df


if __name__ == "__main__":
    run_preprocessing()
