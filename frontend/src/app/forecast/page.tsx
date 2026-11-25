"use client";

import React, { useEffect, useMemo, useState } from "react";
import { fetchForecast } from "@/lib/api";
import type { ForecastResponse } from "@/lib/types";
import {
  ForecastChart,
  type ForecastSeriesRow,
} from "@/components/charts/ForecastChart";

export default function ForecastPage() {
  const [itemId, setItemId] = useState<string>("");
  const [data, setData] = useState<ForecastResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    setLoading(true);
    fetchForecast(itemId || undefined)
      .then((res) => {
        if (active) {
          setData(res);
          if (!itemId) setItemId(res.item_id);
          setError(null);
        }
      })
      .catch((err) => {
        if (active) setError(err instanceof Error ? err.message : "Failed to load forecast");
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [itemId]);

  const combined30Plus7 = useMemo<ForecastSeriesRow[]>(() => {
    if (!data) return [];
    return [
      ...data.history_30d.map((h) => ({ date: h.date, actual_sales: h.actual_sales })),
      ...data.forecast_7d.map((f) => ({
        date: f.forecast_date,
        predicted_sales: f.predicted_sales,
      })),
    ];
  }, [data]);

  const holdout28 = useMemo<ForecastSeriesRow[]>(() => {
    if (!data) return [];
    return data.holdout_28d.map((h) => ({
      date: h.date,
      actual_sales: h.actual_sales,
      predicted_sales: h.predicted_sales,
    }));
  }, [data]);

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-xl font-bold text-slate-900">7-Day Demand Forecast</h2>
          <p className="text-sm text-slate-500">
            {data
              ? `Using ${data.best_model} · SKU Test RMSE: ${data.sku_rmse.toFixed(2)}`
              : "Select an SKU to view historical demand and next 7-day predictions."}
          </p>
        </div>

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
      </div>

      {error && (
        <div className="rounded-xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-700">
          {error}
        </div>
      )}

      {loading && !data ? (
        <div className="p-8 text-sm text-slate-500">Loading 7-day forecast...</div>
      ) : (
        data && (
          <>
            <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
              <h3 className="mb-1 text-sm font-semibold text-slate-900">
                Last 30 Days Actuals + Next 7-Day Forecast ({data.item_id})
              </h3>
              <p className="mb-4 text-xs text-slate-500">
                Statistical expected daily demand generated with 7-day-shifted features
              </p>
              <ForecastChart data={combined30Plus7} />
            </div>

            <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
              <h3 className="mb-1 text-sm font-semibold text-slate-900">
                28-Day Test Holdout: Actual vs. Predicted ({data.item_id})
              </h3>
              <p className="mb-4 text-xs text-slate-500">
                Chronological out-of-sample evaluation window
              </p>
              <ForecastChart data={holdout28} />
            </div>

            <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
              <h3 className="mb-3 text-sm font-semibold text-slate-900">
                7-Day Forecast Schedule
              </h3>
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs">
                  <thead>
                    <tr className="border-b border-slate-200 text-slate-500">
                      <th className="py-2 pr-4 font-medium">Forecast Date</th>
                      <th className="py-2 text-right font-medium">Predicted Units</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {data.forecast_7d.map((row) => (
                      <tr key={row.forecast_date} className="hover:bg-slate-50">
                        <td className="py-2.5 pr-4 font-medium text-slate-800">
                          {row.forecast_date}
                        </td>
                        <td className="py-2.5 text-right font-bold text-blue-700">
                          {row.predicted_sales.toFixed(2)}
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
