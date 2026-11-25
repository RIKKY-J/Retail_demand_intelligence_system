"""Simple textbook inventory formulas and single-table SQLite helpers."""

from __future__ import annotations

import math
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

REPO_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = REPO_ROOT / "data" / "inventory.db"

SERVICE_LEVEL_Z = 1.65  # ~95% service level


def calculate_safety_stock(sku_rmse: float, lead_time_days: int) -> float:
    """Safety Stock = 1.65 * sku_rmse * sqrt(lead_time_days)."""
    return round(SERVICE_LEVEL_Z * max(0.0, float(sku_rmse)) * math.sqrt(max(1, int(lead_time_days))), 2)


def calculate_reorder_point(
    daily_forecasts: Sequence[float],
    lead_time_days: int,
    safety_stock: float,
) -> float:
    """Reorder Point = forecast_lead_demand + safety_stock."""
    arr = [max(0.0, float(v)) for v in daily_forecasts] or [0.0]
    if len(arr) >= lead_time_days:
        lead_demand = sum(arr[:lead_time_days])
    else:
        avg_daily = sum(arr) / len(arr)
        lead_demand = sum(arr) + (lead_time_days - len(arr)) * avg_daily
    return round(lead_demand + safety_stock, 2)


def calculate_recommended_order_qty(current_stock: int, reorder_point: float) -> int:
    """Recommended Order Qty = max(0, ceil(reorder_point - current_stock))."""
    return max(0, int(math.ceil(reorder_point - int(current_stock))))


def classify_stock_status(current_stock: int, reorder_point: float) -> str:
    """Classify SKU into Low Stock (Reorder), Overstock, or Healthy."""
    if current_stock <= reorder_point:
        return "Low Stock (Reorder)"
    if current_stock > 2.0 * reorder_point:
        return "Overstock"
    return "Healthy"


def compute_inventory_item(
    item_id: str,
    cat_id: str,
    current_stock: int,
    lead_time_days: int,
    updated_at: str,
    sku_rmse: float,
    daily_forecasts: Sequence[float],
) -> dict:
    """Compute Safety Stock, ROP, Order Qty, and Status for one SKU."""
    ss = calculate_safety_stock(sku_rmse=sku_rmse, lead_time_days=lead_time_days)
    rop = calculate_reorder_point(
        daily_forecasts=daily_forecasts,
        lead_time_days=lead_time_days,
        safety_stock=ss,
    )
    order_qty = calculate_recommended_order_qty(current_stock=current_stock, reorder_point=rop)
    status = classify_stock_status(current_stock=current_stock, reorder_point=rop)

    return {
        "item_id": item_id,
        "cat_id": cat_id,
        "current_stock": int(current_stock),
        "lead_time_days": int(lead_time_days),
        "safety_stock": ss,
        "reorder_point": rop,
        "recommended_order_qty": order_qty,
        "status": status,
        "updated_at": updated_at,
    }


def get_inventory_rows(db_path: Path = DB_PATH) -> list[dict]:
    """Fetch all rows from the single `inventory` SQLite table."""
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT item_id, cat_id, current_stock, lead_time_days, updated_at FROM inventory ORDER BY item_id"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def update_inventory_row(
    item_id: str,
    current_stock: int | None = None,
    lead_time_days: int | None = None,
    db_path: Path = DB_PATH,
) -> dict | None:
    """Update `current_stock` and/or `lead_time_days` in SQLite and return the row."""
    now_iso = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        existing = conn.execute(
            "SELECT item_id, cat_id, current_stock, lead_time_days FROM inventory WHERE item_id = ?",
            (item_id,),
        ).fetchone()
        if existing is None:
            return None

        new_stock = int(current_stock) if current_stock is not None else int(existing["current_stock"])
        new_lead = int(lead_time_days) if lead_time_days is not None else int(existing["lead_time_days"])

        conn.execute(
            """
            UPDATE inventory
            SET current_stock = ?, lead_time_days = ?, updated_at = ?
            WHERE item_id = ?
            """,
            (new_stock, new_lead, now_iso, item_id),
        )
        conn.commit()

        updated = conn.execute(
            "SELECT item_id, cat_id, current_stock, lead_time_days, updated_at FROM inventory WHERE item_id = ?",
            (item_id,),
        ).fetchone()
        return dict(updated) if updated else None
    finally:
        conn.close()
