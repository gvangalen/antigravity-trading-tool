import React, { ReactNode } from "react";

/**
 * Formatteert dagverandering in %
 *
 * Regels:
 * - null / undefined → "–"
 * - 0.00 → neutraal (geen groen/rood)
 * - > 0 → groen met "+"
 * - < 0 → rood
 */
export function formatChange(
  change: number | null | undefined
): ReactNode {
  if (change === null || change === undefined || Number.isNaN(change)) {
    return "–";
  }

  // Neutraal bij exact 0
  if (change === 0) {
    return (
      <span className="text-[var(--text-light)]">
        0.00%
      </span>
    );
  }

  const isPositive = change > 0;
  const color = isPositive ? "text-green-600" : "text-red-600";
  const sign = isPositive ? "+" : "";

  return (
    <span className={color}>
      {sign}{change.toFixed(2)}%
    </span>
  );
}

/**
 * Formatteert numerieke waarden (prijzen / aantallen)
 */
export function formatNumber(
  num: number | string | null,
  isPrice = false
): string {
  if (num === null || num === "N/A" || Number.isNaN(Number(num))) {
    return "–";
  }

  const value = Number(num);

  return isPrice
    ? `$${value.toFixed(2)}`
    : value.toLocaleString("nl-NL");
}
