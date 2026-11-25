"""Data ingestion, sell_price filtering, downcasting, and horizon-aligned features.

Implements Section 6 of the implementation plan:
- Melts raw M5 wide CSVs to long format when ingesting Kaggle M5 files.
- Enforces the critical M5 filtering rule: drop all rows where `sell_price` is
  NaN BEFORE computing any lag or rolling features.
- Downcasts numeric types (`float64` -> `float32`) for laptop memory efficiency.
- Builds strictly horizon-aligned features (`lag_h`, `lag_h_plus_7`,
  `lag_h_plus_21`, shifted rolling means/stds) so predictions for date `t` from
  cutoff `t - h` never leak future sales or prices.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

from backend.src.database import REPO_ROOT

CATEGORICAL_COLS = ("item_id", "dept_id", "cat_id", "store_id", "state_id", "event_name_1")

MODEL_FEATURE_COLS = [
    "item_id",
    "dept_id",
    "cat_id",
    "store_id",
    "sell_price",
    "price_change_4w",
    "day_of_week",
    "month",
    "week_of_year",
    "wday",
    "snap_CA",
    "snap_TX",
    "snap_WI",
    "event_name_1",
    "lag_h",
    "lag_h_plus_7",
    "lag_h_plus_21",
    "rolling_mean_7_shift_h",
    "rolling_mean_28_shift_h",
    "rolling_std_28_shift_h",
]


def filter_unstocked_periods(df: pd.DataFrame) -> pd.DataFrame:
    """Drop rows with missing sell_price BEFORE any lag/rolling feature computation.

    In M5, NaN `sell_price` indicates the SKU was not yet stocked/launched at
    that store in that week; retaining them as zero sales introduces fake zeros.
    """
    filtered = df.dropna(subset=["sell_price"]).copy()
    return filtered


def downcast_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Downcast float64 -> float32, large ints where safe, and IDs to category."""
    out = df.copy()
    for col in out.select_dtypes(include=["float64"]).columns:
        out[col] = out[col].astype(np.float32)

    for col in ("wday", "month", "snap_CA", "snap_TX", "snap_WI"):
        if col in out.columns:
            out[col] = out[col].fillna(0).astype(np.int8)

    if "year" in out.columns:
        if "date" in out.columns:
            out["year"] = out["year"].fillna(pd.to_datetime(out["date"]).dt.year)
        out["year"] = out["year"].fillna(0).astype(np.int16)
    if "wm_yr_wk" in out.columns:
        out["wm_yr_wk"] = out["wm_yr_wk"].ffill().fillna(0).astype(np.int32)
    if "sales" in out.columns:
        out["sales"] = out["sales"].fillna(0).astype(np.int32)

    for col in CATEGORICAL_COLS:
        if col in out.columns:
            if col == "event_name_1":
                out[col] = out[col].fillna("None").astype(str).astype("category")
            else:
                out[col] = out[col].astype(str).astype("category")

    return out


def _select_balanced_items(
    sales_wide: pd.DataFrame,
    max_items: int,
) -> pd.DataFrame:
    """Select up to `max_items` SKUs balanced evenly across available categories."""
    if len(sales_wide) <= max_items:
        return sales_wide

    categories = sorted(sales_wide["cat_id"].unique().tolist())
    if not categories:
        return sales_wide.head(max_items)

    per_cat, remainder = divmod(max_items, len(categories))
    selected_chunks = []
    for idx, cat in enumerate(categories):
        quota = per_cat + (1 if idx < remainder else 0)
        cat_df = sales_wide[sales_wide["cat_id"] == cat].sort_values("item_id")
        selected_chunks.append(cat_df.head(quota))

    return pd.concat(selected_chunks, ignore_index=True)


def preprocess_raw_m5(
    raw_dir: str | Path,
    output_parquet_path: str | Path,
    store_ids: Iterable[str] | None = ("CA_1",),
    cat_ids: Iterable[str] | None = None,
    max_items: int | None = 200,
    tail_days: int | None = 913,
    balance_categories: bool = True,
) -> pd.DataFrame:
    """Load raw Kaggle M5 CSVs, melt wide -> long, filter NaN prices, and save Parquet."""
    raw_path = Path(raw_dir)
    sales_wide = pd.read_csv(raw_path / "sales_train_validation.csv")
    calendar = pd.read_csv(raw_path / "calendar.csv")
    prices = pd.read_csv(raw_path / "sell_prices.csv")

    if store_ids is not None:
        sales_wide = sales_wide[sales_wide["store_id"].isin(list(store_ids))]
    if cat_ids is not None:
        sales_wide = sales_wide[sales_wide["cat_id"].isin(list(cat_ids))]
    if max_items is not None:
        if balance_categories:
            sales_wide = _select_balanced_items(sales_wide, max_items=max_items)
        else:
            sales_wide = sales_wide.head(max_items)

    id_cols = ["id", "item_id", "dept_id", "cat_id", "store_id", "state_id"]
    day_cols = [c for c in sales_wide.columns if c.startswith("d_")]
    if tail_days is not None and len(day_cols) > tail_days:
        day_cols = day_cols[-tail_days:]

    long_df = sales_wide.melt(
        id_vars=id_cols,
        value_vars=day_cols,
        var_name="d",
        value_name="sales",
    )

    long_df = long_df.merge(calendar, on="d", how="left")
    long_df["date"] = pd.to_datetime(long_df["date"])
    long_df = long_df.merge(prices, on=["store_id", "item_id", "wm_yr_wk"], how="left")

    # Critical M5 rule: filter NaN sell_price BEFORE computing any lag/rolling features
    long_df = filter_unstocked_periods(long_df)
    long_df = downcast_dataframe(long_df)
    long_df = long_df.sort_values(["store_id", "item_id", "date"]).reset_index(drop=True)

    out_path = Path(output_parquet_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    long_df.to_parquet(out_path, index=False, engine="pyarrow")
    return long_df


def resolve_sales_parquet_path(parquet_path: str | Path | None = None) -> Path:
    """Resolve explicit Parquet path, or prefer real `m5_sales.parquet` over `sample_sales.parquet`."""
    if parquet_path is not None:
        path = Path(parquet_path)
        return path if path.is_absolute() else REPO_ROOT / path

    real_path = REPO_ROOT / "data" / "processed" / "m5_sales.parquet"
    if real_path.exists():
        return real_path
    return REPO_ROOT / "data" / "processed" / "sample_sales.parquet"


def load_processed_sales(parquet_path: str | Path | None = None) -> pd.DataFrame:
    """Load processed Parquet sales, enforce sell_price filter, and sort chronologically."""
    path = resolve_sales_parquet_path(parquet_path)

    df = pd.read_parquet(path)
    df["date"] = pd.to_datetime(df["date"])
    # Enforce sell_price NaN filter prior to any downstream feature generation
    df = filter_unstocked_periods(df)
    df = df.sort_values(["store_id", "item_id", "date"]).reset_index(drop=True)
    return df


def build_horizon_features(df: pd.DataFrame, horizon: int) -> pd.DataFrame:
    """Construct strictly horizon-aligned features for direct horizon `h` forecasting.

    All lag and rolling demand statistics are shifted by at least `horizon` days
    within each `(store_id, item_id)` series, ensuring zero data leakage relative
    to cutoff date `t - horizon`.
    """
    if horizon < 1:
        raise ValueError(f"horizon must be >= 1, got {horizon}")

    # Guarantee unstocked rows are removed before computing lag/rolling stats
    work = filter_unstocked_periods(df)
    work["date"] = pd.to_datetime(work["date"])
    work = work.sort_values(["store_id", "item_id", "date"]).reset_index(drop=True)

    grp_sales = work.groupby(["store_id", "item_id"], observed=True)["sales"]
    grp_price = work.groupby(["store_id", "item_id"], observed=True)["sell_price"]

    shifted_sales = grp_sales.shift(horizon)

    work["lag_h"] = shifted_sales
    work["lag_h_plus_7"] = grp_sales.shift(horizon + 7)
    work["lag_h_plus_21"] = grp_sales.shift(horizon + 21)

    work["rolling_mean_7_shift_h"] = (
        shifted_sales.groupby([work["store_id"], work["item_id"]], observed=True)
        .transform(lambda s: s.rolling(window=7, min_periods=1).mean())
    )
    work["rolling_mean_28_shift_h"] = (
        shifted_sales.groupby([work["store_id"], work["item_id"]], observed=True)
        .transform(lambda s: s.rolling(window=28, min_periods=1).mean())
    )
    work["rolling_std_28_shift_h"] = (
        shifted_sales.groupby([work["store_id"], work["item_id"]], observed=True)
        .transform(lambda s: s.rolling(window=28, min_periods=1).std())
        .fillna(0.0)
    )

    # Price momentum relative to horizon-shifted 4-week rolling mean
    shifted_price_mean_28 = (
        grp_price.shift(horizon)
        .groupby([work["store_id"], work["item_id"]], observed=True)
        .transform(lambda s: s.rolling(window=28, min_periods=1).mean())
    )
    work["price_change_4w"] = (
        (work["sell_price"] - shifted_price_mean_28)
        / shifted_price_mean_28.replace(0, np.nan)
    ).fillna(0.0)

    # Calendar features
    work["day_of_week"] = work["date"].dt.dayofweek.astype(np.int8)
    work["month"] = work["date"].dt.month.astype(np.int8)
    work["week_of_year"] = work["date"].dt.isocalendar().week.astype(np.int16)

    if "wday" not in work.columns:
        work["wday"] = (((work["day_of_week"] + 2) % 7) + 1).astype(np.int8)
    for snap_col in ("snap_CA", "snap_TX", "snap_WI"):
        if snap_col not in work.columns:
            work[snap_col] = np.int8(0)
    if "event_name_1" not in work.columns:
        work["event_name_1"] = "None"

    work = downcast_dataframe(work)
    return work


def chronological_split_dates(
    df: pd.DataFrame,
    test_days: int = 28,
    val_days: int = 28,
) -> tuple[pd.Timestamp, pd.Timestamp, pd.Timestamp]:
    """Compute strictly chronological split boundary dates (val_start, test_start, max_date)."""
    max_date = pd.Timestamp(df["date"].max())
    test_start = max_date - pd.Timedelta(days=test_days - 1)
    val_start = test_start - pd.Timedelta(days=val_days)
    return val_start, test_start, max_date
