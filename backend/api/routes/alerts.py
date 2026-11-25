"""Stock alerts endpoint (`GET /api/alerts`)."""

from __future__ import annotations

from typing import Literal, Optional

from fastapi import APIRouter, Query

from backend.api.schemas import AlertsResponse
from backend.src.analytics import get_enriched_inventory

router = APIRouter(prefix="/api", tags=["alerts"])


@router.get("/alerts", response_model=AlertsResponse)
def get_alerts(
    store_id: Optional[str] = Query(default=None),
    cat_id: Optional[str] = Query(default=None),
    alert_type: Literal["all", "reorder", "stockout", "overstock"] = Query(default="all"),
) -> AlertsResponse:
    """Return filtered lists of reorder-required, potential stockout, and overstock items."""
    items = get_enriched_inventory(store_id=store_id, cat_id=cat_id)

    reorder_items = [i for i in items if i["is_reorder_required"]]
    stockout_items = [i for i in items if i["is_potential_stockout"]]
    overstock_items = [i for i in items if i["is_possible_overstock"]]
    any_alert = [
        i
        for i in items
        if i["is_reorder_required"] or i["is_potential_stockout"] or i["is_possible_overstock"]
    ]

    if alert_type == "reorder":
        selected = reorder_items
    elif alert_type == "stockout":
        selected = stockout_items
    elif alert_type == "overstock":
        selected = overstock_items
    else:
        selected = any_alert

    selected.sort(
        key=lambda x: (
            0 if x["is_potential_stockout"] else (1 if x["is_reorder_required"] else 2),
            -x["recommended_order_qty"],
            x["item_id"],
        )
    )

    return AlertsResponse(
        counts={
            "all": len(any_alert),
            "reorder_required": len(reorder_items),
            "potential_stockout": len(stockout_items),
            "possible_overstock": len(overstock_items),
        },
        items=selected,
        is_simulated_inventory=True,
    )
