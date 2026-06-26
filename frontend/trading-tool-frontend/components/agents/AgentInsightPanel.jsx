"use client";

import { Brain, TrendingUp, TrendingDown, Minus, Target, ShieldAlert, Cpu } from "lucide-react";

import { useAgentData } from "@/hooks/useAgentData";
import { InsightSkeleton, TextSkeleton } from "@/components/dashboard/DashboardSkeleton";
import DashboardErrorBoundary from "@/components/ui/DashboardErrorBoundary";

export default function AgentInsightPanel({ category, className = "" }) {
  const { insight, reflections, loading } = useAgentData(category);

  if (loading) {
    return <InsightSkeleton />;
  }

  if (!insight) {
    return (
      <div className={`card card-p flex items-center justify-center min-h-[200px] ${className}`}>
        <p className="text-[11px] font-bold text-secondary uppercase tracking-widest text-slate-300">
          Geen gegevens
        </p>
      </div>
    );
  }

  const {
    trend,
    bias,
    risk,
    summary,
    top_signals,
    created_at,
    updated_at,
  } = insight;

  // 🕒 Last Update Timestamp
  const lastUpdateRaw = updated_at || created_at;
  const lastUpdate = lastUpdateRaw
    ? new Date(lastUpdateRaw).toLocaleString("nl-NL", {
        day: "2-digit",
        month: "short",
        year: "numeric",
        hour: "2-digit",
        minute: "2-digit",
      })
    : null;

  const trendIcon =
    trend === "bullish" ? (
      <TrendingUp size={14} className="text-green-600" />
    ) : trend === "bearish" ? (
      <TrendingDown size={14} className="text-red-600" />
    ) : (
      <Minus size={14} className="text-secondary" />
    );

  const normalizeBullet = (item) => {
    if (!item) return "";
    if (typeof item === "string") return item;
    if (typeof item === "object") {
      return Object.entries(item).map(([k, v]) => `${k}: ${v}`).join(" • ");
    }
    return String(item);
  };

  const cleanSignals = Array.isArray(top_signals) ? top_signals.map(normalizeBullet) : [];

  return (
    <div className={`card ${className}`}>
      
      {/* HEADER */}
      <div className="card-header">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-[var(--color-border-subtle)] border border-slate-200 flex items-center justify-center text-blue-600">
            <Cpu size={20} />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h3 className="text-sm font-semibold text-foreground leading-none">Analyse</h3>
              <span className="status status-active">Actief</span>
            </div>
            <p className="text-[10px] font-bold text-secondary uppercase tracking-widest mt-1">Marktsentiment</p>
          </div>
        </div>
      </div>

      <div className="card-p space-y-8">
        
        {/* KPI Grid */}
        <div className="flex flex-wrap items-center gap-4">
           <div className="flex flex-col p-5 rounded-2xl bg-card border-2 border-slate-100 min-w-[140px] flex-1">
              <span className="metric-label text-blue-600">Trend</span>
              <div className="flex items-center gap-2">
                 {trendIcon}
                 <span className="text-sm font-black text-foreground uppercase tracking-tight">{trend || "Neutraal"}</span>
              </div>
           </div>

           <div className="flex flex-col p-5 rounded-2xl bg-card border-2 border-slate-100 min-w-[140px] flex-1">
              <span className="metric-label text-blue-600">Sentiment</span>
              <div className="flex items-center gap-2">
                 <Target size={14} className="text-secondary" />
                 <span className="text-sm font-black text-foreground uppercase tracking-tight">{bias || "Geen"}</span>
              </div>
           </div>

           <div className="flex flex-col p-5 rounded-2xl bg-card border-2 border-slate-100 min-w-[140px] flex-1">
              <span className="metric-label text-blue-600">Risico</span>
              <div className="flex items-center gap-2">
                 <ShieldAlert size={14} className="text-secondary" />
                 <span className="text-sm font-black text-foreground uppercase tracking-tight">{risk || "Laag"}</span>
              </div>
           </div>
        </div>

        {/* SUMMARY */}
        <div className="space-y-4">
           <div className="metric-label ml-1">Toelichting</div>
           <div className="bg-gradient-to-br from-white to-slate-50 border-2 border-slate-100 p-8 rounded-2xl relative overflow-hidden">
              <div className="absolute top-4 right-6 opacity-[0.2] text-slate-400">
                 <Brain size={16} />
              </div>
              <p className="text-sm font-medium text-foreground leading-relaxed max-w-4xl tracking-tight italic">
                {summary}
              </p>
           </div>
        </div>

        {/* REFLECTIONS */}
        <div className="space-y-4">
           {loading ? (
             <div className="space-y-6">
               <div className="p-4 bg-[var(--color-border-subtle)] dark:bg-slate-900/50 rounded-2xl border border-slate-100 dark:border-slate-800">
                  <TextSkeleton lines={2} />
               </div>
               <div className="p-4 bg-[var(--color-border-subtle)] dark:bg-slate-900/50 rounded-2xl border border-slate-100 dark:border-slate-800">
                  <TextSkeleton lines={2} />
               </div>
             </div>
           ) : (
             reflections?.length > 0 ? (
               reflections.map((r, i) => (
                 <div key={i} className="p-4 bg-[var(--color-border-subtle)] dark:bg-slate-900/50 rounded-2xl border border-slate-100 dark:border-slate-800 hover:border-blue-500/30 transition-all group shadow-sm">
                    <p className="text-xs text-secondary dark:text-slate-400 font-medium italic leading-relaxed group-hover:text-slate-900 dark:group-hover:text-slate-200">
                      "{r.reflection}"
                    </p>
                 </div>
               ))
             ) : (
               <div className="text-[11px] font-bold text-slate-300 dark:text-slate-600 uppercase tracking-widest text-center py-8">
                  Nog geen reflecties vastgelegd
               </div>
             )
           )}
        </div>

        {/* SIGNALS */}
        {cleanSignals.length > 0 && (
          <div className="space-y-3">
             <div className="text-[11px] font-bold text-secondary uppercase tracking-widest">Signalen</div>
             <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                {cleanSignals.map((s, i) => (
                  <div key={i} className="flex items-center gap-3 p-4 bg-card border border-slate-100 rounded-lg shadow-sm hover:border-blue-200 hover:bg-blue-50 transition-all">
                     <div className="w-1.5 h-1.5 rounded-full bg-blue-500 shrink-0" />
                     <div className="text-[10px] font-semibold text-dim uppercase tracking-tight leading-tight">
                        {s}
                     </div>
                  </div>
                ))}
             </div>
          </div>
        )}

        {/* FOOTER */}
        <footer className="pt-6 border-t border-slate-100 flex items-center justify-between opacity-50">
           <div className="text-[9px] font-bold text-secondary uppercase tracking-widest">Controle voltooid</div>
           {lastUpdate && (
             <div className="text-[9px] font-bold text-secondary uppercase tracking-[0.1em]">
               Bijgewerkt: {lastUpdate}
             </div>
           )}
        </footer>
      </div>
    </div>
  );
}
