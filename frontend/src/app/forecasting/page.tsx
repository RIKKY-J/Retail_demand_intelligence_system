"use client";

import React, { useEffect, useMemo, useState } from "react";
import { Info } from "lucide-react";
import { fetchForecasts } from "@/lib/api";
import type { ForecastsResponse } from "@/lib/types";
import {
  ForecastChart,
  type ForecastSeriesRow,
} from "@/components/charts/ForecastChart";

export default function ForecastingPage() {
  const [itemId, setItemId] = useState<string>("");
  const [horizon, setHorizon] = useState<7 | 14 | 28>(28);
  const [data, setData] = useState<ForecastsResponse | null>(null);
  const [page, setPage] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    setLoading(true);
    fetchForecasts({
      store_id: "CA_1",
      item_id: itemId || undefined,
      horizon,
      history_days: 60,
    })
      .then((res) => {
        if (active) {
          setData(res);
          if (!itemId) setItemId(res.item_id);
          setPage(0);
          setError(null);
        }
      })
      .catch((err) => {
        if (active) setError(err instanceof Error ? err.message : "Failed to load forecasts");
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [itemId, horizon]);

  const combinedChartData = useMemo<ForecastSeriesRow[]>(() => {
    if (!data) return [];
    const hist: ForecastSeriesRow[] = data.history.map((h) => ({
      date: h.date,
      actual_sales: h.actual_sales,
    }));
    const fut: ForecastSeriesRow[] = data.forecasts.map((f) => ({
      date: f.forecast_date,
      lightgbm_pred: f.lightgbm_pred,
      lightgbm_p95: f.lightgbm_p95,
      seasonal_naive_pred: f.seasonal_naive_pred,
    }));
    return [...hist, ...fut];
  }, [data]);

  const holdoutChartData = useMemo<ForecastSeriesRow[]>(() => {
    if (!data) return [];
    return data.holdout_comparison.map((h) => ({
      date: h.date,
      actual_sales: h.actual_sales,
      lightgbm_pred: h.lightgbm_pred,
      seasonal_naive_pred: h.seasonal_naive_pred,
    }));
  }, [data]);

  const pageSize = 10;
  const totalPages = data ? Math.ceil(data.forecasts.length / pageSize) : 1;
  const pageRows = data
    ? data.forecasts.slice(page * pageSize, (page + 1) * pageSize)
    : [];

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-xl font-bold text-slate-900">Demand Forecasting</h2>
          <p className="text-sm text-slate-500">
            Direct multi-horizon LightGBM (Tweedie) vs. Seasonal Naive 7-day baseline.
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-3">
          <select
            value={data?.item_id ?? itemId}
            onChange={(e) => setItemId(e.target.value)}
            className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm font-medium text-slate-800"
          >
            {(data?.available_items ?? []).map((sku) => (
              <option key={sku.item_id} value={sku.item_id}>
                {sku.item_id} ({sku.cat_id})
              </option>
            ))}
          </select>

          <div className="inline-flex rounded-lg border border-slate-200 bg-white p-1">
            {([7, 14, 28] as const).map((h) => (
              <button
                key={h}
                type="button"
                onClick={() => setHorizon(h)}
                className={`rounded-md px-3 py-1.5 text-xs font-semibold transition-colors ${
                  horizon === h
                    ? "bg-blue-600 text-white"
                    : "text-slate-600 hover:bg-slate-100"
                }`}
              >
                {h}d Horizon
              </button>
            ))}
          </div>
        </div>
      </div>

      {data && (
        <div className="flex items-start gap-2.5 rounded-xl border border-blue-200 bg-blue-50/70 px-4 py-3 text-xs text-blue-900">
          <Info className="mt-0.5 h-4 w-4 shrink-0 text-blue-600" />
          <div>
            <span className="font-semibold">Statistical Estimate Disclaimer: </span>
            {data.disclaimer} (SKU Validation RMSE: {data.sku_validation_rmse.toFixed(2)})
          </div>
        </div>
      )}

      {error && (
        <div className="rounded-xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-700">
          {error}
        </div>
      )}

      {loading && !data ? (
        <div className="p-8 text-sm text-slate-500">Loading SKU forecasts...</div>
      ) : (
        data && (
          <>
            <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
              <div className="mb-4 flex items-center justify-between">
                <div>
                  <h3 className="text-sm font-semibold text-slate-900">
                    Historical Sales + {horizon}-Day Forecast ({data.item_id})
                  </h3>
                  <p className="text-xs text-slate-500">
                    Last 60 days actuals followed by {horizon}-day LightGBM point forecast, P95 Upper Estimate (RMSE-based), and Seasonal Naive
                  </p>
                </div>
              </div>
              <ForecastChart data={combinedChartData} />
            </div>

            <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
              <div className="mb-4">
                <h3 className="text-sm font-semibold text-slate-900">
                  28-Day Holdout Actual vs. Predicted Comparison
                </h3>
                <p className="text-xs text-slate-500">
                  Out-of-sample chronological holdout performance for {data.item_id}
                </p>
              </div>
              <ForecastChart data={holdoutChartData} />
            </div>

            <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
              <div className="mb-3 flex items-center justify-between">
                <h3 className="text-sm font-semibold text-slate-900">
                  {horizon}-Day Forecast Schedule
                </h3>
                <div className="flex items-center gap-2 text-xs">
                  <button
                    type="button"
                    disabled={page === 0}
                    onClick={() => setPage((p) => Math.max(0, p - 1))}
                    className="rounded border border-slate-200 px-2.5 py-1 disabled:opacity-40"
                  >
                    Prev
                  </button>
                  <span className="text-slate-500">
                    Page {page + 1} / {Math.max(1, totalPages)}
                  </span>
                  <button
                    type="button"
                    disabled={page + 1 >= totalPages}
                    onClick={() => setPage((p) => p + 1)}
                    className="rounded border border-slate-200 px-2.5 py-1 disabled:opacity-40"
                  >
                    Next
                  </button>
                </div>
              </div>

              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs">
                  <thead>
                    <tr className="border-b border-slate-200 text-slate-500">
                      <th className="py-2 pr-4 font-medium">Forecast Date</th>
                      <th className="py-2 pr-4 text-right font-medium">
                        LightGBM Expected Units
                      </th>
                      <th className="py-2 pr-4 text-right font-medium">
                        P95 Upper Estimate (RMSE-based)
                      </th>
                      <th className="py-2 text-right font-medium">
                        Seasonal Naive Baseline
                      </th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {pageRows.map((row) => (
                      <tr key={row.forecast_date} className="hover:bg-slate-50">
                        <td className="py-2.5 pr-4 font-medium text-slate-800">
                          {row.forecast_date}
                        </td>
                        <td className="py-2.5 pr-4 text-right font-bold text-blue-700">
                          {row.lightgbm_pred.toFixed(2)}
                        </td>
                        <td className="py-2.5 pr-4 text-right text-slate-600">
                          {row.lightgbm_p95 !== null ? row.lightgbm_p95.toFixed(2) : "—"}
                        </td>
                        <td className="py-2.5 text-right text-amber-700">
                          {row.seasonal_naive_pred !== null
                            ? row.seasonal_naive_pred.toFixed(2)
                            : "—"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </>
        )
      )}
    </div>
  );
}
