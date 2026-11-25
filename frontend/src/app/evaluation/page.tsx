"use client";

import React, { useEffect, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { fetchEvaluation } from "@/lib/api";
import type { EvaluationResponse } from "@/lib/types";
import { KpiCard } from "@/components/inventory/KpiCard";
import { BacktestBarChart } from "@/components/charts/BacktestBarChart";

export default function EvaluationPage() {
  const [data, setData] = useState<EvaluationResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    fetchEvaluation()
      .then((res) => {
        if (active) {
          setData(res);
          setError(null);
        }
      })
      .catch((err) => {
        if (active) setError(err instanceof Error ? err.message : "Failed to load evaluation");
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, []);

  if (loading && !data) {
    return <div className="p-8 text-sm text-slate-500">Loading model evaluation...</div>;
  }

  if (error || !data) {
    return (
      <div className="rounded-xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-700">
        {error ?? "Unable to load evaluation metrics"}
      </div>
    );
  }

  const bt = data.policy_backtest_28d;
  const h28 = data.horizon_metrics.find((h) => h.horizon_days === 28);

  const horizonRmseChart = data.horizon_metrics.map((h) => ({
    horizon: `${h.horizon_days}d`,
    LightGBM: h.lightgbm.rmse,
    SeasonalNaive: h.seasonal_naive.rmse,
  }));

  const backtestComparisonChart = [
    {
      metric: "Holding Cost ($)",
      SeasonalNaive: bt.seasonal_naive.holding_cost,
      LightGBM: bt.lightgbm.holding_cost,
    },
    {
      metric: "Stockout Cost ($)",
      SeasonalNaive: bt.seasonal_naive.stockout_cost,
      LightGBM: bt.lightgbm.stockout_cost,
    },
    {
      metric: "Total Policy Cost ($)",
      SeasonalNaive: bt.seasonal_naive.total_policy_cost,
      LightGBM: bt.lightgbm.total_policy_cost,
    },
  ];

  const costSavings = bt.comparison.total_policy_cost_savings;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-xl font-bold text-slate-900">
            Model Evaluation & 28-Day Financial Policy Backtest
          </h2>
          <p className="text-sm text-slate-500">
            Holdout ({data.split.test_start} to {data.split.test_end}) · Unmet demand:{" "}
            <span className="font-semibold">{bt.unmet_demand_mode}</span> · Holding rate:{" "}
            {(bt.annual_holding_rate * 100).toFixed(0)}%/yr · Stockout penalty:{" "}
            {bt.stockout_penalty_multiplier}× unit cost
          </p>
        </div>
      </div>

      {/* Top Metric Cards */}
      {h28 && (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-5">
          <KpiCard
            title="28d LightGBM RMSE"
            value={h28.lightgbm.rmse.toFixed(3)}
            subtitle={`vs. Baseline ${h28.seasonal_naive.rmse.toFixed(3)}`}
            accent="blue"
          />
          <KpiCard
            title="28d LightGBM WMAPE"
            value={`${(h28.lightgbm.wmape * 100).toFixed(1)}%`}
            subtitle={`vs. Baseline ${(h28.seasonal_naive.wmape * 100).toFixed(1)}%`}
            accent="emerald"
          />
          <KpiCard
            title="LightGBM Fill Rate (28d)"
            value={`${bt.lightgbm.fill_rate_pct}%`}
            subtitle={`Baseline: ${bt.seasonal_naive.fill_rate_pct}%`}
          />
          <KpiCard
            title="Avg Daily On-Hand / SKU"
            value={bt.lightgbm.avg_daily_on_hand_per_sku.toFixed(2)}
            subtitle={`Delta vs. Baseline: ${bt.comparison.avg_on_hand_delta_per_sku} units`}
            accent="amber"
          />
          <KpiCard
            title="Total Policy Cost (28d)"
            value={`$${bt.lightgbm.total_policy_cost.toFixed(2)}`}
            subtitle={
              costSavings >= 0
                ? `Saves $${costSavings.toFixed(2)} (${bt.comparison.total_policy_cost_savings_pct}%) vs. Baseline $${bt.seasonal_naive.total_policy_cost.toFixed(2)}`
                : `Baseline: $${bt.seasonal_naive.total_policy_cost.toFixed(2)}`
            }
            accent="emerald"
          />
        </div>
      )}

      {/* Charts */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
          <h3 className="mb-1 text-sm font-semibold text-slate-900">
            Forecast RMSE Across Horizons (7d, 14d, 28d)
          </h3>
          <p className="mb-4 text-xs text-slate-500">Lower RMSE indicates tighter prediction accuracy</p>
          <div className="h-72 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={horizonRmseChart}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                <XAxis dataKey="horizon" tick={{ fontSize: 12, fill: "#475569" }} />
                <YAxis tick={{ fontSize: 12, fill: "#64748b" }} />
                <Tooltip />
                <Legend />
                <Bar dataKey="SeasonalNaive" name="Seasonal Naive" fill="#94a3b8" radius={[6, 6, 0, 0]} />
                <Bar dataKey="LightGBM" name="LightGBM (Tweedie)" fill="#2563eb" radius={[6, 6, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
          <h3 className="mb-1 text-sm font-semibold text-slate-900">
            28-Day Financial Policy Cost Comparison ($)
          </h3>
          <p className="mb-4 text-xs text-slate-500">
            Holding Cost + Stockout Penalty Cost across {bt.lightgbm.skus_evaluated} SKUs
          </p>
          <BacktestBarChart data={backtestComparisonChart} />
        </div>
      </div>

      {/* Horizon & Financial Tables */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
          <h3 className="mb-3 text-sm font-semibold text-slate-900">
            Multi-Horizon Accuracy Comparison
          </h3>
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead>
                <tr className="border-b border-slate-200 text-slate-500">
                  <th className="py-2 pr-3 font-medium">Horizon</th>
                  <th className="py-2 pr-3 font-medium">Model</th>
                  <th className="py-2 pr-3 text-right font-medium">MAE</th>
                  <th className="py-2 pr-3 text-right font-medium">RMSE</th>
                  <th className="py-2 pr-3 text-right font-medium">WMAPE</th>
                  <th className="py-2 text-right font-medium">Bias</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {data.horizon_metrics.flatMap((h) => [
                  <tr key={`lgbm-${h.horizon_days}`} className="bg-blue-50/40">
                    <td className="py-2 pr-3 font-semibold text-slate-800">{h.horizon_days}d</td>
                    <td className="py-2 pr-3 font-semibold text-blue-700">LightGBM</td>
                    <td className="py-2 pr-3 text-right">{h.lightgbm.mae.toFixed(4)}</td>
                    <td className="py-2 pr-3 text-right">{h.lightgbm.rmse.toFixed(4)}</td>
                    <td className="py-2 pr-3 text-right">{(h.lightgbm.wmape * 100).toFixed(2)}%</td>
                    <td className="py-2 text-right">{(h.lightgbm.forecast_bias * 100).toFixed(2)}%</td>
                  </tr>,
                  <tr key={`base-${h.horizon_days}`}>
                    <td className="py-2 pr-3 text-slate-500">{h.horizon_days}d</td>
                    <td className="py-2 pr-3 text-slate-600">Seasonal Naive</td>
                    <td className="py-2 pr-3 text-right">{h.seasonal_naive.mae.toFixed(4)}</td>
                    <td className="py-2 pr-3 text-right">{h.seasonal_naive.rmse.toFixed(4)}</td>
                    <td className="py-2 pr-3 text-right">
                      {(h.seasonal_naive.wmape * 100).toFixed(2)}%
                    </td>
                    <td className="py-2 text-right">
                      {(h.seasonal_naive.forecast_bias * 100).toFixed(2)}%
                    </td>
                  </tr>,
                ])}
              </tbody>
            </table>
          </div>
        </div>

        <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
          <h3 className="mb-3 text-sm font-semibold text-slate-900">
            28-Day Operational & Financial Backtest Breakdown
          </h3>
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead>
                <tr className="border-b border-slate-200 text-slate-500">
                  <th className="py-2 pr-3 font-medium">Policy Metric</th>
                  <th className="py-2 pr-3 text-right font-medium">Seasonal Naive</th>
                  <th className="py-2 text-right font-medium">LightGBM (Tweedie)</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                <tr>
                  <td className="py-2 pr-3 font-medium text-slate-700">Total Demand (Units)</td>
                  <td className="py-2 pr-3 text-right">{bt.seasonal_naive.total_actual_demand}</td>
                  <td className="py-2 text-right">{bt.lightgbm.total_actual_demand}</td>
                </tr>
                <tr>
                  <td className="py-2 pr-3 font-medium text-slate-700">Lost Sales (Stockout Units)</td>
                  <td className="py-2 pr-3 text-right">{bt.seasonal_naive.total_lost_sales}</td>
                  <td className="py-2 text-right font-semibold text-blue-700">
                    {bt.lightgbm.total_lost_sales}
                  </td>
                </tr>
                <tr>
                  <td className="py-2 pr-3 font-medium text-slate-700">Fill Rate (%)</td>
                  <td className="py-2 pr-3 text-right">{bt.seasonal_naive.fill_rate_pct}%</td>
                  <td className="py-2 text-right font-semibold text-blue-700">
                    {bt.lightgbm.fill_rate_pct}%
                  </td>
                </tr>
                <tr>
                  <td className="py-2 pr-3 font-medium text-slate-700">Avg Daily On-Hand / SKU</td>
                  <td className="py-2 pr-3 text-right">
                    {bt.seasonal_naive.avg_daily_on_hand_per_sku}
                  </td>
                  <td className="py-2 text-right font-semibold text-emerald-700">
                    {bt.lightgbm.avg_daily_on_hand_per_sku}
                  </td>
                </tr>
                <tr>
                  <td className="py-2 pr-3 font-medium text-slate-700">Holding Cost ($)</td>
                  <td className="py-2 pr-3 text-right">${bt.seasonal_naive.holding_cost.toFixed(2)}</td>
                  <td className="py-2 text-right font-semibold text-emerald-700">
                    ${bt.lightgbm.holding_cost.toFixed(2)}
                  </td>
                </tr>
                <tr>
                  <td className="py-2 pr-3 font-medium text-slate-700">Stockout Cost ($)</td>
                  <td className="py-2 pr-3 text-right">${bt.seasonal_naive.stockout_cost.toFixed(2)}</td>
                  <td className="py-2 text-right font-semibold text-blue-700">
                    ${bt.lightgbm.stockout_cost.toFixed(2)}
                  </td>
                </tr>
                <tr className="bg-slate-50 font-bold">
                  <td className="py-2.5 pr-3 text-slate-900">Total Policy Cost ($)</td>
                  <td className="py-2.5 pr-3 text-right text-slate-800">
                    ${bt.seasonal_naive.total_policy_cost.toFixed(2)}
                  </td>
                  <td className="py-2.5 text-right text-emerald-700">
                    ${bt.lightgbm.total_policy_cost.toFixed(2)}
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
}
