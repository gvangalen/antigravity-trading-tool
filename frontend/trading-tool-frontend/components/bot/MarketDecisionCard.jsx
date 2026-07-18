"use client";

import {
  Activity,
  Sparkles
} from "lucide-react";

import MarketConditionsPanel from "@/components/bot/MarketConditionsPanel";
import { useIntelligenceSemantics } from "@/hooks/useIntelligenceSemantics";
import { useTranslation } from "@/app/providers/I18nProvider";

export default function MarketDecisionCard({ data, symbol = "BTC", compact = false }) {
  const { t } = useTranslation();
  if (!data) return null;
  const copy = t?.ui?.marketDecision || {};

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
  const macroData = getMacroSemantics(data?.debug?.scores?.macro_score ?? data?.scores?.macro_score ?? 65);
  const marketData = getMarketSemantics(data?.debug?.scores?.market_score ?? data?.scores?.market_score ?? 60);

  const phase = data?.cycle || "expansion";

  /* ======================================
     TRENDS
  ====================================== */

  const trendShort = trend?.short || "trading range";
  const trendMid = trend?.mid || "trading range";
  const trendLong = trend?.long || "trading range";

  const formatTrend = (trendValue) => {
    const v = String(trendValue).toLowerCase();
    const trendLabels = copy.trendLabels || {};

    if (v === "bullish") return trendLabels.bullish;
    if (v === "bearish") return trendLabels.bearish;
    if (v === "trading_range" || v === "trading range" || v === "ranging") return trendLabels.sideways;
    return trendLabels.sideways;
  };

  /* ======================================
     MARKET CYCLE
  ====================================== */

  const phaseCopy = copy.phases || {};
  const phases = [
    phaseCopy.accumulation,
    phaseCopy.expansion,
    phaseCopy.distribution,
    phaseCopy.correction,
  ];

  const phaseIndex =
    {
      accumulation: 0,
      expansion: 1,
      distribution: 2,
      correction: 3,
    }[phase?.toLowerCase()] ?? 1;

  /* ======================================
     RENDER
  ====================================== */

  return (
    <div className={compact ? "space-y-4" : "space-y-8"}>
      <div className={`flex items-center justify-between border-b border-slate-100 dark:border-slate-800 ${compact ? "pb-3" : "pb-4"}`}>
        <div className="flex items-center gap-3">
          <div className={`${compact ? "p-1.5 rounded-md" : "p-2 rounded-lg"} bg-blue-50 dark:bg-blue-600/10 text-blue-600`}>
            <Activity size={compact ? 16 : 18} />
          </div>
          <div>
            <div className="text-[10px] font-black text-muted uppercase tracking-widest mb-0.5">{copy.title}</div>
            <div className={`${compact ? "text-[13px]" : "text-sm"} font-bold text-foreground tracking-tight`}>{copy.subtitle}</div>
          </div>
        </div>

        <div className={`flex items-center gap-2 border shadow-sm ${compact ? "px-2.5 py-1 rounded-lg" : "px-3 py-1.5 rounded-xl"} ${macroData.badgeClass}`}>
          <span className="text-[9px] font-black uppercase tracking-tighter opacity-70">{copy.riskStatus}</span>
          <span className="text-[10px] font-black uppercase tracking-widest">
            {macroData.riskState}
          </span>
        </div>
      </div>

      <div className={`group/cycle transition-all ${compact ? "space-y-2 p-1.5" : "space-y-4 p-3"} rounded-2xl`}>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="text-[10px] font-black text-secondary uppercase tracking-[0.2em]">{copy.structuralPhase}</div>
            <button 
              onClick={(e) => {
                e.stopPropagation();
                if (typeof window !== "undefined") {
                  window.dispatchEvent(new CustomEvent('finn-action-trigger', {
                    detail: { metric: 'structural_cycle', symbol, timeframe: '1W' }
                  }));
                }
              }}
              className={`opacity-0 group-hover/cycle:opacity-100 flex items-center gap-1 bg-blue-50 dark:bg-blue-900/40 text-[9px] font-black uppercase tracking-wider text-blue-600 dark:text-blue-400 border border-blue-200 dark:border-blue-800 transition-all hover:scale-105 active:scale-95 shadow-sm ${compact ? "px-1.5 py-0.5 rounded-md" : "px-2 py-0.5 rounded-lg"}`}
            >
              <Sparkles size={10} /> {copy.askFinn}
            </button>
          </div>
          <div className={`text-[10px] font-black text-[var(--primary)] uppercase tracking-widest bg-blue-50 dark:bg-blue-900/30 border border-blue-100 dark:border-blue-800 ${compact ? "px-2 py-0.5 rounded-md" : "px-2 py-0.5 rounded-md"}`}>
             {copy.active}: {macroData.regime}
          </div>
        </div>

        <div className={`grid grid-cols-4 items-end ${compact ? "gap-2 h-2 pb-4" : "gap-3 h-3 pb-8"}`}>
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
                        ? "bg-slate-300 dark:bg-slate-700" 
                        : "bg-[var(--color-border-subtle)] dark:bg-slate-800"
                  }`} 
                />
                <div className={`mt-2 text-[8px] font-black uppercase tracking-[0.12em] transition-colors whitespace-nowrap ${
                  isActive ? "text-blue-600" : isCompleted ? "text-muted" : "text-slate-300 dark:text-slate-600"
                }`}>
                  {p}
                </div>
              </div>
            );
          })}
        </div>

        <div className={`${compact ? "text-[10px]" : "text-[11px]"} text-muted italic pt-0.5`}>
          {macroData.explanation}
        </div>
      </div>

      <div className={`grid grid-cols-1 md:grid-cols-3 ${compact ? "gap-2 pt-1" : "gap-4 pt-4"}`}>
        {[
          { label: copy.shortTerm, value: trendShort },
          { label: copy.mediumTerm, value: trendMid },
          { label: copy.longTerm, value: trendLong }
        ].map((t) => {
          const val = String(t.value || "trading range").toLowerCase();
          const colorClass = val === 'bullish' ? 'text-green-600' : val === 'bearish' ? 'text-red-600' : 'text-slate-600';
          const dotClass = val === 'bullish' ? 'bg-green-500' : val === 'bearish' ? 'bg-red-500' : 'bg-slate-400';

          return (
            <div key={t.label} className={`${compact ? "p-2.5 rounded-lg" : "p-4 rounded-2xl"} bg-[var(--color-border-subtle)] dark:bg-slate-900/40 border border-slate-100 dark:border-slate-800 flex flex-col justify-center`}>
              <div className="text-[8px] font-black text-secondary uppercase tracking-widest mb-1 opacity-60">
                {t.label}
              </div>
              <div className={`text-[11px] font-black uppercase tracking-tight flex items-center gap-2 ${colorClass}`}>
                <div className={`w-1.5 h-1.5 rounded-full ${dotClass}`} />
                {formatTrend(t.value)}
              </div>
            </div>
          );
        })}
      </div>

      <div className={`bg-[var(--color-border-subtle)] dark:bg-slate-900/50 border border-[var(--color-border)] shadow-inner ${compact ? "rounded-xl p-4" : "rounded-2xl p-6"}`}>
        <MarketConditionsPanel
          health={health}
          transitionRisk={transitionRisk}
          pressure={pressure}
          volatility={volatility}
          trendStrength={trendStrength}
          multiplier={positionSize}
          symbol={symbol}
          compact={compact}
          hideMetrics={compact ? ["setup_quality", "position_size"] : []}
        />
      </div>
    </div>
  );
}
