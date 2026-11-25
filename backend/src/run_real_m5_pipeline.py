"""CLI pipeline for real Kaggle M5 CSV ingestion, training, backtest, and SQLite seeding.

Usage:
    python -m backend.src.run_real_m5_pipeline

Checks `data/raw/` (or `--raw-dir`) for `sales_train_validation.csv`, `calendar.csv`,
and `sell_prices.csv`. If missing, automatically downloads the competition files via
`kagglehub.competition_download('m5-forecasting-accuracy')` and places them into
`data/raw/`. Then filters to store `CA_1`, selects a balanced 200-SKU subset across
FOODS, HOBBIES, and HOUSEHOLD over the last 2.5 years (913 days), applies strict
`sell_price` NaN filtering, saves `data/processed/m5_sales.parquet`, retrains the 3
direct LightGBM Tweedie models (h=7, 14, 28), runs the 28-day financial policy
backtest, and repopulates SQLite.
"""

from __future__ import annotations

import argparse
import shutil
import sys
import zipfile
from pathlib import Path

import pandas as pd

from backend.src.data_processing import preprocess_raw_m5
from backend.src.database import REPO_ROOT, db_session, get_db_path
from backend.src.forecasting import load_config, run_forecasting_pipeline
from backend.src.inventory import run_28day_policy_backtest
from backend.src.seed_mock_data import seed_sqlite

REQUIRED_M5_FILES = (
    "sales_train_validation.csv",
    "calendar.csv",
    "sell_prices.csv",
)


def ensure_m5_raw_files(raw_dir: Path, auto_download: bool = True) -> Path:
    """Ensure all required M5 CSVs exist in `raw_dir`, downloading via kagglehub if needed."""
    raw_dir.mkdir(parents=True, exist_ok=True)
    missing = [f for f in REQUIRED_M5_FILES if not (raw_dir / f).exists()]
    if not missing:
        return raw_dir

    if not auto_download:
        raise FileNotFoundError(
            f"Missing Kaggle M5 CSV files in {raw_dir}: {', '.join(missing)}."
        )

    import kagglehub

    print("M5 CSVs not found in data/raw/. Downloading via kagglehub...")
    downloaded_path = Path(kagglehub.competition_download("m5-forecasting-accuracy"))
    print("Path to competition files:", downloaded_path)

    # Extract any zip archives if kagglehub returned compressed files
    for zf_path in downloaded_path.glob("*.zip"):
        with zipfile.ZipFile(zf_path, "r") as zf:
            zf.extractall(downloaded_path)

    # Copy required CSVs into raw_dir (search recursively in case files are nested)
    for filename in REQUIRED_M5_FILES:
        dest = raw_dir / filename
        if dest.exists():
            continue
        matches = list(downloaded_path.rglob(filename))
        if not matches:
            raise FileNotFoundError(
                f"Downloaded M5 directory {downloaded_path} did not contain {filename}."
            )
        shutil.copy2(matches[0], dest)
        print(f"Copied {filename} -> {dest}")

    return raw_dir


def run_pipeline(
    raw_dir: Path,
    output_parquet: Path,
    store_id: str = "CA_1",
    max_items: int = 200,
    tail_days: int = 913,
    models_dir: Path | None = None,
    db_path: Path | None = None,
    config_path: Path = REPO_ROOT / "configs" / "inventory_config.yaml",
    auto_download: bool = True,
) -> dict:
    """Execute end-to-end real M5 ingestion, training, backtest, and SQLite seeding."""
    ensure_m5_raw_files(raw_dir=raw_dir, auto_download=auto_download)

    config = load_config(config_path)
    resolved_models = models_dir or (REPO_ROOT / config["storage"]["models_dir"])
    resolved_db = get_db_path(db_path or config["storage"]["database_path"])

    print(
        f"[1/4] Ingesting raw M5 CSVs from {raw_dir} "
        f"(store={store_id}, balanced max_items={max_items}, tail_days={tail_days})..."
    )
    sales_df = preprocess_raw_m5(
        raw_dir=raw_dir,
        output_parquet_path=output_parquet,
        store_ids=(store_id,),
        cat_ids=("FOODS", "HOBBIES", "HOUSEHOLD"),
        max_items=max_items,
        tail_days=tail_days,
        balance_categories=True,
    )
    cat_counts = sales_df.groupby("cat_id", observed=True)["item_id"].nunique().to_dict()
    print(
        f"      Saved {output_parquet} ({len(sales_df):,} rows, "
        f"{sales_df['item_id'].nunique()} SKUs: {cat_counts})"
    )

    print("[2/4] Training direct LightGBM Tweedie models (h=7, 14, 28) & persisting forecasts...")
    fc_out = run_forecasting_pipeline(
        parquet_path=output_parquet,
        models_dir=resolved_models,
        config_path=config_path,
        persist_to_sqlite=True,
        db_path=resolved_db,
    )

    print("[3/4] Running 28-day financial policy backtest...")
    backtest = run_28day_policy_backtest(
        baseline_holdout_df=fc_out["holdout_predictions"]["seasonal_naive"],
        lgbm_holdout_df=fc_out["holdout_predictions"]["lightgbm"],
        sales_df=fc_out["sales_df"],
        per_sku_lgbm_rmse=fc_out["summary"]["per_sku_val_rmse"],
        per_sku_baseline_rmse=fc_out["summary"]["per_sku_baseline_val_rmse"],
        config_path=config_path,
        metrics_json_path=fc_out["metrics_path"],
    )

    print("[4/4] Repopulating SQLite inventory & audit transactions from real M5 catalog...")
    catalog = (
        sales_df[["item_id", "store_id", "dept_id", "cat_id", "state_id"]]
        .drop_duplicates()
        .astype(str)
        .sort_values(["cat_id", "item_id"])
        .reset_index(drop=True)
    )
    with db_session(resolved_db) as conn:
        fc_rows = conn.execute(
            """
            SELECT item_id, store_id, forecast_date, prediction, prediction_p95,
                   horizon, model_version, created_at
            FROM forecast_results
            """
        ).fetchall()
    forecasts_df = pd.DataFrame([dict(r) for r in fc_rows])

    seed_sqlite(
        catalog=catalog,
        sales_df=sales_df,
        forecasts_df=forecasts_df,
        config=config,
        db_path=resolved_db,
    )

    print(
        f"Done! Seeded {len(catalog)} SKUs in {resolved_db}. "
        f"28d Policy Cost: Baseline=${backtest['seasonal_naive']['total_policy_cost']} vs "
        f"LightGBM=${backtest['lightgbm']['total_policy_cost']}"
    )
    return {
        "parquet_path": output_parquet,
        "db_path": resolved_db,
        "sku_count": int(len(catalog)),
        "category_counts": {str(k): int(v) for k, v in cat_counts.items()},
        "horizon_metrics": fc_out["summary"]["horizon_metrics"],
        "policy_backtest_28d": backtest,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run real Kaggle M5 ingestion & training pipeline.")
    parser.add_argument("--raw-dir", type=Path, default=REPO_ROOT / "data" / "raw")
    parser.add_argument(
        "--output-parquet", type=Path, default=REPO_ROOT / "data" / "processed" / "m5_sales.parquet"
    )
    parser.add_argument("--store-id", type=str, default="CA_1")
    parser.add_argument("--max-items", type=int, default=200)
    parser.add_argument("--tail-days", type=int, default=913)
    parser.add_argument("--no-download", action="store_true", help="Do not auto-download via kagglehub")
    args = parser.parse_args()

    try:
        run_pipeline(
            raw_dir=args.raw_dir,
            output_parquet=args.output_parquet,
            store_id=args.store_id,
            max_items=args.max_items,
            tail_days=args.tail_days,
            auto_download=not args.no_download,
        )
        return 0
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
