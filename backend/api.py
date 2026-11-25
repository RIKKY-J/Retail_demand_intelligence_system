"""Slim FastAPI backend exposing 4 REST endpoints for the 3-page Next.js app."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Optional

import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from backend.inventory import (
    compute_inventory_item,
    get_inventory_rows,
    update_inventory_row,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_CSV = REPO_ROOT / "data" / "m5_subset.csv"
FORECASTS_CSV = REPO_ROOT / "data" / "forecasts.csv"
METRICS_JSON = REPO_ROOT / "models" / "metrics.json"

app = FastAPI(
    title="Retail Demand Intelligence API",
    version="1.0.0",
    description="Slim FastAPI backend for 4-model demand forecasting and simulated inventory.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class InventoryPatchRequest(BaseModel):
    current_stock: Optional[int] = Field(default=None, ge=0)
    lead_time_days: Optional[int] = Field(default=None, ge=1, le=60)


@lru_cache(maxsize=2)
def _load_sales_csv(mtime_ns: int) -> pd.DataFrame:
    df = pd.read_csv(DATA_CSV)
    df["date"] = pd.to_datetime(df["date"])
    return df


@lru_cache(maxsize=2)
def _load_forecasts_csv(mtime_ns: int) -> pd.DataFrame:
    return pd.read_csv(FORECASTS_CSV)


def _get_sales() -> pd.DataFrame:
    return _load_sales_csv(DATA_CSV.stat().st_mtime_ns)


def _get_forecasts() -> pd.DataFrame:
    return _load_forecasts_csv(FORECASTS_CSV.stat().st_mtime_ns)


def _get_metrics() -> dict:
    with open(METRICS_JSON, "r", encoding="utf-8") as fh:
        return json.load(fh)


def _build_enriched_inventory() -> list[dict]:
    raw_rows = get_inventory_rows()
    fc_df = _get_forecasts()
    metrics = _get_metrics()
    per_sku_rmse = metrics.get("per_sku_rmse", {})

    fc_map: dict[str, list[float]] = {}
    for item_id, grp in fc_df.sort_values("forecast_date").groupby("item_id"):
        fc_map[str(item_id)] = grp["predicted_sales"].astype(float).tolist()

    return [
        compute_inventory_item(
            item_id=row["item_id"],
            cat_id=row["cat_id"],
            current_stock=row["current_stock"],
            lead_time_days=row["lead_time_days"],
            updated_at=row["updated_at"],
            sku_rmse=float(per_sku_rmse.get(row["item_id"], 1.0)),
            daily_forecasts=fc_map.get(row["item_id"], [1.0] * 7),
        )
        for row in raw_rows
    ]


@app.get("/api/overview")
def get_overview() -> dict:
    """Return overview KPIs, daily sales trend, and 4-model comparison table."""
    sales_df = _get_sales()
    metrics = _get_metrics()
    inv_items = _build_enriched_inventory()

    low_stock = sum(1 for i in inv_items if i["status"] == "Low Stock (Reorder)")
    healthy = sum(1 for i in inv_items if i["status"] == "Healthy")
    overstock = sum(1 for i in inv_items if i["status"] == "Overstock")

    trend_df = (
        sales_df.groupby("date", as_index=False)["sales"]
        .sum()
        .sort_values("date")
    )
    daily_trend = [
        {"date": pd.Timestamp(r.date).strftime("%Y-%m-%d"), "units_sold": int(r.sales)}
        for r in trend_df.itertuples(index=False)
    ]

    best_name = metrics["best_model"]
    best_rmse = next(
        (m["rmse"] for m in metrics["model_comparison"] if m["model"] == best_name),
        None,
    )

    return {
        "kpis": {
            "total_units_sold": int(sales_df["sales"].sum()),
            "monitored_skus": len(inv_items),
            "low_stock_alerts": low_stock,
            "healthy_count": healthy,
            "overstock_count": overstock,
            "best_model": best_name,
            "best_model_rmse": best_rmse,
        },
        "daily_sales_trend": daily_trend,
        "model_comparison": metrics["model_comparison"],
        "split": metrics["split"],
    }


@app.get("/api/forecast")
def get_forecast(item_id: Optional[str] = Query(default=None)) -> dict:
    """Return available SKUs, last 30d actuals, 28d holdout, and 7d forecast."""
    sales_df = _get_sales()
    fc_df = _get_forecasts()
    metrics = _get_metrics()

    skus = (
        sales_df[["item_id", "cat_id"]]
        .drop_duplicates()
        .sort_values("item_id")
        .to_dict(orient="records")
    )
    selected = item_id or skus[0]["item_id"]

    sku_sales = sales_df[sales_df["item_id"] == selected].sort_values("date")
    if sku_sales.empty:
        raise HTTPException(status_code=404, detail=f"SKU {selected} not found")

    history = [
        {
            "date": pd.Timestamp(r.date).strftime("%Y-%m-%d"),
            "actual_sales": int(r.sales),
        }
        for r in sku_sales.tail(30).itertuples(index=False)
    ]

    holdout = metrics.get("holdout_series", {}).get(selected, [])

    sku_fc = fc_df[fc_df["item_id"] == selected].sort_values("forecast_date")
    forecast_7d = [
        {
            "forecast_date": str(r.forecast_date),
            "predicted_sales": float(r.predicted_sales),
        }
        for r in sku_fc.itertuples(index=False)
    ]

    return {
        "item_id": selected,
        "cat_id": str(sku_sales["cat_id"].iloc[0]),
        "best_model": metrics["best_model"],
        "sku_rmse": metrics.get("per_sku_rmse", {}).get(selected, 0.0),
        "available_items": skus,
        "history_30d": history,
        "holdout_28d": holdout,
        "forecast_7d": forecast_7d,
    }


@app.get("/api/inventory")
def get_inventory() -> dict:
    """Return all 60 monitored SKUs with Safety Stock, ROP, Order Qty, and Status."""
    items = _build_enriched_inventory()
    return {"items": items, "total": len(items)}


@app.patch("/api/inventory/{item_id}")
def patch_inventory(item_id: str, payload: InventoryPatchRequest) -> dict:
    """Update `current_stock` and/or `lead_time_days` in SQLite and recalculate."""
    updated_row = update_inventory_row(
        item_id=item_id,
        current_stock=payload.current_stock,
        lead_time_days=payload.lead_time_days,
    )
    if updated_row is None:
        raise HTTPException(status_code=404, detail=f"SKU {item_id} not found")

    fc_df = _get_forecasts()
    metrics = _get_metrics()
    sku_fc = (
        fc_df[fc_df["item_id"] == item_id]
        .sort_values("forecast_date")["predicted_sales"]
        .astype(float)
        .tolist()
    )
    sku_rmse = float(metrics.get("per_sku_rmse", {}).get(item_id, 1.0))

    return compute_inventory_item(
        item_id=updated_row["item_id"],
        cat_id=updated_row["cat_id"],
        current_stock=updated_row["current_stock"],
        lead_time_days=updated_row["lead_time_days"],
        updated_at=updated_row["updated_at"],
        sku_rmse=sku_rmse,
        daily_forecasts=sku_fc or [1.0] * 7,
    )
