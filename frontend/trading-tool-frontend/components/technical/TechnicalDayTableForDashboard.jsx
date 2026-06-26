"use client";

import SkeletonTable from "@/components/ui/SkeletonTable";
import TechnicalTerminalGrid from "@/components/technical/TechnicalTerminalGrid";
import { TrendingUp } from "lucide-react";
import { useTranslation } from "@/app/providers/I18nProvider";

export default function TechnicalDayTableForDashboard({
  data = [],
  loading = false,
  error = "",
  onRetry = null,
}) {
  const { t } = useTranslation();
  // ⏳ LOADING
  if (loading) {
    return <SkeletonTable rows={5} columns={5} />;
  }



  // ✅ data komt AL genormaliseerd uit useTechnicalData
  const safeData = Array.isArray(data) ? data : [];

  const formatted = safeData.map((item) => ({
    name: item.name ?? "–",
    value: item.value ?? null,
    score: item.score ?? null,
    action: item.action ?? "–",
    interpretation: item.interpretation ?? "–",

    // 🔥 DIT WAS DE FIX
    timestamp: item.timestamp ?? null,
  }));

  return (
    <TechnicalTerminalGrid
      title={t.dashboard.tabs.technical}
      icon={<TrendingUp className="w-5 h-5 text-[var(--primary)]" />}
      data={formatted}
      error={error}
      onRetry={onRetry}
      onRemove={null} // dashboard = read-only
    />
  );
}
