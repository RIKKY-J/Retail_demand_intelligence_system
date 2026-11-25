"use client";

import React from "react";

interface StatusBadgeProps {
  status: string;
}

const STYLE_MAP: Record<string, string> = {
  Healthy: "border-emerald-200 bg-emerald-50 text-emerald-700",
  "Reorder required": "border-amber-200 bg-amber-50 text-amber-800",
  "Potential stockout": "border-rose-200 bg-rose-50 text-rose-700",
  "Possible overstock": "border-sky-200 bg-sky-50 text-sky-700",
};

export function StatusBadge({ status }: StatusBadgeProps) {
  const cls = STYLE_MAP[status] ?? "border-slate-200 bg-slate-50 text-slate-700";
  return (
    <span
      className={`inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-semibold ${cls}`}
    >
      {status}
    </span>
  );
}
