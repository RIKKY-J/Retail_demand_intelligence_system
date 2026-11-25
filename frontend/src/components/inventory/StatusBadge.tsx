"use client";

import React from "react";

export function StatusBadge({ status }: { status: string }) {
  const styles: Record<string, string> = {
    "Low Stock (Reorder)": "border-rose-200 bg-rose-50 text-rose-700",
    Healthy: "border-emerald-200 bg-emerald-50 text-emerald-700",
    Overstock: "border-sky-200 bg-sky-50 text-sky-700",
  };
  const cls = styles[status] ?? "border-slate-200 bg-slate-50 text-slate-700";
  return (
    <span
      className={`inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-semibold ${cls}`}
    >
      {status}
    </span>
  );
}
