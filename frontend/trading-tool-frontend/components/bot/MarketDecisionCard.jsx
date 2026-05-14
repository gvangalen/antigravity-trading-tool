"use client";

import {
  Activity,
} from "lucide-react";

import MarketConditionsPanel from "@/components/bot/MarketConditionsPanel";
import { useIntelligenceSemantics } from "@/hooks/useIntelligenceSemantics";

export default function MarketDecisionCard({ data }) {
  if (!data) return null;

  /* ======================================
     API DATA (DE ENIGE SOURCE)
  ====================================== */

  const metrics = data?.metrics || {};
  const trend = data?.trend || {};

  const pressure = Number(metrics?.market_pressure ?? 50);
  const transitionRisk = Number(metrics?.transition_risk ?? 50);
  const health = Number(metrics?.setup_quality ?? 50);
  const volatility = Number(metrics?.volatility ?? 50);
  const trendStrength = Number(metrics?.trend_strength ?? 50);

  // position size bestaat niet in API → default
  const positionSize = 0.5;

  /* ======================================
     MARKET STRUCTURE (CENTRAL SEMANTICS)
  ====================================== */
  const { getMacroSemantics, getMarketSemantics } = useIntelligenceSemantics();
  const macroData = getMacroSemantics(data?.scores?.macro_score ?? 65);
  const marketData = getMarketSemantics(data?.scores?.market_score ?? 60);

  const phase = data?.cycle || "expansion";

  /* ======================================
     TRENDS
  ====================================== */

  const trendShort = trend?.short || "trading range";
  const trendMid = trend?.mid || "trading range";
  const trendLong = trend?.long || "trading range";

  const formatTrend = (t) => {
    const v = String(t).toLowerCase();

    if (v === "bullish") return "Bullish";
    if (v === "bearish") return "Bearish";

    return "Trading range";
  };

  /* ======================================
     MARKET CYCLE
  ====================================== */

  const phases = [
    "Accumulation",
    "Expansion",
    "Distribution",
    "Correction",
  ];

  const phaseIndex =
    {
      accumulation: 0,
      expansion: 1,
      distribution: 2,
      correction: 3,
    }[phase?.toLowerCase()] ?? 1;

  /* ======================================
     DEBUG (BELANGRIJK)
  ====================================== */

  console.log("MARKET API DATA", data);

  /* ======================================
     RENDER
  ====================================== */

  return (
    <div className="space-y-8">
      {/* 🚀 MARKET INTELLIGENCE HEADER */}
      <div className="flex items-center justify-between pb-4 border-b border-slate-100">
        <div className="flex items-center gap-3">
          <div className="p-2 rounded-lg bg-blue-50 dark:bg-blue-600/10 text-blue-600">
            <Activity size={18} />
          </div>
          <div>
            <div className="text-[10px] font-black text-muted uppercase tracking-widest mb-0.5">Terminal Intelligence</div>
            <div className="text-sm font-bold text-foreground tracking-tight">Market Context & Global Analysis</div>
          </div>
        </div>

        <div className={`flex items-center gap-2 px-3 py-1.5 rounded-xl border shadow-sm ${macroData.badgeClass}`}>
          <span className="text-[9px] font-black uppercase tracking-tighter opacity-70">Risk State:</span>
          <span className="text-[10px] font-black uppercase tracking-widest">
            {macroData.riskState}
          </span>
        </div>
      </div>

      {/* 🧩 MARKET CYCLE PROGRESSOR */}
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <div className="text-[10px] font-black text-secondary uppercase tracking-[0.2em]">Structural Cycle Phase</div>
          <div className="text-[10px] font-black text-[var(--primary)] uppercase tracking-widest bg-blue-50 px-2 py-0.5 rounded-md border border-blue-100">
             Active: {macroData.regime}
          </div>
        </div>

        <div className="grid grid-cols-4 gap-3 h-3 items-end pb-8">
          {phases.map((p, i) => {
            const isActive = i === phaseIndex;
            const isCompleted = i < phaseIndex;
            
            return (
              <div key={p} className="relative group flex flex-col items-center">
                <div 
                  className={`w-full h-2 rounded-full transition-all duration-700 ${
                    isActive 
                      ? "bg-blue-600 shadow-[0_0_12px_rgba(37,99,235,0.4)] scale-y-125" 
                      : isCompleted 
                        ? "bg-slate-300" 
                        : "bg-[var(--color-border-subtle)]"
                  }`} 
                />
                <div className={`mt-3 text-[9px] font-black uppercase tracking-[0.15em] transition-colors whitespace-nowrap ${
                  isActive ? "text-blue-600" : isCompleted ? "text-muted" : "text-slate-300"
                }`}>
                  {p}
                </div>
              </div>
            );
          })}
        </div>

        <div className="text-[11px] text-muted italic pt-1">
          {macroData.explanation}
        </div>
      </div>

      {/* 📊 TREND TELEMETRY */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 pt-4">
        {[
          { label: "Short Term", value: trendShort },
          { label: "Mid Term", value: trendMid },
          { label: "Long Term", value: trendLong }
        ].map((t) => {
          const val = String(t.value || "trading range").toLowerCase();
          const colorClass = val === 'bullish' ? 'text-green-600' : val === 'bearish' ? 'text-red-600' : 'text-slate-600';
          const dotClass = val === 'bullish' ? 'bg-green-500' : val === 'bearish' ? 'bg-red-500' : 'bg-slate-400';

          return (
            <div key={t.label} className="p-4 rounded-2xl bg-[var(--color-border-subtle)] border border-slate-100 flex flex-col justify-center">
              <div className="text-[9px] font-black text-secondary uppercase tracking-widest mb-1.5 opacity-60">
                {t.label} Trend
              </div>
              <div className={`text-xs font-black uppercase tracking-tight flex items-center gap-2 ${colorClass}`}>
                <div className={`w-1.5 h-1.5 rounded-full ${dotClass}`} />
                {t.value}
              </div>
            </div>
          );
        })}
      </div>

      {/* 🛡️ SENSOR READOUTS */}
      <div className="bg-[var(--color-border-subtle)] dark:bg-slate-900/50 rounded-2xl border border-[var(--color-border)] p-6 shadow-inner">
        <MarketConditionsPanel
          health={health}
          transitionRisk={transitionRisk}
          pressure={pressure}
          volatility={volatility}
          trendStrength={trendStrength}
          multiplier={positionSize}
        />
      </div>
    </div>
  );
}
