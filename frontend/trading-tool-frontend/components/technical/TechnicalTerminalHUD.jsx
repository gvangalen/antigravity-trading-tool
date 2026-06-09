import React from "react";
import { Target, Activity } from "lucide-react";
import { HUDSkeleton } from "@/components/dashboard/DashboardSkeleton";

/**
 * 🛰️ TechnicalTerminalHUD — PRO V2
 * Visualizes the aggregate technical data from useScoresData().
 */
export default function TechnicalTerminalHUD({ score, bias, trend, risk, loading = false }) {
  if (loading) {
    return <HUDSkeleton />;
  }
  
  const scoreNum = Number(score ?? 0);
  
  /* ---------------- COLORS & LABELS ---------------- */
  const getBiasConfig = (s) => {
    if (s >= 80) return { label: "EXTREME BULLISH", color: "text-green-500", bg: "bg-green-500", dot: "bg-green-500", border: "border-green-200" };
    if (s >= 60) return { label: "BULLISH", color: "text-blue-500", bg: "bg-blue-500", dot: "bg-blue-500", border: "border-blue-200" };
    if (s >= 40) return { label: "NEUTRAL", color: "text-secondary", bg: "bg-slate-400", dot: "bg-slate-400", border: "border-slate-200" };
    if (s >= 20) return { label: "BEARISH", color: "text-red-400", bg: "bg-red-400", dot: "bg-red-400", border: "border-red-200" };
    return { label: "EXTREME BEARISH", color: "text-red-600", bg: "bg-red-600", dot: "bg-red-600", border: "border-red-300" };
  };

  const config = getBiasConfig(scoreNum);

  return (
    <div className="w-full grid grid-cols-1 lg:grid-cols-3 gap-6">
      
      {/* 🔮 MODULE 1: TECHNICAL CONTEXT */}
      <div className="lg:col-span-2 bg-card rounded-[2.5rem] border border-[var(--color-border)] p-6 sm:p-10 shadow-[0_8px_30px_rgb(0,0,0,0.04)] flex flex-col justify-between relative overflow-hidden group transition-all hover:shadow-[0_20px_50px_rgba(0,0,0,0.08)]">
         <div className="absolute inset-0 opacity-[0.03] pointer-events-none bg-[radial-gradient(#000_1px,transparent_1px)] [background-size:24px_24px]" />
         
         <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-10 relative z-10">
            <div className="flex items-center gap-4">
               <div className="w-10 h-10 sm:w-12 sm:h-12 rounded-2xl bg-gradient-to-br from-[var(--color-border-subtle)] to-[var(--color-border)] border border-[var(--color-border)] flex items-center justify-center text-foreground shadow-inner">
                  <Target size={20} className="sm:size-6" strokeWidth={1.5} />
               </div>
               <div>
                  <div className="text-[10px] sm:text-[11px] font-bold text-secondary/60 uppercase tracking-[0.2em] mb-0.5">Price Action Intelligence</div>
                  <div className="text-xl sm:text-2xl font-black text-foreground tracking-tight uppercase leading-none">Technical Context</div>
               </div>
            </div>
            
            <div className={`w-fit px-4 sm:px-5 py-1.5 sm:py-2 rounded-xl border-2 ${config.border} ${config.color} bg-white/50 dark:bg-slate-900/50 backdrop-blur-sm text-[10px] sm:text-[11px] font-black uppercase tracking-widest shadow-sm transition-all group-hover:scale-105`}>
               {config.label}
            </div>
         </div>

         <div className="space-y-8 relative z-10">
            <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-4">
               <div className="text-5xl sm:text-7xl font-black text-foreground tracking-tighter leading-none flex items-baseline">
                  {score !== null && score !== undefined ? score : "—"}
                  <span className="text-xl sm:text-2xl text-secondary ml-2 font-medium opacity-30 tracking-tight">/ 100</span>
               </div>
               <div className="text-left sm:text-right">
                  <div className="text-[10px] font-black text-secondary/40 uppercase tracking-[0.2em] mb-1 sm:mb-2 leading-none">Current Bias</div>
                  <div className={`text-2xl sm:text-3xl font-black ${config.color} tracking-tighter uppercase leading-none drop-shadow-sm`}>{bias || "STABLE"}</div>
               </div>
            </div>

            <div className="h-8 w-full bg-slate-100 dark:bg-slate-800/50 rounded-2xl p-1.5 border border-[var(--color-border)] overflow-hidden shadow-inner">
               <div 
                  className={`h-full rounded-xl transition-all duration-1000 ease-out shadow-[0_0_20px_-2px] ${config.bg} relative overflow-hidden`}
                  style={{ width: `${scoreNum > 0 ? scoreNum : 0.1}%` }}
               >
                 <div className="absolute inset-0 bg-gradient-to-r from-transparent via-white/20 to-transparent animate-shimmer" />
               </div>
            </div>
         </div>
      </div>

      {/* 📡 MODULE 2: MARKET REGIME NODE */}
      <div className="bg-card rounded-[2.5rem] border border-[var(--color-border)] p-6 sm:p-10 flex flex-col justify-between shadow-[0_8px_30px_rgb(0,0,0,0.04)] relative overflow-hidden group h-full transition-all hover:shadow-[0_20px_50px_rgba(0,0,0,0.08)]">
         <div className="absolute top-0 right-0 w-40 h-40 bg-blue-500/10 blur-[80px] rounded-full -mr-20 -mt-20 group-hover:bg-blue-500/20 transition-all duration-1000" />
         
         <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-8 relative z-10">
            <div className="flex items-center gap-4">
               <div className="w-10 h-10 rounded-2xl bg-blue-500/10 border border-blue-500/20 flex items-center justify-center shadow-inner">
                  <Activity size={20} className="text-blue-500" strokeWidth={1.5} />
               </div>
               <div className="text-[10px] sm:text-[11px] font-bold uppercase tracking-[0.2em] text-secondary/60 leading-none">Execution Flow</div>
            </div>
         </div>

         <div className="relative z-10 space-y-3">
            <div className="text-[10px] sm:text-[11px] font-black text-blue-500 uppercase tracking-[0.25em]">Dominant Trend</div>
            <div className="text-2xl sm:text-4xl font-black tracking-tighter uppercase leading-none text-foreground">
               {trend || "RANGING"}
            </div>
            <div className="py-3 px-4 rounded-xl bg-slate-50 dark:bg-slate-900/50 border border-[var(--color-border-subtle)]">
               <p className="text-[9px] sm:text-[10px] text-secondary/70 leading-relaxed font-bold uppercase tracking-wider">
                  Technical analysis confirms a dominant {trend || "RANGING"} phase with synchronized indicator verification.
               </p>
            </div>
         </div>

         <div className="mt-10 relative z-10 border-t border-[var(--color-border-subtle)] pt-6">
            <div className="flex justify-between items-center gap-2">
               <div className="flex flex-col">
                  <span className="text-[8px] sm:text-[9px] font-black tracking-[0.2em] text-secondary/40 uppercase leading-none mb-2">Risk Profile</span>
                  <span className="text-xs sm:text-sm font-black text-foreground tracking-tight leading-none uppercase">{risk || "STABLE"}</span>
               </div>
               <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-blue-500/5 border border-blue-500/10">
                  <div className="w-1.5 h-1.5 rounded-full bg-blue-500 animate-pulse shadow-[0_0_8px_rgba(59,130,246,0.5)]" />
                  <span className="text-[9px] font-black tracking-widest text-blue-500/80 uppercase whitespace-nowrap">Live Monitoring</span>
               </div>
            </div>
         </div>
      </div>
    </div>
  );
}
