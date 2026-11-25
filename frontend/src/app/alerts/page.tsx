"use client";

import React, { useEffect, useState } from "react";
import { Download } from "lucide-react";
import { fetchAlerts } from "@/lib/api";
import type { AlertsResponse } from "@/lib/types";
import { StatusBadge } from "@/components/inventory/StatusBadge";
import { SimulatedBadge } from "@/components/inventory/SimulatedBadge";

type AlertTab = "all" | "stockout" | "reorder" | "overstock";

export default function AlertsPage() {
  const [tab, setTab] = useState<AlertTab>("all");
  const [data, setData] = useState<AlertsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    setLoading(true);
    fetchAlerts({ alert_type: tab })
      .then((res) => {
        if (active) {
          setData(res);
          setError(null);
        }
      })
      .catch((err) => {
        if (active) setError(err instanceof Error ? err.message : "Failed to load alerts");
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [tab]);

  function exportCsv() {
    if (!data || data.items.length === 0) return;
    const headers = [
      "item_id",
      "store_id",
      "cat_id",
      "status",
      "on_hand",
      "on_order",
      "inventory_position",
      "safety_stock",
      "reorder_point",
      "target_stock",
      "recommended_order_qty",
      "alert_reasons",
    ];
    const rows = data.items.map((item) => [
      item.item_id,
      item.store_id,
      item.cat_id,
      item.status,
      item.on_hand,
      item.on_order,
      item.inventory_position,
      item.safety_stock,
      item.reorder_point,
      item.target_stock,
      item.recommended_order_qty,
      `"${item.alert_reasons.join("; ").replace(/"/g, '""')}"`,
    ]);
    const csv = [headers.join(","), ...rows.map((r) => r.join(","))].join("\n");
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `stock_alerts_${tab}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  }

  const tabs: { key: AlertTab; label: string; count?: number }[] = [
    { key: "all", label: "All Alerts", count: data?.counts.all },
    { key: "stockout", label: "Potential Stockout", count: data?.counts.potential_stockout },
    { key: "reorder", label: "Reorder Required", count: data?.counts.reorder_required },
    { key: "overstock", label: "Possible Overstock", count: data?.counts.possible_overstock },
  ];

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-xl font-bold text-slate-900">Stock Alerts & Replenishment</h2>
          <p className="text-sm text-slate-500">
            Actionable exception queues computed from simulated inventory and LightGBM demand forecasts.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <SimulatedBadge />
          <button
            type="button"
            onClick={exportCsv}
            disabled={!data || data.items.length === 0}
            className="inline-flex items-center gap-2 rounded-lg bg-slate-900 px-3.5 py-2 text-xs font-semibold text-white hover:bg-slate-800 disabled:opacity-40"
          >
            <Download className="h-3.5 w-3.5" />
            Export CSV
          </button>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex flex-wrap gap-2">
        {tabs.map((t) => (
          <button
            key={t.key}
            type="button"
            onClick={() => setTab(t.key)}
            className={`inline-flex items-center gap-2 rounded-lg border px-3.5 py-2 text-xs font-semibold transition-colors ${
              tab === t.key
                ? "border-blue-600 bg-blue-600 text-white"
                : "border-slate-200 bg-white text-slate-700 hover:bg-slate-50"
            }`}
          >
            <span>{t.label}</span>
            {t.count !== undefined && (
              <span
                className={`rounded-full px-2 py-0.5 text-[11px] ${
                  tab === t.key ? "bg-blue-500 text-white" : "bg-slate-100 text-slate-600"
                }`}
              >
                {t.count}
              </span>
            )}
          </button>
        ))}
      </div>

      {error && (
        <div className="rounded-xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-700">
          {error}
        </div>
      )}

      <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
        {loading && !data ? (
          <div className="py-8 text-center text-sm text-slate-500">Loading alerts...</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead>
                <tr className="border-b border-slate-200 text-slate-500">
                  <th className="py-2 pr-3 font-medium">SKU</th>
                  <th className="py-2 pr-3 font-medium">Category</th>
                  <th className="py-2 pr-3 font-medium">Status</th>
                  <th className="py-2 pr-3 text-right font-medium">On-Hand</th>
                  <th className="py-2 pr-3 text-right font-medium">IP</th>
                  <th className="py-2 pr-3 text-right font-medium">ROP</th>
                  <th className="py-2 pr-3 text-right font-medium">Target</th>
                  <th className="py-2 pr-3 text-right font-medium">Order Qty</th>
                  <th className="py-2 font-medium">Triggered Rules</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {(data?.items ?? []).map((item) => (
                  <tr key={item.item_id} className="hover:bg-slate-50">
                    <td className="py-2.5 pr-3 font-semibold text-slate-900">{item.item_id}</td>
                    <td className="py-2.5 pr-3 text-slate-600">{item.cat_id}</td>
                    <td className="py-2.5 pr-3">
                      <StatusBadge status={item.status} />
                    </td>
                    <td className="py-2.5 pr-3 text-right">{item.on_hand}</td>
                    <td className="py-2.5 pr-3 text-right">{item.inventory_position}</td>
                    <td className="py-2.5 pr-3 text-right">{item.reorder_point.toFixed(1)}</td>
                    <td className="py-2.5 pr-3 text-right">{item.target_stock.toFixed(1)}</td>
                    <td className="py-2.5 pr-3 text-right font-bold text-blue-700">
                      {item.recommended_order_qty}
                    </td>
                    <td className="py-2.5">
                      <div className="flex flex-wrap gap-1">
                        {item.alert_reasons.map((reason) => (
                          <span
                            key={reason}
                            className="rounded bg-slate-100 px-2 py-0.5 text-[11px] text-slate-700"
                          >
                            {reason}
                          </span>
                        ))}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
