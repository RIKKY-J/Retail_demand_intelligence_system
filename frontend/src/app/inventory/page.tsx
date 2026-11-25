"use client";

import React, { useCallback, useEffect, useMemo, useState } from "react";
import { Search } from "lucide-react";
import { fetchInventory, fetchItemTransactions } from "@/lib/api";
import type { InventoryItem, InventoryTransaction } from "@/lib/types";
import { StatusBadge } from "@/components/inventory/StatusBadge";
import { SimulatedBadge } from "@/components/inventory/SimulatedBadge";
import { StockUpdateForm } from "@/components/inventory/StockUpdateForm";

export default function InventoryPage() {
  const [items, setItems] = useState<InventoryItem[]>([]);
  const [categories, setCategories] = useState<string[]>([]);
  const [catFilter, setCatFilter] = useState<string>("");
  const [statusFilter, setStatusFilter] = useState<string>("");
  const [search, setSearch] = useState<string>("");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [transactions, setTransactions] = useState<InventoryTransaction[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadInventory = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetchInventory({
        cat_id: catFilter || undefined,
        status: statusFilter || undefined,
        search: search.trim() || undefined,
      });
      setItems(res.items);
      setCategories(res.categories);
      setSelectedId((prev) => {
        if (prev && res.items.some((i) => i.item_id === prev)) return prev;
        return res.items[0]?.item_id ?? null;
      });
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load inventory");
    } finally {
      setLoading(false);
    }
  }, [catFilter, statusFilter, search]);

  useEffect(() => {
    loadInventory();
  }, [loadInventory]);

  const selectedItem = useMemo(
    () => items.find((i) => i.item_id === selectedId) ?? items[0] ?? null,
    [items, selectedId]
  );

  useEffect(() => {
    if (!selectedItem) return;
    fetchItemTransactions(selectedItem.store_id, selectedItem.item_id, 8)
      .then(setTransactions)
      .catch(() => setTransactions([]));
  }, [selectedItem]);

  function handleItemUpdated(updated: InventoryItem) {
    setItems((prev) =>
      prev.map((i) => (i.item_id === updated.item_id && i.store_id === updated.store_id ? updated : i))
    );
    fetchItemTransactions(updated.store_id, updated.item_id, 8)
      .then(setTransactions)
      .catch(() => {});
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-xl font-bold text-slate-900">Inventory Management</h2>
          <p className="text-sm text-slate-500">
            Monitor simulated stock, forecast-aware safety stock, reorder points, and update parameters live.
          </p>
        </div>
        <SimulatedBadge label="Simulated Inventory · Persisted in SQLite" />
      </div>

      {/* Filters */}
      <div className="flex flex-wrap items-center gap-3 rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
        <div className="relative min-w-[220px] flex-1">
          <Search className="absolute left-3 top-2.5 h-4 w-4 text-slate-400" />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search SKU or department (e.g., FOODS_3_001)..."
            className="w-full rounded-lg border border-slate-300 py-2 pl-9 pr-3 text-sm focus:border-blue-500 focus:outline-none"
          />
        </div>
        <select
          value={catFilter}
          onChange={(e) => setCatFilter(e.target.value)}
          className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-700"
        >
          <option value="">All Categories</option>
          {categories.map((c) => (
            <option key={c} value={c}>
              {c}
            </option>
          ))}
        </select>
        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
          className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-700"
        >
          <option value="">All Statuses</option>
          <option value="Healthy">Healthy</option>
          <option value="Reorder required">Reorder required</option>
          <option value="Potential stockout">Potential stockout</option>
          <option value="Possible overstock">Possible overstock</option>
        </select>
      </div>

      {error && (
        <div className="rounded-xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-700">
          {error}
        </div>
      )}

      {/* Selected SKU Live Panel & Edit Form */}
      {selectedItem && (
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
          <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm lg:col-span-2">
            <div className="mb-4 flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 pb-3">
              <div>
                <div className="flex items-center gap-2.5">
                  <h3 className="text-base font-bold text-slate-900">
                    {selectedItem.item_id}
                  </h3>
                  <StatusBadge status={selectedItem.status} />
                </div>
                <p className="mt-0.5 text-xs text-slate-500">
                  Store {selectedItem.store_id} · {selectedItem.cat_id} / {selectedItem.dept_id} · Val RMSE:{" "}
                  {selectedItem.validation_rmse.toFixed(2)}
                </p>
              </div>
              <div className="text-right">
                <div className="text-xs text-slate-500">Recommended Order</div>
                <div className="text-xl font-bold text-blue-600">
                  {selectedItem.recommended_order_qty} units
                </div>
              </div>
            </div>

            <div className="mb-5 grid grid-cols-2 gap-3 sm:grid-cols-4">
              <div className="rounded-lg bg-slate-50 p-3">
                <div className="text-[11px] font-medium text-slate-500">Inventory Position</div>
                <div className="mt-1 text-lg font-bold text-slate-900">
                  {selectedItem.inventory_position}
                </div>
                <div className="text-[11px] text-slate-400">On-hand + On-order - BO</div>
              </div>
              <div className="rounded-lg bg-slate-50 p-3">
                <div className="text-[11px] font-medium text-slate-500">Safety Stock (95%)</div>
                <div className="mt-1 text-lg font-bold text-slate-900">
                  {selectedItem.safety_stock.toFixed(1)}
                </div>
                <div className="text-[11px] text-slate-400">1.645 × RMSE × √L</div>
              </div>
              <div className="rounded-lg bg-slate-50 p-3">
                <div className="text-[11px] font-medium text-slate-500">Reorder Point (ROP)</div>
                <div className="mt-1 text-lg font-bold text-slate-900">
                  {selectedItem.reorder_point.toFixed(1)}
                </div>
                <div className="text-[11px] text-slate-400">
                  Lead Demand: {selectedItem.lead_time_demand.toFixed(1)}
                </div>
              </div>
              <div className="rounded-lg bg-slate-50 p-3">
                <div className="text-[11px] font-medium text-slate-500">Target Stock</div>
                <div className="mt-1 text-lg font-bold text-slate-900">
                  {selectedItem.target_stock.toFixed(1)}
                </div>
                <div className="text-[11px] text-slate-400">
                  L+R={selectedItem.lead_time_days + selectedItem.review_period_days}d cover
                </div>
              </div>
            </div>

            <StockUpdateForm item={selectedItem} onUpdated={handleItemUpdated} />
          </div>

          <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
            <h3 className="text-sm font-semibold text-slate-900">
              Recent Audit Log ({selectedItem.item_id})
            </h3>
            <p className="mb-3 text-xs text-slate-500">
              SQLite `inventory_transactions` history
            </p>
            <div className="space-y-2.5">
              {transactions.map((t) => (
                <div
                  key={t.transaction_id}
                  className="rounded-lg border border-slate-100 bg-slate-50 p-2.5 text-xs"
                >
                  <div className="flex items-center justify-between font-semibold text-slate-800">
                    <span className="capitalize">{t.transaction_type.replace("_", " ")}</span>
                    <span className={t.quantity >= 0 ? "text-emerald-700" : "text-rose-700"}>
                      {t.quantity >= 0 ? `+${t.quantity}` : t.quantity}
                    </span>
                  </div>
                  <div className="mt-0.5 text-[11px] text-slate-500">{t.transaction_date}</div>
                  {t.notes && <div className="mt-1 text-[11px] text-slate-600">{t.notes}</div>}
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* SKU Table */}
      <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
        <div className="mb-3 flex items-center justify-between">
          <h3 className="text-sm font-semibold text-slate-900">
            Monitored SKUs ({items.length})
          </h3>
          {loading && <span className="text-xs text-slate-400">Refreshing...</span>}
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead>
              <tr className="border-b border-slate-200 text-slate-500">
                <th className="py-2 pr-3 font-medium">Item ID</th>
                <th className="py-2 pr-3 font-medium">Category</th>
                <th className="py-2 pr-3 font-medium">Status</th>
                <th className="py-2 pr-3 text-right font-medium">On-Hand</th>
                <th className="py-2 pr-3 text-right font-medium">On-Order</th>
                <th className="py-2 pr-3 text-right font-medium">IP</th>
                <th className="py-2 pr-3 text-right font-medium">Lead (d)</th>
                <th className="py-2 pr-3 text-right font-medium">Safety Stock</th>
                <th className="py-2 pr-3 text-right font-medium">ROP</th>
                <th className="py-2 text-right font-medium">Order Qty</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {items.map((item) => {
                const isSelected = selectedItem?.item_id === item.item_id;
                return (
                  <tr
                    key={item.item_id}
                    onClick={() => setSelectedId(item.item_id)}
                    className={`cursor-pointer transition-colors ${
                      isSelected ? "bg-blue-50/70" : "hover:bg-slate-50"
                    }`}
                  >
                    <td className="py-2.5 pr-3 font-semibold text-slate-900">
                      {item.item_id}
                    </td>
                    <td className="py-2.5 pr-3 text-slate-600">{item.cat_id}</td>
                    <td className="py-2.5 pr-3">
                      <StatusBadge status={item.status} />
                    </td>
                    <td className="py-2.5 pr-3 text-right">{item.on_hand}</td>
                    <td className="py-2.5 pr-3 text-right">{item.on_order}</td>
                    <td className="py-2.5 pr-3 text-right font-medium">
                      {item.inventory_position}
                    </td>
                    <td className="py-2.5 pr-3 text-right">{item.lead_time_days}</td>
                    <td className="py-2.5 pr-3 text-right">{item.safety_stock.toFixed(1)}</td>
                    <td className="py-2.5 pr-3 text-right">{item.reorder_point.toFixed(1)}</td>
                    <td className="py-2.5 text-right font-bold text-blue-700">
                      {item.recommended_order_qty}
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
