"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import {
  AlertTriangle,
  ArrowRight,
  Boxes,
  PackageCheck,
  ShoppingCart,
  TrendingUp,
} from "lucide-react";
import { fetchOverview } from "@/lib/api";
import type { OverviewResponse } from "@/lib/types";
import { KpiCard } from "@/components/inventory/KpiCard";
import { StatusBadge } from "@/components/inventory/StatusBadge";
import { SimulatedBadge } from "@/components/inventory/SimulatedBadge";

const STATUS_COLORS: Record<string, string> = {
  Healthy: "#10b981",
  "Reorder required": "#f59e0b",
  "Potential stockout": "#ef4444",
  "Possible overstock": "#0ea5e9",
};

export default function OverviewPage() {
  const [data, setData] = useState<OverviewResponse | null>(null);
  const [days, setDays] = useState<number>(90);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    setLoading(true);
    fetchOverview(undefined, days)
      .then((res) => {
        if (active) {
          setData(res);
          setError(null);
        }
      })
      .catch((err) => {
        if (active) setError(err instanceof Error ? err.message : "Failed to load overview");
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [days]);

  if (loading && !data) {
    return <div className="p-8 text-sm text-slate-500">Loading overview metrics...</div>;
  }

  if (error || !data) {
    return (
      <div className="rounded-xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-700">
        {error ?? "Unable to load overview data. Make sure FastAPI is running on port 8000."}
      </div>
    );
  }

  const { kpis } = data;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-xl font-bold text-slate-900">Overview Dashboard</h2>
          <p className="text-sm text-slate-500">
            Historical M5-formatted sales performance paired with live simulated inventory health.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <SimulatedBadge />
          <select
            value={days}
            onChange={(e) => setDays(Number(e.target.value))}
            className="rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-xs font-medium text-slate-700"
          >
            <option value={30}>Last 30 days</option>
            <option value={90}>Last 90 days</option>
            <option value={180}>Last 180 days</option>
            <option value={365}>Last 365 days</option>
            <option value={913}>Full History (913d)</option>
          </select>
        </div>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-5">
        <KpiCard
          title="Total Units Sold"
          value={kpis.total_units_sold.toLocaleString()}
          subtitle={`Revenue: $${kpis.total_revenue.toLocaleString()}`}
          accent="blue"
          icon={<TrendingUp className="h-4 w-4" />}
        />
        <KpiCard
          title="Monitored SKUs"
          value={kpis.monitored_skus}
          subtitle={`${kpis.healthy_count} Healthy`}
          icon={<Boxes className="h-4 w-4" />}
        />
        <KpiCard
          title="Reorder Alerts"
          value={kpis.reorder_alerts}
          subtitle={`${kpis.recommended_order_units.toLocaleString()} units suggested (incl. stockout-risk SKUs below ROP)`}
          accent="amber"
          icon={<ShoppingCart className="h-4 w-4" />}
        />
        <KpiCard
          title="Potential Stockouts"
          value={kpis.potential_stockouts}
          subtitle="On-hand < lead-time demand"
          accent="rose"
          icon={<AlertTriangle className="h-4 w-4" />}
        />
        <KpiCard
          title="Possible Overstock"
          value={kpis.possible_overstock}
          subtitle={
            kpis.avg_fill_rate_pct !== null
              ? `28d Backtest Fill Rate: ${kpis.avg_fill_rate_pct}%`
              : "On-hand > 1.5x Target"
          }
          accent="emerald"
          icon={<PackageCheck className="h-4 w-4" />}
        />
      </div>

      {/* Charts Row */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm lg:col-span-2">
          <div className="mb-4 flex items-center justify-between">
            <div>
              <h3 className="text-sm font-semibold text-slate-900">
                Daily Unit Sales Trend
              </h3>
              <p className="text-xs text-slate-500">
                Aggregated daily unit volume across store CA_1
              </p>
            </div>
          </div>
          <div className="h-72 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={data.sales_trend}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                <XAxis dataKey="date" tick={{ fontSize: 11, fill: "#64748b" }} minTickGap={24} />
                <YAxis tick={{ fontSize: 11, fill: "#64748b" }} />
                <Tooltip />
                <Area
                  type="monotone"
                  dataKey="units_sold"
                  name="Units Sold"
                  stroke="#2563eb"
                  fill="#dbeafe"
                  strokeWidth={2}
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
          <div className="mb-4 flex items-center justify-between">
            <div>
              <h3 className="text-sm font-semibold text-slate-900">
                Inventory Status Distribution
              </h3>
              <p className="text-xs text-slate-500">Simulated stock health breakdown</p>
            </div>
          </div>
          <div className="h-72 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={data.status_breakdown} layout="vertical" margin={{ left: 20 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                <XAxis type="number" tick={{ fontSize: 11, fill: "#64748b" }} />
                <YAxis
                  type="category"
                  dataKey="status"
                  width={120}
                  tick={{ fontSize: 11, fill: "#334155" }}
                />
                <Tooltip />
                <Bar dataKey="count" name="SKUs" radius={[0, 6, 6, 0]}>
                  {data.status_breakdown.map((entry) => (
                    <Cell
                      key={entry.status}
                      fill={STATUS_COLORS[entry.status] ?? "#64748b"}
                    />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>

      {/* Category & Recent Urgent Alerts */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
          <h3 className="text-sm font-semibold text-slate-900">Category Volume</h3>
          <p className="mb-4 text-xs text-slate-500">Total historical units by M5 category</p>
          <div className="space-y-3">
            {data.category_breakdown.map((cat) => (
              <div
                key={cat.cat_id}
                className="flex items-center justify-between rounded-lg border border-slate-100 bg-slate-50 px-3 py-2.5"
              >
                <div>
                  <div className="text-sm font-semibold text-slate-800">{cat.cat_id}</div>
                  <div className="text-xs text-slate-500">{cat.sku_count} SKUs</div>
                </div>
                <div className="text-sm font-bold text-slate-900">
                  {cat.units_sold.toLocaleString()} units
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm lg:col-span-2">
          <div className="mb-3 flex items-center justify-between">
            <div>
              <h3 className="text-sm font-semibold text-slate-900">
                Top Priority Replenishment Alerts
              </h3>
              <p className="text-xs text-slate-500">
                SKUs currently in Potential Stockout or Reorder Required state
              </p>
            </div>
            <Link
              href="/alerts"
              className="inline-flex items-center gap-1 text-xs font-semibold text-blue-600 hover:text-blue-700"
            >
              View all alerts <ArrowRight className="h-3.5 w-3.5" />
            </Link>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead>
                <tr className="border-b border-slate-200 text-slate-500">
                  <th className="py-2 pr-3 font-medium">SKU</th>
                  <th className="py-2 pr-3 font-medium">Status</th>
                  <th className="py-2 pr-3 font-medium text-right">On-Hand</th>
                  <th className="py-2 pr-3 font-medium text-right">IP</th>
                  <th className="py-2 pr-3 font-medium text-right">ROP</th>
                  <th className="py-2 font-medium text-right">Suggested Order</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {data.recent_alerts.map((item) => (
                  <tr key={item.item_id} className="hover:bg-slate-50">
                    <td className="py-2.5 pr-3 font-semibold text-slate-800">
                      {item.item_id}
                    </td>
                    <td className="py-2.5 pr-3">
                      <StatusBadge status={item.status} />
                    </td>
                    <td className="py-2.5 pr-3 text-right">{item.on_hand}</td>
                    <td className="py-2.5 pr-3 text-right">{item.inventory_position}</td>
                    <td className="py-2.5 pr-3 text-right">{item.reorder_point.toFixed(1)}</td>
                    <td className="py-2.5 text-right font-bold text-blue-700">
                      +{item.recommended_order_qty}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
}
