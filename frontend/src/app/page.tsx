"use client";

import React, { useEffect, useState } from "react";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { AlertTriangle, Award, Boxes, TrendingUp } from "lucide-react";
import { fetchOverview } from "@/lib/api";
import type { OverviewResponse } from "@/lib/types";
import { KpiCard } from "@/components/inventory/KpiCard";

export default function OverviewPage() {
  const [data, setData] = useState<OverviewResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    fetchOverview()
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
  }, []);

  if (loading && !data) {
    return <div className="p-8 text-sm text-slate-500">Loading overview & model metrics...</div>;
  }

  if (error || !data) {
    return (
      <div className="rounded-xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-700">
        {error ?? "Unable to load overview data."}
      </div>
    );
  }

  const { kpis, model_comparison, split } = data;

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-bold text-slate-900">Overview & Model Comparison</h2>
        <p className="text-sm text-slate-500">
          Store CA_1 (60 balanced M5 SKUs) · 28-day chronological test split ({split.test_start} to{" "}
          {split.test_end})
        </p>
      </div>

      {/* 4 KPI Cards */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <KpiCard
          title="Total Units Sold"
          value={kpis.total_units_sold.toLocaleString()}
          subtitle="Across 60 M5 SKUs (1 year)"
          accent="blue"
          icon={<TrendingUp className="h-4 w-4" />}
        />
        <KpiCard
          title="Monitored SKUs"
          value={kpis.monitored_skus}
          subtitle={`${kpis.healthy_count} Healthy · ${kpis.overstock_count} Overstock`}
          icon={<Boxes className="h-4 w-4" />}
        />
        <KpiCard
          title="Low Stock Alerts"
          value={kpis.low_stock_alerts}
          subtitle="SKUs at or below Reorder Point"
          accent="rose"
          icon={<AlertTriangle className="h-4 w-4" />}
        />
        <KpiCard
          title="Best Model RMSE"
          value={kpis.best_model_rmse !== null ? kpis.best_model_rmse.toFixed(4) : "—"}
          subtitle={`Selected model: ${kpis.best_model}`}
          accent="emerald"
          icon={<Award className="h-4 w-4" />}
        />
      </div>

      {/* Charts */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
          <h3 className="mb-1 text-sm font-semibold text-slate-900">
            Daily Sales Trend (60 SKUs)
          </h3>
          <p className="mb-4 text-xs text-slate-500">Aggregated daily unit sales volume</p>
          <div className="h-72 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={data.daily_sales_trend}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                <XAxis dataKey="date" tick={{ fontSize: 11, fill: "#64748b" }} minTickGap={28} />
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
          <h3 className="mb-1 text-sm font-semibold text-slate-900">
            4-Model Error Comparison (28-Day Holdout)
          </h3>
          <p className="mb-4 text-xs text-slate-500">Lower MAE and RMSE indicate higher accuracy</p>
          <div className="h-72 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={model_comparison}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                <XAxis dataKey="model" tick={{ fontSize: 11, fill: "#475569" }} />
                <YAxis tick={{ fontSize: 11, fill: "#64748b" }} />
                <Tooltip />
                <Legend />
                <Bar dataKey="mae" name="MAE" fill="#60a5fa" radius={[6, 6, 0, 0]} />
                <Bar dataKey="rmse" name="RMSE" fill="#2563eb" radius={[6, 6, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>

      {/* Model Comparison Table */}
      <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
        <h3 className="mb-3 text-sm font-semibold text-slate-900">
          Model Evaluation Table (MAE, RMSE, WMAPE)
        </h3>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead>
              <tr className="border-b border-slate-200 text-slate-500">
                <th className="py-2 pr-4 font-medium">Model</th>
                <th className="py-2 pr-4 text-right font-medium">MAE</th>
                <th className="py-2 pr-4 text-right font-medium">RMSE</th>
                <th className="py-2 text-right font-medium">WMAPE</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {model_comparison.map((row) => {
                const isBest = row.model === kpis.best_model;
                return (
                  <tr
                    key={row.model}
                    className={isBest ? "bg-blue-50/60 font-semibold" : "hover:bg-slate-50"}
                  >
                    <td className="py-2.5 pr-4 text-slate-900">
                      {row.model}
                      {isBest && (
                        <span className="ml-2 rounded-full bg-blue-600 px-2 py-0.5 text-[10px] font-semibold text-white">
                          Best
                        </span>
                      )}
                    </td>
                    <td className="py-2.5 pr-4 text-right">{row.mae.toFixed(4)}</td>
                    <td className="py-2.5 pr-4 text-right">{row.rmse.toFixed(4)}</td>
                    <td className="py-2.5 text-right">{(row.wmape * 100).toFixed(2)}%</td>
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
