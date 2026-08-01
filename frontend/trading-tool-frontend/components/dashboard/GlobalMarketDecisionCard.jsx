"use client";

import React from "react";
import { useMarketIntelligence } from "@/hooks/useMarketIntelligence";
import MarketDecisionCard from "@/components/bot/MarketDecisionCard";
import { useTranslation } from "@/app/providers/I18nProvider";

export default function GlobalMarketDecisionCard({
  symbol = "BTC",
  snapshot = null,
  compact = false,
  fallbackMessage = null,
}) {
  const { t } = useTranslation();
  const fallbackSnapshot = useMarketIntelligence(symbol, { enabled: !snapshot });
  const { data, loading } = snapshot || fallbackSnapshot;

  if (loading) {
    return (
      <div className="flex items-center gap-3 text-xs font-black text-secondary uppercase tracking-widest p-12 justify-center">
        <div className="w-4 h-4 rounded-full border-2 border-slate-200 border-t-[var(--primary)] animate-spin" />
        {t.dashboard.loadingMarketContext}
      </div>
    );
  }

  if (
    data?.available === false
    || data?.data_status === "insufficient_data"
    || data?.data_status === "fallback"
  ) {
    return (
      <div className="rounded-xl border border-slate-200 bg-slate-50 px-4 py-5 text-sm font-semibold text-slate-500">
        {fallbackMessage || t?.common?.insufficientData || "Onvoldoende data"}
      </div>
    );
  }

  return <MarketDecisionCard data={data} symbol={symbol} compact={compact} />;
}
