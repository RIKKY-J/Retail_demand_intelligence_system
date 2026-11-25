"use client";

import React from "react";

interface KpiCardProps {
  title: string;
  value: string | number;
  subtitle?: string;
  accent?: "default" | "emerald" | "amber" | "rose" | "blue";
  icon?: React.ReactNode;
}

const ACCENT_RING: Record<NonNullable<KpiCardProps["accent"]>, string> = {
  default: "border-slate-200",
  emerald: "border-emerald-200 bg-emerald-50/30",
  amber: "border-amber-200 bg-amber-50/30",
  rose: "border-rose-200 bg-rose-50/30",
  blue: "border-blue-200 bg-blue-50/30",
};

export function KpiCard({
  title,
  value,
  subtitle,
  accent = "default",
  icon,
}: KpiCardProps) {
  return (
    <div
      className={`rounded-xl border bg-white p-4 shadow-sm transition-shadow hover:shadow ${ACCENT_RING[accent]}`}
    >
      <div className="flex items-center justify-between">
        <span className="text-xs font-medium uppercase tracking-wide text-slate-500">
          {title}
        </span>
        {icon && <span className="text-slate-400">{icon}</span>}
      </div>
      <div className="mt-2 text-2xl font-bold tracking-tight text-slate-900">
        {value}
      </div>
      {subtitle && <p className="mt-1 text-xs text-slate-500">{subtitle}</p>}
    </div>
  );
}
