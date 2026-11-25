"use client";

import React, { useEffect, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { fetchAnalytics } from "@/lib/api";
import type { AnalyticsResponse } from "@/lib/types";

export default function AnalyticsPage() {
  const [data, setData] = useState<AnalyticsResponse | null>(null);
  const [catId, setCatId] = useState<string>("");
  const [granularity, setGranularity] = useState<"daily" | "weekly" | "monthly">("weekly");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    setLoading(true);
    fetchAnalytics({
      cat_id: catId || undefined,
      granularity,
    })
      .then((res) => {
        if (active) {
          setData(res);
          setError(null);
        }
      })
      .catch((err) => {
        if (active) setError(err instanceof Error ? err.message : "Failed to load analytics");
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [catId, granularity]);

  if (loading && !data) {
    return <div className="p-8 text-sm text-slate-500">Loading sales analytics...</div>;
  }

  if (error || !data) {
    return (
      <div className="rounded-xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-700">
        {error ?? "Unable to load analytics"}
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-xl font-bold text-slate-900">Sales & Demand Analytics</h2>
          <p className="text-sm text-slate-500">
            Explore seasonal trends, category/weekday patterns, price vs. demand, and SKU rankings.
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <select
            value={catId}
            onChange={(e) => setCatId(e.target.value)}
            className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-xs font-medium text-slate-700"
          >
            <option value="">All Categories</option>
            {data.filters.categories.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>

          <select
            value={granularity}
            onChange={(e) =>
              setGranularity(e.target.value as "daily" | "weekly" | "monthly")
            }
            className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-xs font-medium text-slate-700"
          >
            <option value="daily">Daily</option>
            <option value="weekly">Weekly</option>
            <option value="monthly">Monthly</option>
          </select>
        </div>
      </div>

      {/* Sales Trend & Weekday Pattern */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm lg:col-span-2">
          <h3 className="mb-1 text-sm font-semibold text-slate-900">
            Sales Volume & Revenue Trend ({granularity})
          </h3>
          <p className="mb-4 text-xs text-slate-500">
            Window: {data.filters.min_date} to {data.filters.max_date}
          </p>
          <div className="h-72 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={data.sales_trend}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                <XAxis dataKey="period" tick={{ fontSize: 11, fill: "#64748b" }} minTickGap={20} />
                <YAxis yAxisId="left" tick={{ fontSize: 11, fill: "#64748b" }} />
                <YAxis yAxisId="right" orientation="right" tick={{ fontSize: 11, fill: "#64748b" }} />
                <Tooltip />
                <Legend />
                <Line
                  yAxisId="left"
                  type="monotone"
                  dataKey="units_sold"
                  name="Units Sold"
                  stroke="#2563eb"
                  strokeWidth={2}
                  dot={false}
                />
                <Line
                  yAxisId="right"
                  type="monotone"
                  dataKey="revenue"
                  name="Revenue ($)"
                  stroke="#10b981"
                  strokeWidth={2}
                  dot={false}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
          <h3 className="mb-1 text-sm font-semibold text-slate-900">Weekday Seasonality</h3>
          <p className="mb-4 text-xs text-slate-500">Average daily units per SKU by weekday</p>
          <div className="h-72 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={data.weekday_pattern}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                <XAxis dataKey="weekday" tick={{ fontSize: 11, fill: "#64748b" }} />
                <YAxis tick={{ fontSize: 11, fill: "#64748b" }} />
                <Tooltip />
                <Bar dataKey="avg_units" name="Avg Units / SKU" fill="#2563eb" radius={[6, 6, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>

      {/* Category Comparison & Price vs Demand */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
          <h3 className="mb-1 text-sm font-semibold text-slate-900">Category Performance</h3>
          <p className="mb-4 text-xs text-slate-500">Units sold & revenue across categories</p>
          <div className="h-64 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={data.category_comparison}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                <XAxis dataKey="cat_id" tick={{ fontSize: 12, fill: "#334155" }} />
                <YAxis tick={{ fontSize: 11, fill: "#64748b" }} />
                <Tooltip />
                <Legend />
                <Bar dataKey="total_units" name="Total Units" fill="#2563eb" radius={[6, 6, 0, 0]} />
                <Bar dataKey="total_revenue" name="Revenue ($)" fill="#0ea5e9" radius={[6, 6, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
          <h3 className="mb-1 text-sm font-semibold text-slate-900">Price vs. Demand Trend</h3>
          <p className="mb-4 text-xs text-slate-500">Average sell price ($) vs. average unit sales</p>
          <div className="h-64 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={data.price_demand}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                <XAxis dataKey="period" tick={{ fontSize: 11, fill: "#64748b" }} minTickGap={20} />
                <YAxis yAxisId="left" tick={{ fontSize: 11, fill: "#64748b" }} />
                <YAxis yAxisId="right" orientation="right" tick={{ fontSize: 11, fill: "#64748b" }} />
                <Tooltip />
                <Legend />
                <Line
                  yAxisId="left"
                  type="monotone"
                  dataKey="avg_price"
                  name="Avg Price ($)"
                  stroke="#f59e0b"
                  strokeWidth={2}
                  dot={false}
                />
                <Line
                  yAxisId="right"
                  type="monotone"
                  dataKey="avg_units"
                  name="Avg Units / SKU"
                  stroke="#2563eb"
                  strokeWidth={2}
                  dot={false}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>

      {/* Top vs Low Demand Tables */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        {[
          { title: "Top 10 Selling Products", rows: data.top_products },
          { title: "Bottom 10 Low-Demand Products", rows: data.low_demand_products },
        ].map((panel) => (
          <div
            key={panel.title}
            className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm"
          >
            <h3 className="mb-3 text-sm font-semibold text-slate-900">{panel.title}</h3>
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead>
                  <tr className="border-b border-slate-200 text-slate-500">
                    <th className="py-2 pr-3 font-medium">Item ID</th>
                    <th className="py-2 pr-3 font-medium">Category</th>
                    <th className="py-2 pr-3 text-right font-medium">Total Units</th>
                    <th className="py-2 pr-3 text-right font-medium">Avg / Day</th>
                    <th className="py-2 text-right font-medium">Revenue</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {panel.rows.map((r) => (
                    <tr key={r.item_id} className="hover:bg-slate-50">
                      <td className="py-2 pr-3 font-semibold text-slate-800">{r.item_id}</td>
                      <td className="py-2 pr-3 text-slate-600">{r.cat_id}</td>
                      <td className="py-2 pr-3 text-right font-medium">
                        {r.total_units.toLocaleString()}
                      </td>
                      <td className="py-2 pr-3 text-right">{r.avg_daily_units.toFixed(2)}</td>
                      <td className="py-2 text-right">${r.total_revenue.toLocaleString()}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
