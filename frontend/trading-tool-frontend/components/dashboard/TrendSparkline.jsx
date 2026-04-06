"use client";

import React from "react";
import { useIndicatorHistory } from "@/hooks/useIndicatorHistory";
import Sparkline from "@/components/dashboard/Sparkline";

/**
 * 🕵️ TrendSparkline — Verbindt de Sparkline-component met de echte API-data.
 * Zorgt ervoor dat we per indicator een trend zien.
 */
export default function TrendSparkline({ indicatorName, score }) {
  const { history, loading } = useIndicatorHistory(indicatorName, 14);

  if (loading) {
    return <div className="w-[70px] h-5 bg-[var(--bg-soft)] rounded animate-pulse opacity-50 mx-auto" />;
  }

  if (!history || history.length < 2) {
    return <span className="text-[10px] text-[var(--text-light)] opacity-40 italic">Geen trend data</span>;
  }

  // Bepaal kleur op basis van de huidige score (of trend)
  const getColor = () => {
    if (score >= 70) return "#22c55e"; // Groen
    if (score <= 30) return "#ef4444"; // Rood
    return "#94a3b8"; // Grijs (Neutral)
  };

  return (
    <div className="flex items-center justify-center p-1">
      <Sparkline 
        data={history} 
        width={70} 
        height={20} 
        color={getColor()} 
      />
    </div>
  );
}
