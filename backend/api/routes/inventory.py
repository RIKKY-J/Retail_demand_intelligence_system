"""Inventory management endpoints (`GET /api/inventory`, `PATCH /api/inventory/{store_id}/{item_id}`)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from backend.api.schemas import (
    InventoryItemOut,
    InventoryListResponse,
    InventoryPatchRequest,
    TransactionOut,
)
from backend.src.analytics import get_enriched_inventory
from backend.src.database import db_session, get_db_path
from backend.src.inventory import load_inventory_config

router = APIRouter(prefix="/api", tags=["inventory"])


@router.get("/inventory", response_model=InventoryListResponse)
def list_inventory(
    store_id: Optional[str] = Query(default=None),
    cat_id: Optional[str] = Query(default=None),
    status: Optional[str] = Query(default=None),
    search: Optional[str] = Query(default=None),
) -> InventoryListResponse:
    """List simulated inventory items with live Safety Stock, ROP, and order recommendations."""
    all_items = get_enriched_inventory()
    stores = sorted({i["store_id"] for i in all_items})
    categories = sorted({i["cat_id"] for i in all_items})

    filtered = get_enriched_inventory(
        store_id=store_id,
        cat_id=cat_id,
        status_filter=status,
        search=search,
    )

    return InventoryListResponse(
        items=filtered,
        stores=stores,
        categories=categories,
        total=len(filtered),
        is_simulated_inventory=True,
    )


@router.patch("/inventory/{store_id}/{item_id}", response_model=InventoryItemOut)
def update_inventory_item(
    store_id: str,
    item_id: str,
    payload: InventoryPatchRequest,
) -> InventoryItemOut:
    """Update simulated inventory stock or lead-time parameters and log an audit transaction."""
    cfg = load_inventory_config()
    resolved_db = get_db_path(cfg["storage"]["database_path"])
    now_iso = datetime.now(timezone.utc).replace(microsecond=0).isoformat()

    with db_session(resolved_db) as conn:
        existing = conn.execute(
            """
            SELECT on_hand, on_order, backorders, lead_time_days, review_period_days, unit_cost
            FROM inventory
            WHERE store_id = ? AND item_id = ?
            """,
            (store_id, item_id),
        ).fetchone()

        if existing is None:
            raise HTTPException(
                status_code=404,
                detail=f"Inventory record not found for {store_id}/{item_id}",
            )

        new_on_hand = payload.on_hand if payload.on_hand is not None else int(existing["on_hand"])
        new_on_order = payload.on_order if payload.on_order is not None else int(existing["on_order"])
        new_backorders = payload.backorders if payload.backorders is not None else int(existing["backorders"])
        new_lead = payload.lead_time_days if payload.lead_time_days is not None else int(existing["lead_time_days"])
        new_review = (
            payload.review_period_days
            if payload.review_period_days is not None
            else int(existing["review_period_days"])
        )
        new_cost = payload.unit_cost if payload.unit_cost is not None else float(existing["unit_cost"])

        conn.execute(
            """
            UPDATE inventory
            SET on_hand = ?,
                on_order = ?,
                backorders = ?,
                lead_time_days = ?,
                review_period_days = ?,
                unit_cost = ?,
                updated_at = ?
            WHERE store_id = ? AND item_id = ?
            """,
            (
                new_on_hand,
                new_on_order,
                new_backorders,
                new_lead,
                new_review,
                new_cost,
                now_iso,
                store_id,
                item_id,
            ),
        )

        delta_on_hand = new_on_hand - int(existing["on_hand"])
        delta_on_order = new_on_order - int(existing["on_order"])
        if delta_on_hand > 0 and delta_on_order < 0:
            txn_type = "receipt"
        elif delta_on_hand < 0 and payload.notes and "sale" in payload.notes.lower():
            txn_type = "simulated_sale"
        else:
            txn_type = "manual_adjustment"

        note_text = payload.notes or (
            f"Updated stock/policy via UI (on_hand={new_on_hand}, on_order={new_on_order}, "
            f"backorders={new_backorders}, lead_time={new_lead}d, review={new_review}d)"
        )

        conn.execute(
            """
            INSERT INTO inventory_transactions (
                item_id, store_id, transaction_type, quantity, transaction_date, notes
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (item_id, store_id, txn_type, delta_on_hand, now_iso, note_text),
        )

    updated_list = get_enriched_inventory(store_id=store_id)
    for item in updated_list:
        if item["item_id"] == item_id:
            return InventoryItemOut(**item)

    raise HTTPException(status_code=500, detail="Failed to reload updated inventory item")


@router.get("/inventory/{store_id}/{item_id}/transactions", response_model=list[TransactionOut])
def get_item_transactions(
    store_id: str,
    item_id: str,
    limit: int = Query(default=20, ge=1, le=100),
) -> list[TransactionOut]:
    """Return recent simulated inventory audit transactions for an SKU."""
    cfg = load_inventory_config()
    resolved_db = get_db_path(cfg["storage"]["database_path"])
    with db_session(resolved_db) as conn:
        rows = conn.execute(
            """
            SELECT transaction_id, item_id, store_id, transaction_type,
                   quantity, transaction_date, notes
            FROM inventory_transactions
            WHERE store_id = ? AND item_id = ?
            ORDER BY transaction_id DESC
            LIMIT ?
            """,
            (store_id, item_id, limit),
        ).fetchall()

    return [TransactionOut(**dict(r)) for r in rows]
