"use client";

import React, { useEffect, useMemo, useState } from "react";
import { Save, Search } from "lucide-react";
import { fetchInventory, patchInventory } from "@/lib/api";
import type { InventoryItem } from "@/lib/types";
import { StatusBadge } from "@/components/inventory/StatusBadge";

type StatusFilter = "All" | "Low Stock (Reorder)" | "Healthy" | "Overstock";

export default function InventoryPage() {
  const [items, setItems] = useState<InventoryItem[]>([]);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("All");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [stockInput, setStockInput] = useState<number>(0);
  const [leadInput, setLeadInput] = useState<number>(5);
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    fetchInventory()
      .then((res) => {
        if (active) {
          setItems(res.items);
          if (res.items[0]) {
            setSelectedId(res.items[0].item_id);
            setStockInput(res.items[0].current_stock);
            setLeadInput(res.items[0].lead_time_days);
          }
          setError(null);
        }
      })
      .catch((err) => {
        if (active) setError(err instanceof Error ? err.message : "Failed to load inventory");
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, []);

  const filteredItems = useMemo(() => {
    const q = search.trim().toLowerCase();
    return items.filter((item) => {
      const matchesStatus = statusFilter === "All" || item.status === statusFilter;
      const matchesQuery =
        !q ||
        item.item_id.toLowerCase().includes(q) ||
        item.cat_id.toLowerCase().includes(q);
      return matchesStatus && matchesQuery;
    });
  }, [items, search, statusFilter]);

  const selectedItem = useMemo(
    () => items.find((i) => i.item_id === selectedId) ?? null,
    [items, selectedId]
  );

  function selectRow(item: InventoryItem) {
    setSelectedId(item.item_id);
    setStockInput(item.current_stock);
    setLeadInput(item.lead_time_days);
    setMsg(null);
  }

  async function handleSave(e: React.FormEvent) {
    e.preventDefault();
    if (!selectedItem) return;
    setSaving(true);
    setMsg(null);
    try {
      const updated = await patchInventory(selectedItem.item_id, {
        current_stock: Number(stockInput),
        lead_time_days: Number(leadInput),
      });
      setItems((prev) =>
        prev.map((i) => (i.item_id === updated.item_id ? updated : i))
      );
      setMsg("Saved to SQLite and recalculated Safety Stock & Reorder Point.");
    } catch (err) {
      setMsg(err instanceof Error ? err.message : "Update failed");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-bold text-slate-900">Inventory & Reorder Alerts</h2>
        <p className="text-sm text-slate-500">
          Safety Stock = 1.65 × RMSE × √Lead Time · Reorder Point = Lead Demand + Safety Stock
        </p>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap items-center gap-3 rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
        <div className="relative min-w-[220px] flex-1">
          <Search className="absolute left-3 top-2.5 h-4 w-4 text-slate-400" />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search SKU or category..."
            className="w-full rounded-lg border border-slate-300 py-2 pl-9 pr-3 text-sm focus:border-blue-500 focus:outline-none"
          />
        </div>

        <div className="flex flex-wrap gap-1.5">
          {(["All", "Low Stock (Reorder)", "Healthy", "Overstock"] as const).map((st) => (
            <button
              key={st}
              type="button"
              onClick={() => setStatusFilter(st)}
              className={`rounded-lg border px-3 py-1.5 text-xs font-semibold transition-colors ${
                statusFilter === st
                  ? "border-blue-600 bg-blue-600 text-white"
                  : "border-slate-200 bg-white text-slate-700 hover:bg-slate-50"
              }`}
            >
              {st}
            </button>
          ))}
        </div>
      </div>

      {error && (
        <div className="rounded-xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-700">
          {error}
        </div>
      )}

      {/* Inline Update Form */}
      {selectedItem && (
        <form
          onSubmit={handleSave}
          className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm"
        >
          <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
            <div className="flex items-center gap-2.5">
              <span className="text-sm font-bold text-slate-900">
                Edit SKU: {selectedItem.item_id}
              </span>
              <StatusBadge status={selectedItem.status} />
            </div>
            <div className="text-xs text-slate-500">
              ROP: <span className="font-semibold text-slate-800">{selectedItem.reorder_point.toFixed(1)}</span> ·
              Recommended Order:{" "}
              <span className="font-bold text-blue-700">
                {selectedItem.recommended_order_qty} units
              </span>
            </div>
          </div>

          <div className="flex flex-wrap items-end gap-4">
            <label className="block">
              <span className="text-xs font-medium text-slate-600">Current Stock</span>
              <input
                type="number"
                min={0}
                value={stockInput}
                onChange={(e) => setStockInput(Number(e.target.value))}
                className="mt-1 block w-36 rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none"
              />
            </label>

            <label className="block">
              <span className="text-xs font-medium text-slate-600">Lead Time (Days)</span>
              <input
                type="number"
                min={1}
                max={60}
                value={leadInput}
                onChange={(e) => setLeadInput(Number(e.target.value))}
                className="mt-1 block w-36 rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none"
              />
            </label>

            <button
              type="submit"
              disabled={saving}
              className="inline-flex items-center gap-2 rounded-lg bg-blue-600 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-700 disabled:opacity-50"
            >
              <Save className="h-4 w-4" />
              {saving ? "Saving..." : "Save to SQLite"}
            </button>

            {msg && <span className="text-xs font-medium text-emerald-700">{msg}</span>}
          </div>
        </form>
      )}

      {/* Inventory Table */}
      <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
        <div className="mb-3 flex items-center justify-between">
          <h3 className="text-sm font-semibold text-slate-900">
            Monitored SKUs ({filteredItems.length})
          </h3>
          {loading && <span className="text-xs text-slate-400">Loading...</span>}
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead>
              <tr className="border-b border-slate-200 text-slate-500">
                <th className="py-2 pr-3 font-medium">SKU</th>
                <th className="py-2 pr-3 font-medium">Category</th>
                <th className="py-2 pr-3 text-right font-medium">Current Stock</th>
                <th className="py-2 pr-3 text-right font-medium">Lead Time (d)</th>
                <th className="py-2 pr-3 text-right font-medium">Safety Stock</th>
                <th className="py-2 pr-3 text-right font-medium">Reorder Point</th>
                <th className="py-2 pr-3 text-right font-medium">Order Qty</th>
                <th className="py-2 font-medium">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {filteredItems.map((item) => {
                const isSelected = selectedItem?.item_id === item.item_id;
                return (
                  <tr
                    key={item.item_id}
                    onClick={() => selectRow(item)}
                    className={`cursor-pointer transition-colors ${
                      isSelected ? "bg-blue-50/70" : "hover:bg-slate-50"
                    }`}
                  >
                    <td className="py-2.5 pr-3 font-semibold text-slate-900">
                      {item.item_id}
                    </td>
                    <td className="py-2.5 pr-3 text-slate-600">{item.cat_id}</td>
                    <td className="py-2.5 pr-3 text-right">{item.current_stock}</td>
                    <td className="py-2.5 pr-3 text-right">{item.lead_time_days}</td>
                    <td className="py-2.5 pr-3 text-right">{item.safety_stock.toFixed(1)}</td>
                    <td className="py-2.5 pr-3 text-right">{item.reorder_point.toFixed(1)}</td>
                    <td className="py-2.5 pr-3 text-right font-bold text-blue-700">
                      {item.recommended_order_qty}
                    </td>
                    <td className="py-2.5">
                      <StatusBadge status={item.status} />
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
