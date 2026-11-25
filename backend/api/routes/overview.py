"""Overview dashboard endpoint (`GET /api/overview`)."""

from __future__ import annotations

from typing import Optional

import pandas as pd
from fastapi import APIRouter, Query

from backend.api.schemas import OverviewResponse
from backend.src.analytics import (
    get_enriched_inventory,
    get_sales_dataframe,
    load_model_metrics,
)

router = APIRouter(prefix="/api", tags=["overview"])


@router.get("/overview", response_model=OverviewResponse)
def get_overview(
    store_id: Optional[str] = Query(default=None),
    days: int = Query(default=90, ge=7, le=1000),
) -> OverviewResponse:
    """Return sales KPIs, simulated inventory KPIs, trend series, and urgent alerts."""
    df = get_sales_dataframe()
    if store_id:
        df = df[df["store_id"].astype(str) == store_id]

    total_units_sold = int(df["sales"].sum()) if not df.empty else 0
    total_revenue = round(float(df["revenue"].sum()), 2) if not df.empty else 0.0

    max_date = pd.Timestamp(df["date"].max()) if not df.empty else pd.Timestamp.utcnow()
    cutoff = max_date - pd.Timedelta(days=days - 1)
    trend_src = df[df["date"] >= cutoff]

    trend_df = (
        trend_src.groupby("date", as_index=False)
        .agg(units_sold=("sales", "sum"), revenue=("revenue", "sum"))
        .sort_values("date")
    )
    sales_trend = [
        {
            "date": pd.Timestamp(r.date).strftime("%Y-%m-%d"),
            "units_sold": int(r.units_sold),
            "revenue": round(float(r.revenue), 2),
        }
        for r in trend_df.itertuples(index=False)
    ]

    cat_df = (
        df.groupby("cat_id", observed=True, as_index=False)
        .agg(units_sold=("sales", "sum"), sku_count=("item_id", "nunique"))
        .sort_values("units_sold", ascending=False)
    )
    category_breakdown = [
        {
            "cat_id": str(r.cat_id),
            "units_sold": int(r.units_sold),
            "sku_count": int(r.sku_count),
        }
        for r in cat_df.itertuples(index=False)
    ]

    inv_items = get_enriched_inventory(store_id=store_id)
    status_counts = {
        "Healthy": 0,
        "Reorder required": 0,
        "Potential stockout": 0,
        "Possible overstock": 0,
    }
    recommended_order_units = 0
    for item in inv_items:
        status_counts[item["status"]] = status_counts.get(item["status"], 0) + 1
        recommended_order_units += int(item["recommended_order_qty"])

    metrics_doc = load_model_metrics()
    fill_rate = (
        metrics_doc.get("policy_backtest_28d", {})
        .get("lightgbm", {})
        .get("fill_rate_pct")
    )

    urgent = [
        item
        for item in inv_items
        if item["is_potential_stockout"] or item["is_reorder_required"]
    ]
    urgent.sort(
        key=lambda x: (
            0 if x["is_potential_stockout"] else 1,
            -x["recommended_order_qty"],
        )
    )

    return OverviewResponse(
        kpis={
            "total_units_sold": total_units_sold,
            "total_revenue": total_revenue,
            "monitored_skus": len(inv_items),
            "healthy_count": status_counts["Healthy"],
            "reorder_alerts": sum(1 for i in inv_items if i["is_reorder_required"]),
            "potential_stockouts": sum(1 for i in inv_items if i["is_potential_stockout"]),
            "possible_overstock": sum(1 for i in inv_items if i["is_possible_overstock"]),
            "recommended_order_units": recommended_order_units,
            "avg_fill_rate_pct": fill_rate,
            "is_simulated_inventory": True,
        },
        sales_trend=sales_trend,
        status_breakdown=[
            {"status": k, "count": v} for k, v in status_counts.items()
        ],
        category_breakdown=category_breakdown,
        recent_alerts=urgent[:5],
    )
