"""Sales and price analytics endpoint (`GET /api/analytics`)."""

from __future__ import annotations

from typing import Literal, Optional

from fastapi import APIRouter, Query

from backend.api.schemas import AnalyticsResponse
from backend.src.analytics import compute_sales_analytics

router = APIRouter(prefix="/api", tags=["analytics"])


@router.get("/analytics", response_model=AnalyticsResponse)
def get_analytics(
    store_id: Optional[str] = Query(default=None),
    cat_id: Optional[str] = Query(default=None),
    start_date: Optional[str] = Query(default=None),
    end_date: Optional[str] = Query(default=None),
    granularity: Literal["daily", "weekly", "monthly"] = Query(default="weekly"),
) -> AnalyticsResponse:
    """Return aggregated trend, top/low SKUs, category/store, weekday, and price-demand analytics."""
    payload = compute_sales_analytics(
        store_id=store_id,
        cat_id=cat_id,
        start_date=start_date,
        end_date=end_date,
        granularity=granularity,
    )
    return AnalyticsResponse(**payload)
