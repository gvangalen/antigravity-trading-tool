"use client";

import CardWrapper from "@/components/ui/CardWrapper";
import { CheckCircle2, Layers } from "lucide-react";
import { useDailySetupScores } from "@/hooks/useDailySetupScores";
import { ScoreCardSkeleton } from "@/components/dashboard/DashboardSkeleton";

/* -------------------------------------------------------
   Kleine helper voor score visualisatie
------------------------------------------------------- */
function ScoreBar({ score }) {
  const pct = Math.max(0, Math.min(100, Number(score) || 0));

  let color = "bg-yellow-400";
  if (pct >= 70) color = "bg-green-500";
  else if (pct <= 40) color = "bg-red-500";

  return (
    <div className="w-full h-2 bg-gray-200 rounded overflow-hidden">
      <div
        className={`h-full ${color}`}
        style={{ width: `${pct}%` }}
      />
    </div>
  );
}

/* =======================================================
   Setup Match Card
======================================================= */
export default function SetupMatchCard() {
  const { dailySetups, loading } = useDailySetupScores();

  /* -------------------------------
     Loading
  ------------------------------- */
  if (loading) {
    return <ScoreCardSkeleton />;
  }

  /* -------------------------------
     Geen data
  ------------------------------- */
  if (!dailySetups || dailySetups.length === 0) {
    return (
      <CardWrapper>
        <div className="space-y-2 text-sm text-[var(--text-light)]">
          <p>Er zijn nog geen setup-scores voor vandaag.</p>
          <p className="text-xs opacity-80">
            Dat kan normaal zijn als de marktcontext net is ververst. Vraag Finn om een compact setup-overzicht totdat de nieuwe scores klaarstaan.
          </p>
        </div>
      </CardWrapper>
    );
  }

  /* -------------------------------
     Sorteren & selecteren
  ------------------------------- */
  const sorted = [...dailySetups].sort(
    (a, b) => (b.score || 0) - (a.score || 0)
  );

  const best = sorted.find((s) => s.is_best) || sorted[0];
  const topSetups = sorted.slice(0, 3);

  return (
    <div className="bg-card rounded-[2.5rem] border border-[var(--color-border)] p-6 sm:p-10 shadow-[0_8px_30px_rgb(0,0,0,0.04)] relative overflow-hidden group transition-all hover:shadow-[0_20px_50px_rgba(0,0,0,0.08)] h-full flex flex-col">
      <div className="absolute inset-0 opacity-[0.03] pointer-events-none bg-[radial-gradient(#000_1px,transparent_1px)] [background-size:24px_24px]" />
      <div className="absolute top-0 right-0 w-40 h-40 bg-blue-500/10 blur-[80px] rounded-full -mr-20 -mt-20 group-hover:bg-blue-500/20 transition-all duration-1000" />

      {/* 🔮 HEADER */}
      <div className="flex items-center justify-between mb-8 relative z-10">
         <div className="flex items-center gap-4">
            <div className="w-10 h-10 rounded-2xl bg-blue-500/10 border border-blue-500/20 flex items-center justify-center shadow-inner">
               <Layers size={18} className="text-blue-500 sm:size-5" strokeWidth={1.5} />
            </div>
            <div>
               <div className="text-[10px] sm:text-[11px] font-bold text-secondary/60 uppercase tracking-[0.2em] mb-0.5">Optimization</div>
               <div className="text-lg sm:text-xl font-black text-foreground tracking-tight uppercase leading-none">Setup Matcher</div>
            </div>
         </div>
      </div>

      {/* 🚀 BEST MATCH HERO */}
      <div className="mb-10 relative z-10 bg-slate-50 dark:bg-slate-900/40 rounded-3xl p-4 sm:p-6 border border-[var(--color-border-subtle)] shadow-sm">
         <div className="flex items-center gap-3 mb-4">
            <div className="px-3 py-1 rounded-full bg-green-500/10 border border-green-500/20 text-[8px] sm:text-[9px] font-black text-green-500 uppercase tracking-widest flex items-center gap-2">
               <div className="w-1.5 h-1.5 rounded-full bg-green-500 animate-pulse" />
               Elite Selection
            </div>
         </div>

         <div className="space-y-4">
            <div>
               <div className="text-[9px] sm:text-[10px] font-black text-secondary/40 uppercase tracking-[0.2em] mb-1">Active Selection</div>
               <div className="text-xl sm:text-2xl font-black text-foreground tracking-tighter uppercase leading-none">
                  {best.name}
               </div>
               <div className="flex items-center gap-2 mt-2">
                  <span className="px-2 py-0.5 rounded bg-[var(--color-border-subtle)] text-[9px] sm:text-[10px] font-bold text-secondary/60 uppercase tracking-wider">{best.symbol}</span>
                  <span className="px-2 py-0.5 rounded bg-[var(--color-border-subtle)] text-[9px] sm:text-[10px] font-bold text-secondary/60 uppercase tracking-wider">{best.timeframe}</span>
               </div>
            </div>

            <div className="pt-2">
               <div className="flex justify-between items-end mb-2">
                  <span className="text-[10px] font-black text-secondary/40 uppercase tracking-widest">Confidence Score</span>
                  <span className="text-sm font-black text-foreground">{best.score}%</span>
               </div>
               <div className="h-3 w-full bg-slate-200 dark:bg-slate-800 rounded-full overflow-hidden p-0.5 border border-[var(--color-border-subtle)] shadow-inner">
                  <div 
                     className="h-full rounded-full bg-gradient-to-r from-blue-500 to-indigo-500 transition-all duration-1000 relative"
                     style={{ width: `${best.score}%` }}
                  >
                     <div className="absolute inset-0 bg-gradient-to-r from-transparent via-white/20 to-transparent animate-shimmer" />
                  </div>
               </div>
            </div>
         </div>
      </div>

      {/* 📊 COMPETITORS */}
      <div className="flex-grow relative z-10">
         <div className="text-[10px] font-black text-secondary/40 uppercase tracking-[0.2em] mb-6">Comparison Matrix</div>
         <div className="space-y-6">
            {topSetups.map((s, idx) => (
               <div key={s.id} className="group/item">
                  <div className="flex justify-between items-center mb-2">
                     <span className={`text-[11px] font-black uppercase tracking-wider ${s.id === best.id ? 'text-blue-500' : 'text-foreground/70'}`}>
                        {s.name}
                     </span>
                     <span className="text-[11px] font-black tabular-nums text-foreground/40">{s.score}%</span>
                  </div>
                  <div className="h-1.5 w-full bg-slate-100 dark:bg-slate-800/50 rounded-full overflow-hidden">
                     <div 
                        className={`h-full rounded-full transition-all duration-1000 ${s.score >= 70 ? 'bg-green-500/60' : s.score >= 50 ? 'bg-blue-500/60' : 'bg-amber-500/60'}`}
                        style={{ width: `${s.score}%` }}
                     />
                  </div>
               </div>
            ))}
         </div>
      </div>

      {/* 📝 FOOTER NOTE */}
      <div className="mt-10 relative z-10 pt-6 border-t border-[var(--color-border-subtle)]">
         <p className="text-[9px] text-secondary/40 leading-relaxed font-bold uppercase tracking-wider italic">
            Elite matching determined via multi-vector cross-correlation across macro, technical, and market indicators.
         </p>
      </div>
    </div>
  );
}
