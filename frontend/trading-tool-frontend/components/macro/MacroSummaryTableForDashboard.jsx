"use client";

import { Globe2 } from "lucide-react";
import SkeletonTable from "@/components/ui/SkeletonTable";
import TechnicalTerminalGrid from "@/components/technical/TechnicalTerminalGrid";

export default function MacroSummaryTableForDashboard({
  data = [],
  loading = false,
  error = "",
  onRetry = null,
}) {
  // ⏳ LOADING
  if (loading) {
    return <SkeletonTable rows={5} columns={5} />;
  }



  // ✅ Data defensief maken
  const safeData = Array.isArray(data) ? data : [];

  // 🔥 DEFINITIEVE NORMALISATIE (BELANGRIJK)
  const formatted = safeData.map((item) => ({
    indicator: item.indicator || item.name || "–", // ✅ DIT WAS DE FIX
    value: item.value ?? null,
    score: item.score ?? null,
    action: item.action ?? "–",
    interpretation: item.interpretation ?? "–",
    timestamp: item.timestamp,
  }));

  return (
    <TechnicalTerminalGrid
      title="Macro Indicatoren"
      icon={<Globe2 className="w-5 h-5 text-[var(--primary)]" />}
      data={formatted}
      error={error}
      onRetry={onRetry}
      onRemove={null} // dashboard = read-only
    />
  );
}
