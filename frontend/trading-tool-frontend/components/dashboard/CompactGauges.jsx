"use client";

import { useScoresData } from "@/hooks/useScoresData";
import { Globe2, LineChart, DollarSign, Settings2 } from "lucide-react";
import { useTranslation } from "@/app/providers/I18nProvider";
import { GaugeSkeleton } from "./DashboardSkeleton";

/**
 * 📏 CompactGauges — Minimalist Status Bar (V2.1)
 * Replaces large Gauge cards with a slim horizontal strip.
 */
export default function CompactGauges() {
  const { t } = useTranslation();
  const { macro, technical, market, setup, loading } = useScoresData();

  const items = [
    { title: t.dashboard.gauges.macro, icon: <Globe2 size={14} />, score: macro.score },
    { title: t.dashboard.gauges.technical, icon: <LineChart size={14} />, score: technical.score },
    { title: t.dashboard.gauges.market, icon: <DollarSign size={14} />, score: market.score },
    { title: t.dashboard.gauges.setup, icon: <Settings2 size={14} />, score: setup.score },
  ];

  if (loading) {
     return (
       <div className="grid grid-cols-1 xs:grid-cols-2 md:grid-cols-4 gap-4 w-full">
         {[1, 2, 3, 4].map(i => (
           <GaugeSkeleton key={i} />
         ))}
       </div>
     );
  }

  return (
    <div className="grid grid-cols-1 xs:grid-cols-2 md:grid-cols-4 gap-4 w-full">
      {items.map((item, idx) => {
        const score = Math.round(item.score || 0);
        
        // Color logic
        let colorClass = "text-secondary dark:text-slate-500";
        let bgClass = "bg-[var(--color-border-subtle)] dark:bg-slate-900";
        let borderClass = "border-slate-100 dark:border-slate-800";

        if (score >= 75) {
          colorClass = "text-emerald-600 dark:text-emerald-400";
          bgClass = "bg-emerald-50 dark:bg-emerald-950/30";
          borderClass = "border-emerald-100 dark:border-emerald-900/50";
        } else if (score >= 50) {
          colorClass = "text-blue-600 dark:text-blue-400";
          bgClass = "bg-blue-50 dark:bg-blue-950/30";
          borderClass = "border-blue-100 dark:border-blue-900/50";
        } else if (score < 40) {
          colorClass = "text-rose-500 dark:text-rose-400";
          bgClass = "bg-rose-50 dark:bg-rose-950/30";
          borderClass = "border-rose-100 dark:border-rose-900/50";
        }

        return (
          <div 
            key={idx} 
            className={`
              flex items-center justify-between px-3 sm:px-4 py-2.5 
              rounded-xl border ${borderClass} ${bgClass}
              shadow-sm transition-all hover:shadow-md dark:hover:border-blue-500/30
            `}
          >
            <div className="flex items-center gap-2 sm:gap-2.5 min-w-0">
              <div className={`shrink-0 p-1.5 rounded-lg bg-card dark:bg-slate-800 shadow-sm ${colorClass} border border-slate-50 dark:border-slate-700`}>
                {item.icon}
              </div>
              <span className="text-[10px] sm:text-[11px] font-black uppercase tracking-wider text-secondary dark:text-slate-500 truncate">
                {item.title}
              </span>
            </div>
            
            <div className="flex items-center gap-1.5 shrink-0 ml-2">
              <span className={`text-xs sm:text-sm font-black font-mono ${colorClass}`}>
                {score}%
              </span>
              <div className="w-1 h-1 sm:w-1.5 sm:h-1.5 rounded-full bg-current opacity-60" />
            </div>
          </div>
        );
      })}
    </div>
  );
}
