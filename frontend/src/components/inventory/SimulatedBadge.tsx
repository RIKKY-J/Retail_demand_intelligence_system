"use client";

import React from "react";

interface SimulatedBadgeProps {
  label?: string;
}

export function SimulatedBadge({
  label = "Simulated Inventory Layer",
}: SimulatedBadgeProps) {
  return (
    <span
      title="M5 dataset does not contain physical stock levels; stock-on-hand, lead times, and purchase orders are simulated in SQLite."
      className="inline-flex items-center gap-1.5 rounded-full border border-amber-200 bg-amber-50 px-2.5 py-0.5 text-xs font-medium text-amber-800"
    >
      <span className="h-1.5 w-1.5 rounded-full bg-amber-500" />
      {label}
    </span>
  );
}
