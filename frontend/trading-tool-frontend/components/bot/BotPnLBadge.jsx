"use client";

export default function BotPnLBadge({ pnlEur = 0, pnlPct = null }) {
  const isPositive = pnlEur > 0;
  const isNegative = pnlEur < 0;

  const colorClass = isPositive
    ? "icon-success"
    : isNegative
    ? "icon-danger"
    : "text-[var(--text-muted)]";

  return (
    <div className={`text-sm font-medium ${colorClass}`}>
      {pnlEur > 0 && "+"}
      €{pnlEur.toFixed(2)}

      {pnlPct !== null && (
        <span className="ml-1 text-xs">
          ({pnlPct > 0 ? "+" : ""}
          {pnlPct.toFixed(2)}%)
        </span>
      )}
    </div>
  );
}
