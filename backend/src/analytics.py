"""Sales analytics, enriched inventory state, and model metrics helpers.

Serves aggregated historical M5 Parquet queries and live SQLite-backed
inventory optimization state for the FastAPI routes without duplicating math.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from backend.src.data_processing import load_processed_sales, resolve_sales_parquet_path
from backend.src.database import REPO_ROOT, db_session, get_db_path
from backend.src.inventory import compute_replenishment_metrics, load_inventory_config

DEFAULT_METRICS_PATH = REPO_ROOT / "models" / "model_metrics.json"


@lru_cache(maxsize=4)
def _cached_sales_df(resolved_path: str, mtime_ns: int) -> pd.DataFrame:
    df = load_processed_sales(resolved_path)
    df["revenue"] = df["sales"].astype(np.float64) * df["sell_price"].astype(np.float64)
    return df


def get_sales_dataframe(parquet_path: str | Path | None = None) -> pd.DataFrame:
    """Load processed sales Parquet with mtime-aware in-memory caching."""
    path = resolve_sales_parquet_path(parquet_path)
    stat = path.stat()
    return _cached_sales_df(str(path), stat.st_mtime_ns)


def load_model_metrics(metrics_path: str | Path | None = None) -> dict[str, Any]:
    """Load `models/model_metrics.json` if available."""
    path = Path(metrics_path) if metrics_path is not None else DEFAULT_METRICS_PATH
    if not path.is_absolute():
        path = REPO_ROOT / path
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def get_enriched_inventory(
    store_id: str | None = None,
    cat_id: str | None = None,
    status_filter: str | None = None,
    search: str | None = None,
    db_path: str | Path | None = None,
) -> list[dict[str, Any]]:
    """Join SQLite inventory + metadata + LightGBM forecasts and compute live policy metrics."""
    cfg = load_inventory_config()
    ml_version = cfg["forecasting"]["ml_model_version"]
    z_score = float(cfg["inventory"]["service_level_z"])
    overstock_mult = float(cfg["thresholds"]["overstock_multiplier"])
    moq = int(cfg["inventory"]["default_moq"])
    pack_size = int(cfg["inventory"]["default_pack_size"])

    metrics_doc = load_model_metrics()
    per_sku_rmse: dict[str, float] = metrics_doc.get("per_sku_val_rmse", {})

    resolved_db = get_db_path(db_path or cfg["storage"]["database_path"])

    where_clauses = []
    params: list[Any] = []
    if store_id:
        where_clauses.append("i.store_id = ?")
        params.append(store_id)
    if cat_id:
        where_clauses.append("m.cat_id = ?")
        params.append(cat_id)
    if search:
        where_clauses.append("(LOWER(i.item_id) LIKE ? OR LOWER(m.dept_id) LIKE ?)")
        like_term = f"%{search.strip().lower()}%"
        params.extend([like_term, like_term])

    where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

    with db_session(resolved_db) as conn:
        inv_rows = conn.execute(
            f"""
            SELECT
                i.inventory_id,
                i.item_id,
                i.store_id,
                m.dept_id,
                m.cat_id,
                m.state_id,
                i.on_hand,
                i.on_order,
                i.backorders,
                i.lead_time_days,
                i.review_period_days,
                i.unit_cost,
                i.updated_at
            FROM inventory i
            JOIN product_metadata m
              ON i.item_id = m.item_id AND i.store_id = m.store_id
            {where_sql}
            ORDER BY i.store_id, i.item_id
            """,
            params,
        ).fetchall()

        fc_rows = conn.execute(
            """
            SELECT store_id, item_id, forecast_date, prediction
            FROM forecast_results
            WHERE horizon = 28 AND model_version = ?
            ORDER BY store_id, item_id, forecast_date
            """,
            (ml_version,),
        ).fetchall()

    fc_map: dict[tuple[str, str], list[float]] = {}
    for row in fc_rows:
        fc_map.setdefault((row["store_id"], row["item_id"]), []).append(float(row["prediction"]))

    enriched: list[dict[str, Any]] = []
    for row in inv_rows:
        key = (row["store_id"], row["item_id"])
        daily_fc = fc_map.get(key, [1.0] * 28)
        rmse_val = float(per_sku_rmse.get(f"{row['store_id']}::{row['item_id']}", 1.0))

        policy = compute_replenishment_metrics(
            on_hand=int(row["on_hand"]),
            on_order=int(row["on_order"]),
            backorders=int(row["backorders"]),
            lead_time_days=int(row["lead_time_days"]),
            review_period_days=int(row["review_period_days"]),
            daily_forecasts=daily_fc,
            validation_rmse=rmse_val,
            z_score=z_score,
            overstock_multiplier=overstock_mult,
            moq=moq,
            pack_size=pack_size,
        )

        if status_filter and policy.status.lower() != status_filter.lower():
            continue

        reasons: list[str] = []
        if policy.is_potential_stockout:
            reasons.append(
                f"On-hand ({row['on_hand']}) < lead-time demand ({policy.lead_time_demand:.1f})"
            )
        if policy.is_reorder_required:
            reasons.append(
                f"Inventory Position ({policy.inventory_position}) <= ROP ({policy.reorder_point:.1f})"
            )
        if policy.is_possible_overstock:
            reasons.append(
                f"On-hand ({row['on_hand']}) > {overstock_mult}x Target Stock ({policy.target_stock:.1f})"
            )

        enriched.append(
            {
                "inventory_id": int(row["inventory_id"]),
                "item_id": row["item_id"],
                "store_id": row["store_id"],
                "dept_id": row["dept_id"],
                "cat_id": row["cat_id"],
                "state_id": row["state_id"],
                "on_hand": int(row["on_hand"]),
                "on_order": int(row["on_order"]),
                "backorders": int(row["backorders"]),
                "lead_time_days": int(row["lead_time_days"]),
                "review_period_days": int(row["review_period_days"]),
                "unit_cost": float(row["unit_cost"]),
                "updated_at": row["updated_at"],
                "validation_rmse": round(rmse_val, 4),
                "inventory_position": policy.inventory_position,
                "safety_stock": policy.safety_stock,
                "lead_time_demand": policy.lead_time_demand,
                "review_period_demand": policy.review_period_demand,
                "reorder_point": policy.reorder_point,
                "target_stock": policy.target_stock,
                "recommended_order_qty": policy.recommended_order_qty,
                "status": policy.status,
                "is_reorder_required": policy.is_reorder_required,
                "is_potential_stockout": policy.is_potential_stockout,
                "is_possible_overstock": policy.is_possible_overstock,
                "alert_reasons": reasons,
                "is_simulated": True,
            }
        )

    return enriched


def compute_sales_analytics(
    store_id: str | None = None,
    cat_id: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    granularity: str = "weekly",
    parquet_path: str | Path | None = None,
) -> dict[str, Any]:
    """Compute historical M5 sales & price analytics over the Parquet dataset."""
    df = get_sales_dataframe(parquet_path)

    all_stores = sorted(df["store_id"].astype(str).unique().tolist())
    all_categories = sorted(df["cat_id"].astype(str).unique().tolist())
    min_date_str = pd.Timestamp(df["date"].min()).strftime("%Y-%m-%d")
    max_date_str = pd.Timestamp(df["date"].max()).strftime("%Y-%m-%d")

    mask = pd.Series(True, index=df.index)
    if store_id:
        mask &= df["store_id"].astype(str) == store_id
    if cat_id:
        mask &= df["cat_id"].astype(str) == cat_id
    if start_date:
        mask &= df["date"] >= pd.Timestamp(start_date)
    if end_date:
        mask &= df["date"] <= pd.Timestamp(end_date)

    sub = df[mask].copy()
    if sub.empty:
        return {
            "filters": {
                "stores": all_stores,
                "categories": all_categories,
                "min_date": min_date_str,
                "max_date": max_date_str,
            },
            "sales_trend": [],
            "top_products": [],
            "low_demand_products": [],
            "store_comparison": [],
            "category_comparison": [],
            "weekday_pattern": [],
            "price_demand": [],
        }

    # 1. Time-series trend (daily, weekly, or monthly)
    if granularity == "daily":
        sub["period"] = sub["date"].dt.strftime("%Y-%m-%d")
    elif granularity == "monthly":
        sub["period"] = sub["date"].dt.to_period("M").astype(str)
    else:
        sub["period"] = sub["date"].dt.to_period("W-SUN").apply(lambda p: p.start_time.strftime("%Y-%m-%d"))

    trend_df = (
        sub.groupby("period", as_index=False)
        .agg(
            units_sold=("sales", "sum"),
            revenue=("revenue", "sum"),
            avg_price=("sell_price", "mean"),
            avg_units=("sales", "mean"),
        )
        .sort_values("period")
    )

    sales_trend = [
        {
            "period": r.period,
            "units_sold": int(r.units_sold),
            "revenue": round(float(r.revenue), 2),
            "avg_price": round(float(r.avg_price), 2),
        }
        for r in trend_df.itertuples(index=False)
    ]

    price_demand = [
        {
            "period": r.period,
            "avg_price": round(float(r.avg_price), 2),
            "avg_units": round(float(r.avg_units), 2),
        }
        for r in trend_df.itertuples(index=False)
    ]

    # 2. Top & low-demand products
    sku_agg = (
        sub.groupby(["item_id", "dept_id", "cat_id"], observed=True, as_index=False)
        .agg(
            total_units=("sales", "sum"),
            total_revenue=("revenue", "sum"),
            avg_daily_units=("sales", "mean"),
        )
    )
    sku_agg["item_id"] = sku_agg["item_id"].astype(str)
    sku_agg["dept_id"] = sku_agg["dept_id"].astype(str)
    sku_agg["cat_id"] = sku_agg["cat_id"].astype(str)

    def _fmt_products(frame: pd.DataFrame) -> list[dict[str, Any]]:
        return [
            {
                "item_id": r.item_id,
                "dept_id": r.dept_id,
                "cat_id": r.cat_id,
                "total_units": int(r.total_units),
                "total_revenue": round(float(r.total_revenue), 2),
                "avg_daily_units": round(float(r.avg_daily_units), 2),
            }
            for r in frame.itertuples(index=False)
        ]

    top_products = _fmt_products(sku_agg.sort_values("total_units", ascending=False).head(10))
    low_demand_products = _fmt_products(sku_agg.sort_values("total_units", ascending=True).head(10))

    # 3. Store comparison
    store_agg = (
        sub.groupby("store_id", observed=True, as_index=False)
        .agg(
            total_units=("sales", "sum"),
            total_revenue=("revenue", "sum"),
            sku_count=("item_id", "nunique"),
        )
    )
    store_comparison = [
        {
            "store_id": str(r.store_id),
            "total_units": int(r.total_units),
            "total_revenue": round(float(r.total_revenue), 2),
            "sku_count": int(r.sku_count),
        }
        for r in store_agg.itertuples(index=False)
    ]

    # 4. Category comparison
    cat_agg = (
        sub.groupby("cat_id", observed=True, as_index=False)
        .agg(
            total_units=("sales", "sum"),
            total_revenue=("revenue", "sum"),
            sku_count=("item_id", "nunique"),
        )
        .sort_values("total_units", ascending=False)
    )
    category_comparison = [
        {
            "cat_id": str(r.cat_id),
            "total_units": int(r.total_units),
            "total_revenue": round(float(r.total_revenue), 2),
            "sku_count": int(r.sku_count),
        }
        for r in cat_agg.itertuples(index=False)
    ]

    # 5. Weekday pattern (Mon -> Sun)
    sub["py_wd"] = sub["date"].dt.weekday
    sub["wd_name"] = sub["date"].dt.day_name().str.slice(0, 3)
    wd_agg = (
        sub.groupby(["py_wd", "wd_name"], as_index=False)
        .agg(avg_units=("sales", "mean"), total_units=("sales", "sum"))
        .sort_values("py_wd")
    )
    weekday_pattern = [
        {
            "weekday": r.wd_name,
            "avg_units": round(float(r.avg_units), 2),
            "total_units": int(r.total_units),
        }
        for r in wd_agg.itertuples(index=False)
    ]

    return {
        "filters": {
            "stores": all_stores,
            "categories": all_categories,
            "min_date": min_date_str,
            "max_date": max_date_str,
        },
        "sales_trend": sales_trend,
        "top_products": top_products,
        "low_demand_products": low_demand_products,
        "store_comparison": store_comparison,
        "category_comparison": category_comparison,
        "weekday_pattern": weekday_pattern,
        "price_demand": price_demand,
    }
