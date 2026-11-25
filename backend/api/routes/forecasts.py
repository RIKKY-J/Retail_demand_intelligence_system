"""Demand forecasting endpoint (`GET /api/forecasts`)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Optional

import lightgbm as lgb
import numpy as np
import pandas as pd
from fastapi import APIRouter, HTTPException, Query

from backend.api.schemas import ForecastsResponse
from backend.src.analytics import get_sales_dataframe, load_model_metrics
from backend.src.data_processing import (
    MODEL_FEATURE_COLS,
    build_horizon_features,
)
from backend.src.database import REPO_ROOT, db_session, get_db_path
from backend.src.forecasting import predict_seasonal_naive
from backend.src.inventory import load_inventory_config

router = APIRouter(prefix="/api", tags=["forecasts"])


@lru_cache(maxsize=4)
def _load_booster(model_path_str: str, mtime_ns: int) -> lgb.Booster:
    return lgb.Booster(model_file=model_path_str)


def _compute_sku_holdout_comparison(
    sku_df: pd.DataFrame,
    global_max_date: pd.Timestamp,
    horizon_days: int = 28,
) -> list[dict]:
    """Score the exact global 28-day chronological holdout window for a single SKU."""
    model_path = REPO_ROOT / "models" / "lgbm_h28.txt"
    if not model_path.exists() or len(sku_df) < 60:
        return []

    max_dt = pd.Timestamp(global_max_date)
    test_start = max_dt - pd.Timedelta(days=horizon_days - 1)
    cutoff_date = test_start - pd.Timedelta(days=1)

    feat_df = build_horizon_features(sku_df, horizon=28)
    holdout_feat = (
        feat_df[(feat_df["date"] >= test_start) & (feat_df["date"] <= max_dt)]
        .sort_values("date")
        .copy()
    )
    if holdout_feat.empty:
        return []

    booster = _load_booster(str(model_path), model_path.stat().st_mtime_ns)
    lgbm_preds = np.clip(booster.predict(holdout_feat[MODEL_FEATURE_COLS]), 0.0, None)
    holdout_feat["lightgbm_pred"] = np.round(lgbm_preds, 2)

    naive_df = predict_seasonal_naive(sku_df, cutoff_date=cutoff_date, horizon=horizon_days)
    naive_map = {
        pd.Timestamp(r.date).strftime("%Y-%m-%d"): float(r.prediction)
        for r in naive_df.itertuples(index=False)
    }

    rows = []
    for r in holdout_feat.itertuples(index=False):
        d_str = pd.Timestamp(r.date).strftime("%Y-%m-%d")
        rows.append(
            {
                "date": d_str,
                "actual_sales": int(r.sales),
                "lightgbm_pred": float(r.lightgbm_pred),
                "seasonal_naive_pred": round(naive_map.get(d_str, 0.0), 2),
            }
        )
    return rows


@router.get("/forecasts", response_model=ForecastsResponse)
def get_forecasts(
    store_id: str = Query(default="CA_1"),
    item_id: Optional[str] = Query(default=None),
    horizon: int = Query(default=28),
    history_days: int = Query(default=60, ge=14, le=365),
) -> ForecastsResponse:
    """Return historical sales, 28-day holdout comparison, and future predictions for an SKU."""
    if horizon not in (7, 14, 28):
        raise HTTPException(status_code=422, detail="horizon must be one of 7, 14, or 28")
    cfg = load_inventory_config()
    ml_version = cfg["forecasting"]["ml_model_version"]
    baseline_version = cfg["forecasting"]["baseline_model_version"]
    resolved_db = get_db_path(cfg["storage"]["database_path"])

    with db_session(resolved_db) as conn:
        sku_rows = conn.execute(
            """
            SELECT item_id, store_id, dept_id, cat_id
            FROM product_metadata
            WHERE store_id = ?
            ORDER BY item_id
            """,
            (store_id,),
        ).fetchall()

        if not sku_rows:
            raise HTTPException(status_code=404, detail=f"No SKUs found for store {store_id}")

        available_items = [dict(r) for r in sku_rows]
        selected_item = item_id or available_items[0]["item_id"]

        selected_meta = next((s for s in available_items if s["item_id"] == selected_item), None)
        if selected_meta is None:
            raise HTTPException(
                status_code=404,
                detail=f"Item {selected_item} not found in store {store_id}",
            )

        fc_rows = conn.execute(
            """
            SELECT forecast_date, prediction, prediction_p95, model_version
            FROM forecast_results
            WHERE store_id = ? AND item_id = ? AND horizon = ?
            ORDER BY forecast_date
            """,
            (store_id, selected_item, horizon),
        ).fetchall()

    by_date: dict[str, dict] = {}
    for r in fc_rows:
        entry = by_date.setdefault(
            r["forecast_date"],
            {
                "forecast_date": r["forecast_date"],
                "lightgbm_pred": 0.0,
                "lightgbm_p95": None,
                "seasonal_naive_pred": None,
            },
        )
        if r["model_version"] == ml_version:
            entry["lightgbm_pred"] = round(float(r["prediction"]), 2)
            entry["lightgbm_p95"] = (
                round(float(r["prediction_p95"]), 2)
                if r["prediction_p95"] is not None
                else None
            )
        elif r["model_version"] == baseline_version:
            entry["seasonal_naive_pred"] = round(float(r["prediction"]), 2)

    forecasts = [by_date[d] for d in sorted(by_date.keys())]

    sales_df = get_sales_dataframe()
    global_max_date = pd.Timestamp(sales_df["date"].max())
    sku_df = sales_df[
        (sales_df["store_id"].astype(str) == store_id)
        & (sales_df["item_id"].astype(str) == selected_item)
    ].sort_values("date")

    hist_slice = sku_df.tail(history_days)
    history = [
        {
            "date": pd.Timestamp(r.date).strftime("%Y-%m-%d"),
            "actual_sales": int(r.sales),
            "sell_price": round(float(r.sell_price), 2),
        }
        for r in hist_slice.itertuples(index=False)
    ]

    holdout_comparison = _compute_sku_holdout_comparison(
        sku_df,
        global_max_date=global_max_date,
        horizon_days=28,
    )
    metrics_doc = load_model_metrics()
    sku_rmse = float(
        metrics_doc.get("per_sku_val_rmse", {}).get(f"{store_id}::{selected_item}", 1.0)
    )

    return ForecastsResponse(
        item_id=selected_item,
        store_id=store_id,
        dept_id=selected_meta["dept_id"],
        cat_id=selected_meta["cat_id"],
        horizon=horizon,
        sku_validation_rmse=round(sku_rmse, 4),
        disclaimer=(
            "Point forecasts are statistical expected-demand estimates derived from "
            "historical M5-style sales patterns, not guaranteed sales outcomes."
        ),
        available_items=available_items,
        history=history,
        holdout_comparison=holdout_comparison,
        forecasts=forecasts,
    )
