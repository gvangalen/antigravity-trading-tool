"use client";

export default function BotBudgetBar({
  total = 0,
  spent = 0,
  label = "Budget",
}) {
  if (total <= 0) {
    return (
      <div className="text-xs text-[var(--text-muted)]">
        Geen budget ingesteld
      </div>
    );
  }

  const pct = total > 0 ? Math.min((spent / total) * 100, 100) : 0;

  const remaining = Math.max(total - spent, 0);

  let barClass = "bg-green-500";

  if (pct > 90) barClass = "bg-red-500";
  else if (pct > 70) barClass = "bg-yellow-400";

  return (
    <div className="space-y-2">

      {/* HEADER */}
      <div className="flex justify-between text-xs">
        <span className="text-[var(--text-muted)]">{label}</span>
        <span>
          €{spent.toFixed(0)} / €{total.toFixed(0)}
        </span>
      </div>

      {/* BAR */}
      <div className="h-2 rounded-[var(--radius-xs)] bg-[var(--surface-3)] overflow-hidden">
        <div
          className={`h-full ${barClass} transition-all duration-500`}
          style={{ width: `${pct}%` }}
        />
      </div>

      {/* AVAILABLE */}
      <div className="flex justify-between text-xs text-[var(--text-muted)]">
        <span>Beschikbaar</span>
        <span>€{remaining.toFixed(0)}</span>
      </div>

    </div>
  );
}
