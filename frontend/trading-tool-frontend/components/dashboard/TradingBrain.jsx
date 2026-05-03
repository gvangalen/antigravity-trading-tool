"use client";

import React from "react";
import CardWrapper from "@/components/ui/CardWrapper";
import { useActiveSetup } from "@/app/providers/SetupProvider";
import { useScoresData } from "@/hooks/useScoresData";
import { useSidebarData } from "@/hooks/useSidebarData";
import { useSetupStrategy } from "@/hooks/useSetupStrategy";
import Link from "next/link";
import { 
  Rocket, 
  Target, 
  ShieldAlert, 
  BrainCircuit, 
  Zap, 
  ChevronRight,
  Layers
} from "lucide-react";
import { BrainSkeleton, TextSkeleton } from "./DashboardSkeleton";

import { useTranslation } from "@/app/providers/I18nProvider";

/**
 * 🧠 TradingBrain — Unified Decision Panel (V2.1)
 * Combines Master Score, Active Setup, AI Advice, Bot Status, and Daily Snippet.
 */
export default function TradingBrain({ symbol = "BTC" }) {
  const { t } = useTranslation();
  const { activeSetup, loading: setupLoading } = useActiveSetup();
  const { macro, technical, market, setup: dailySetup, master, loading: scoresLoading } = useScoresData(symbol);
  const { summary, aiStatus, loading: sidebarLoading } = useSidebarData();
  const { data: marketIntelligence, loading: intelLoading } = useMarketIntelligence(symbol);
  const { strategy, loading: strategyLoading } = useSetupStrategy(activeSetup?.id);

  const isLoading = setupLoading || scoresLoading || sidebarLoading || strategyLoading || intelLoading;
  
  // 1. DATA PREP
  const ticker = activeSetup?.symbol || "–";
  const timeframe = activeSetup?.timeframe || "–";
  const setupScore = Math.round(dailySetup?.score || activeSetup?.score || 0);
  
  const advice = {
    entry: strategy?.entry || "–",
    targets: Array.isArray(strategy?.targets) ? strategy.targets.join(" / ") : (strategy?.targets || "–"),
    stopLoss: strategy?.stop_loss || "–",
    trend: activeSetup?.trend || "Neutral",
    riskReward: strategy?.risk_reward || "N/A",
    riskLevel: strategy?.risk_profile || "Medium",
  };

  const isBotActive = aiStatus?.state === "active" || aiStatus?.state === "running";
  
  const isDCA = activeSetup?.setup_type?.toLowerCase() === "dca" || 
                strategy?.setup_type?.toLowerCase() === "dca" || 
                activeSetup?.name?.toLowerCase().includes("dca");
  
  // Minimal report snippet (1 sentence)
  const reportSnippet = (marketIntelligence?.summary || master?.summary || summary)?.split('.')[0] + '.';

  if (isLoading && !activeSetup) {
    return <BrainSkeleton />;
  }

  return (
    <div className="flex flex-col gap-6 sticky top-28 h-fit">
      
      {/* 🚀 PRIMARY: TRADING ADVICE (EXECUTION) */}
      <CardWrapper 
        title={<div className="flex items-center gap-2 text-foreground dark:text-white"><Rocket className="w-5 h-5 text-blue-600" /> {t.dashboard.brain.execution}</div>}
      >
        <div className="space-y-5">
          <div className="bg-[var(--color-border-subtle)] dark:bg-slate-900 p-4 rounded-xl border border-slate-100 dark:border-slate-800 relative overflow-hidden transition-colors">
             <div className="absolute top-0 right-0 p-2 opacity-10">
                <Zap size={48} className="text-blue-600" />
             </div>
             
             <div className="flex justify-between items-end mb-4">
               <div>
                  <p className="text-[10px] uppercase tracking-widest text-secondary dark:text-slate-500 font-bold">{t.dashboard.brain.signal}</p>
                  <h4 className="text-xl font-black text-foreground dark:text-slate-100">{ticker} {advice.trend}</h4>
               </div>
               <div className="text-right">
                  <p className="text-[10px] uppercase tracking-widest text-secondary dark:text-slate-500 font-bold">{t.dashboard.brain.timeframe}</p>
                  <p className="text-sm font-black text-foreground dark:text-slate-100">{timeframe}</p>
               </div>
             </div>

             {isDCA ? (
               <div className="bg-blue-50/50 dark:bg-blue-900/20 border border-blue-100 dark:border-blue-900/30 p-4 rounded-xl mt-4">
                  <div className="flex items-center gap-2 mb-2">
                     <Layers className="w-4 h-4 text-blue-600" />
                     <span className="text-xs font-black text-blue-800 dark:text-blue-300 uppercase tracking-widest">DCA Accumulation</span>
                  </div>
                  <p className="text-xs font-medium text-slate-700 dark:text-slate-300 leading-relaxed">
                     Actieve Dollar Cost Averaging strategie. Instapmomenten en targets worden dynamisch door de bot bepaald op basis van de deviatie logica, in plaats van vaste levels.
                  </p>
               </div>
             ) : (
               <div className="grid grid-cols-1 gap-3">
                  <div className="flex items-center justify-between bg-white/50 dark:bg-slate-800/50 px-3 py-2 rounded-lg border border-white dark:border-slate-700 transition-colors">
                     <div className="flex items-center gap-2">
                         <ChevronRight size={14} className="text-blue-600" />
                         <span className="text-xs font-black text-secondary dark:text-slate-500 uppercase tracking-widest">{t.dashboard.brain.entry}</span>
                     </div>
                     <span className="text-lg font-mono font-black text-blue-700 dark:text-blue-400">
                       {advice.entry !== "–" ? `$${Number(advice.entry).toLocaleString()}` : "–"}
                     </span>
                  </div>

                  <div className="flex items-center justify-between bg-white/50 dark:bg-slate-800/50 px-3 py-2 rounded-lg border border-white dark:border-slate-700 transition-colors">
                     <div className="flex items-center gap-2">
                         <Target size={14} className="text-emerald-600" />
                         <span className="text-xs font-black text-secondary dark:text-slate-500 uppercase tracking-widest">{t.dashboard.brain.targets}</span>
                     </div>
                     <span className="text-sm font-mono font-black text-emerald-700 dark:text-emerald-400">
                       {Array.isArray(strategy?.targets) 
                         ? strategy.targets.map(t => `$${Number(t).toLocaleString()}`).join(" / ")
                         : advice.targets
                       }
                     </span>
                  </div>

                  <div className="flex items-center justify-between bg-white/50 dark:bg-slate-800/50 px-3 py-2 rounded-lg border border-white dark:border-slate-700 transition-colors">
                     <div className="flex items-center gap-2">
                         <ShieldAlert size={14} className="text-rose-500" />
                         <span className="text-xs font-black text-secondary dark:text-slate-500 uppercase tracking-widest">{t.dashboard.brain.stop_loss}</span>
                     </div>
                     <span className="text-sm font-mono font-black text-rose-600 dark:text-rose-400">
                       {advice.stopLoss !== "–" ? `$${Number(advice.stopLoss).toLocaleString()}` : "–"}
                     </span>
                  </div>
               </div>
             )}

             {/* 📊 REAL EXECUTION METADATA */}
             <div className="mt-4 flex items-center justify-between px-1">
                <div className="flex flex-col">
                   <span className="text-[9px] uppercase font-bold text-secondary dark:text-slate-500 opacity-60">{t.dashboard.brain.risk_reward}</span>
                   <span className="text-xs font-black text-foreground dark:text-slate-100">{isDCA ? "Dynamic" : advice.riskReward}</span>
                </div>
                <div className="text-right flex flex-col">
                   <span className="text-[9px] uppercase font-bold text-secondary dark:text-slate-500 opacity-60">{t.dashboard.brain.risk_level}</span>
                   <span className={`text-xs font-black ${advice.riskLevel?.toLowerCase() === 'high' ? 'text-orange-500' : 'text-blue-600 dark:text-blue-400'}`}>
                      {isDCA ? "Scale-In" : advice.riskLevel}
                   </span>
                </div>
             </div>
          </div>
        </div>
      </CardWrapper>

      {/* 🧠 SUPPORTING: MARKET & SETUP INTELLIGENCE */}
      <CardWrapper>
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            {/* Global Market Confidence */}
            <div className="flex flex-col gap-1 p-3 bg-[var(--color-border-subtle)] dark:bg-slate-900 rounded-xl border border-slate-100 dark:border-slate-800">
               <span className="text-[9px] uppercase font-bold text-secondary dark:text-slate-500 tracking-widest leading-none">{t.dashboard.brain.market_health}</span>
               <div className="flex items-center gap-2 mt-1">
                  <div className="w-8 h-8 rounded-full border-2 border-blue-600 flex items-center justify-center bg-card dark:bg-slate-800 shadow-sm">
                     <span className="text-xs font-black text-foreground dark:text-slate-100">{master.score}</span>
                  </div>
                  <span className="text-[10px] font-bold text-dim dark:text-slate-400 uppercase tracking-tighter">{t.dashboard.brain.ai_confidence}</span>
               </div>
            </div>
            
            {/* Specific Asset Strength */}
            <div className="flex flex-col gap-1 p-3 bg-blue-50/50 dark:bg-blue-900/20 rounded-xl border border-blue-100 dark:border-blue-900/30 transition-colors">
               <span className="text-[9px] uppercase font-bold text-blue-600 dark:text-blue-400 opacity-60 tracking-widest leading-none">{t.dashboard.brain.setup_strength}</span>
               <div className="flex items-baseline gap-1 mt-1">
                  <span className="text-xl font-black text-blue-700 dark:text-blue-300">{setupScore}%</span>
                  <span className="text-[10px] font-bold text-blue-600 dark:text-blue-400 opacity-70 uppercase">{t.dashboard.brain.score}</span>
               </div>
            </div>
          </div>

          <div className="border-t border-slate-100 dark:border-slate-800 mt-4 pt-4 px-1">
             
             {/* 🔍 DEEP DIVE SECTION */}
             <div className="space-y-4">
                <div className="flex items-center gap-2 mb-1">
                   <div className="w-1 h-3 bg-blue-500 rounded-full" />
                   <span className="text-[9px] uppercase font-black text-foreground dark:text-slate-300 tracking-widest">Intelligence Deep-Dive</span>
                </div>
                
                <div className="space-y-3">
                   {[
                      { label: "Macro", data: macro?.top_contributors },
                      { label: "Technical", data: technical?.top_contributors },
                      { label: "Market", data: market?.top_contributors }
                   ].map((item, idx) => (
                      <div key={idx} className="flex flex-col gap-1">
                         <span className="text-[8px] uppercase font-black text-secondary dark:text-slate-500 tracking-wider">{item.label} Drivers</span>
                         <div className="flex flex-wrap gap-1">
                            {(Array.isArray(item.data) ? item.data : []).slice(0, 3).map((tag, tIdx) => (
                               <span key={tIdx} className="text-[9px] font-bold px-1.5 py-0.5 bg-slate-50 dark:bg-slate-900 border border-slate-100 dark:border-slate-800 rounded text-slate-600 dark:text-slate-400">
                                  {tag}
                               </span>
                            ))}
                            {(!item.data || item.data.length === 0) && (
                               <span className="text-[9px] font-bold text-secondary/30 italic">No specific signals</span>
                            )}
                         </div>
                      </div>
                   ))}
                </div>
             </div>

             {/* 🧠 MASTER SNIPPET (Moved below Deep-Dive) */}
             <div className="mt-6 pt-5 border-t border-dashed border-slate-200 dark:border-slate-800">
                <div className="flex items-center gap-2 mb-2">
                    <BrainCircuit size={14} className="text-blue-600" />
                    <span className="text-[10px] uppercase font-black text-secondary dark:text-slate-500 tracking-widest">{t.dashboard.brain.master_snippet}</span>
                </div>
                <div className="text-[11px] leading-relaxed text-slate-700 dark:text-slate-300 font-medium italic">
                    {sidebarLoading && !reportSnippet ? (
                      <TextSkeleton lines={2} className="mt-1" />
                    ) : (
                      reportSnippet && reportSnippet !== "undefined." ? `"${reportSnippet}"` : "Nog geen samenvatting beschikbaar."
                    )}
                </div>
             </div>

             <Link 
               href="/report"
               className="mt-5 text-[10px] uppercase font-black text-blue-600 dark:text-blue-400 tracking-widest hover:underline flex items-center gap-1 group"
             >
               {t.dashboard.brain.explore_report} <ChevronRight size={10} className="group-hover:translate-x-1 transition-transform" />
             </Link>
          </div>
        </div>
      </CardWrapper>

      {/* 🤖 BOT STATUS (Conditional) */}
      {isBotActive && (
        <div className="bg-emerald-50 dark:bg-emerald-950/20 border border-emerald-100 dark:border-emerald-900/30 p-3 rounded-xl flex items-center justify-between">
           <div className="flex items-center gap-2">
              <div className="w-2 h-2 bg-emerald-500 rounded-full animate-pulse" />
              <span className="text-xs font-black text-emerald-800 dark:text-emerald-400 uppercase tracking-tight">{t.dashboard.brain.bot_active}</span>
           </div>
           <span className="text-[10px] bg-emerald-100 dark:bg-emerald-900/40 text-emerald-800 dark:text-emerald-300 px-2 py-0.5 rounded-full font-bold">
              {aiStatus.strategy}
           </span>
        </div>
      )}
    </div>
  );
}
