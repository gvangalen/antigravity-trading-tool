"use client";

import React from "react";
import { useMarketIntelligence } from "@/hooks/useMarketIntelligence";
import MarketDecisionCard from "@/components/bot/MarketDecisionCard";

export default function GlobalMarketDecisionCard({
  symbol = "BTC",
  snapshot = null,
}) {
  const fallbackSnapshot = useMarketIntelligence(symbol);
  const { data, loading } = snapshot || fallbackSnapshot;

  if (loading) {
    return (
      <div className="flex items-center gap-3 text-xs font-black text-secondary uppercase tracking-widest p-12 justify-center">
        <div className="w-4 h-4 rounded-full border-2 border-slate-200 border-t-[var(--primary)] animate-spin" />
        Syncing Global Market Telemetry...
      </div>
    );
  }

  return <MarketDecisionCard data={data} />;
}
