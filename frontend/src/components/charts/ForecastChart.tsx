"use client";

import React from "react";
import {
  Area,
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

export interface ForecastSeriesRow {
  date: string;
  actual_sales?: number | null;
  lightgbm_pred?: number | null;
  lightgbm_p95?: number | null;
  seasonal_naive_pred?: number | null;
}

export function ForecastChart({ data }: { data: ForecastSeriesRow[] }) {
  return (
    <div className="h-80 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart data={data} margin={{ top: 10, right: 20, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
          <XAxis
            dataKey="date"
            tick={{ fontSize: 11, fill: "#64748b" }}
            minTickGap={24}
          />
          <YAxis tick={{ fontSize: 11, fill: "#64748b" }} />
          <Tooltip
            contentStyle={{
              borderRadius: "8px",
              border: "1px solid #e2e8f0",
              fontSize: "12px",
            }}
          />
          <Legend wrapperStyle={{ fontSize: "12px" }} />
          <Area
            type="monotone"
            dataKey="lightgbm_p95"
            name="P95 Upper Estimate (RMSE-based)"
            fill="#dbeafe"
            stroke="#93c5fd"
            fillOpacity={0.45}
            connectNulls={false}
          />
          <Line
            type="monotone"
            dataKey="actual_sales"
            name="Actual Sales"
            stroke="#0f172a"
            strokeWidth={2}
            dot={false}
            connectNulls={false}
          />
          <Line
            type="monotone"
            dataKey="lightgbm_pred"
            name="LightGBM Forecast"
            stroke="#2563eb"
            strokeWidth={2.5}
            dot={false}
            connectNulls={false}
          />
          <Line
            type="monotone"
            dataKey="seasonal_naive_pred"
            name="Seasonal Naive"
            stroke="#f59e0b"
            strokeWidth={1.75}
            strokeDasharray="4 4"
            dot={false}
            connectNulls={false}
          />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}
