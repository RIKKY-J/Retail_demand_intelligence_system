"use client";

import React, { useEffect, useState } from "react";
import { patchInventoryItem } from "@/lib/api";
import type { InventoryItem } from "@/lib/types";
import { Save } from "lucide-react";

interface StockUpdateFormProps {
  item: InventoryItem;
  onUpdated: (updated: InventoryItem) => void;
}

export function StockUpdateForm({ item, onUpdated }: StockUpdateFormProps) {
  const [onHand, setOnHand] = useState(item.on_hand);
  const [onOrder, setOnOrder] = useState(item.on_order);
  const [backorders, setBackorders] = useState(item.backorders);
  const [leadTimeDays, setLeadTimeDays] = useState(item.lead_time_days);
  const [reviewPeriodDays, setReviewPeriodDays] = useState(item.review_period_days);
  const [notes, setNotes] = useState("");
  const [saving, setSaving] = useState(false);
  const [feedback, setFeedback] = useState<{ type: "ok" | "err"; msg: string } | null>(
    null
  );

  useEffect(() => {
    setOnHand(item.on_hand);
    setOnOrder(item.on_order);
    setBackorders(item.backorders);
    setLeadTimeDays(item.lead_time_days);
    setReviewPeriodDays(item.review_period_days);
    setNotes("");
    setFeedback(null);
  }, [item]);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    setFeedback(null);
    try {
      const updated = await patchInventoryItem(item.store_id, item.item_id, {
        on_hand: Number(onHand),
        on_order: Number(onOrder),
        backorders: Number(backorders),
        lead_time_days: Number(leadTimeDays),
        review_period_days: Number(reviewPeriodDays),
        notes: notes.trim() || undefined,
      });
      onUpdated(updated);
      setNotes("");
      setFeedback({
        type: "ok",
        msg: "Saved to SQLite and recalculated Safety Stock, ROP, and Order Qty.",
      });
    } catch (err) {
      setFeedback({
        type: "err",
        msg: err instanceof Error ? err.message : "Failed to update inventory",
      });
    } finally {
      setSaving(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
        <label className="block">
          <span className="text-xs font-medium text-slate-600">On-Hand Units</span>
          <input
            type="number"
            min={0}
            value={onHand}
            onChange={(e) => setOnHand(Number(e.target.value))}
            className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none"
          />
        </label>
        <label className="block">
          <span className="text-xs font-medium text-slate-600">On-Order Units</span>
          <input
            type="number"
            min={0}
            value={onOrder}
            onChange={(e) => setOnOrder(Number(e.target.value))}
            className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none"
          />
        </label>
        <label className="block">
          <span className="text-xs font-medium text-slate-600">Backorders</span>
          <input
            type="number"
            min={0}
            value={backorders}
            onChange={(e) => setBackorders(Number(e.target.value))}
            className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none"
          />
        </label>
        <label className="block">
          <span className="text-xs font-medium text-slate-600">Lead Time (Days)</span>
          <input
            type="number"
            min={1}
            max={90}
            value={leadTimeDays}
            onChange={(e) => setLeadTimeDays(Number(e.target.value))}
            className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none"
          />
        </label>
        <label className="block">
          <span className="text-xs font-medium text-slate-600">Review Period (Days)</span>
          <input
            type="number"
            min={1}
            max={90}
            value={reviewPeriodDays}
            onChange={(e) => setReviewPeriodDays(Number(e.target.value))}
            className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none"
          />
        </label>
        <label className="block col-span-2 sm:col-span-1">
          <span className="text-xs font-medium text-slate-600">Audit Note</span>
          <input
            type="text"
            placeholder="e.g., PO receipt"
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none"
          />
        </label>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <button
          type="submit"
          disabled={saving}
          className="inline-flex items-center gap-2 rounded-lg bg-blue-600 px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-blue-700 disabled:opacity-50"
        >
          <Save className="h-4 w-4" />
          {saving ? "Saving..." : "Update Simulated Stock"}
        </button>

        {feedback && (
          <span
            className={`text-xs font-medium ${
              feedback.type === "ok" ? "text-emerald-700" : "text-rose-700"
            }`}
          >
            {feedback.msg}
          </span>
        )}
      </div>
    </form>
  );
}
