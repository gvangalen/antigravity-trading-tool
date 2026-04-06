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
  Bot, 
  BrainCircuit, 
  Zap, 
  ChevronRight
} from "lucide-react";

/**
 * 🧠 TradingBrain — Unified Decision Panel (V2.1)
 * Combines Master Score, Active Setup, AI Advice, Bot Status, and Daily Snippet.
 */
export default function TradingBrain() {
  const { activeSetup } = useActiveSetup();
  const { master, loading: scoresLoading } = useScoresData();
  const { summary, aiStatus, loading: sidebarLoading } = useSidebarData();
  const { strategy, loading: strategyLoading } = useSetupStrategy(activeSetup?.id);
  
  // 1. DATA PREP
  const ticker = activeSetup?.symbol || "–";
  const timeframe = activeSetup?.timeframe || "–";
  const setupScore = Math.round(activeSetup?.score || 0);
  
  // 🟢 AI Advice (Execution) - Now from REAL Strategy Layer
  const advice = {
    entry: strategy?.entry || "–",
    targets: Array.isArray(strategy?.targets) ? strategy.targets.join(" / ") : (strategy?.targets || "–"),
    stopLoss: strategy?.stop_loss || "–",
    trend: activeSetup?.trend || "Neutral",
    riskReward: strategy?.risk_reward || "N/A",
    riskLevel: strategy?.risk_profile || "Medium",
  };

  const isBotActive = aiStatus?.state === "active" || aiStatus?.state === "running";
  
  // Minimal report snippet (1 sentence)
  const reportSnippet = summary?.split('.')[0] + '.';

  return (
    <div className="flex flex-col gap-6 sticky top-28 h-fit">
      
      {/* 🚀 PRIMARY: TRADING ADVICE (EXECUTION) */}
      <CardWrapper 
        title={<div className="flex items-center gap-2"><Rocket className="w-5 h-5 text-[var(--primary)]" /> Execution</div>}
      >
        <div className="space-y-5">
          <div className="bg-[var(--bg-soft)] p-4 rounded-xl border border-[var(--primary-soft)] relative overflow-hidden">
             <div className="absolute top-0 right-0 p-2 opacity-10">
                <Zap size={48} className="text-[var(--primary)]" />
             </div>
             
             <div className="flex justify-between items-end mb-4">
               <div>
                  <p className="text-[10px] uppercase tracking-widest text-[var(--text-light)] font-bold">Signal</p>
                  <h4 className="text-xl font-bold text-[var(--text-dark)]">{ticker} {advice.trend}</h4>
               </div>
               <div className="text-right">
                  <p className="text-[10px] uppercase tracking-widest text-[var(--text-light)] font-bold">Timeframe</p>
                  <p className="text-sm font-semibold">{timeframe}</p>
               </div>
             </div>

             <div className="grid grid-cols-1 gap-3">
                <div className="flex items-center justify-between bg-white/50 px-3 py-2 rounded-lg border border-white">
                   <div className="flex items-center gap-2">
                      <ChevronRight size={14} className="text-[var(--primary)]" />
                      <span className="text-xs font-semibold text-[var(--text-light)]">ENTRY</span>
                   </div>
                   <span className="text-lg font-mono font-bold text-[var(--primary-dark)]">${advice.entry}</span>
                </div>

                <div className="flex items-center justify-between bg-white/50 px-3 py-2 rounded-lg border border-white">
                   <div className="flex items-center gap-2">
                      <Target size={14} className="text-green-600" />
                      <span className="text-xs font-semibold text-[var(--text-light)]">TARGETS</span>
                   </div>
                   <span className="text-sm font-mono font-bold text-green-700">{advice.targets}</span>
                </div>

                <div className="flex items-center justify-between bg-white/50 px-3 py-2 rounded-lg border border-white">
                   <div className="flex items-center gap-2">
                      <ShieldAlert size={14} className="text-red-500" />
                      <span className="text-xs font-semibold text-[var(--text-light)]">STOP LOSS</span>
                   </div>
                   <span className="text-sm font-mono font-bold text-red-600">${advice.stopLoss}</span>
                </div>
             </div>

             {/* 📊 REAL EXECUTION METADATA */}
             <div className="mt-4 flex items-center justify-between px-1">
                <div className="flex flex-col">
                   <span className="text-[9px] uppercase font-bold text-[var(--text-light)] opacity-60">Risk/Reward</span>
                   <span className="text-xs font-black text-[var(--text-dark)]">{advice.riskReward}</span>
                </div>
                <div className="text-right flex flex-col">
                   <span className="text-[9px] uppercase font-bold text-[var(--text-light)] opacity-60">Risk Level</span>
                   <span className={`text-xs font-black ${advice.riskLevel?.toLowerCase() === 'high' ? 'text-orange-500' : 'text-[var(--primary)]'}`}>
                      {advice.riskLevel}
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
            <div className="flex flex-col gap-1 p-3 bg-slate-50 rounded-xl border border-slate-100">
               <span className="text-[9px] uppercase font-bold text-slate-400 tracking-widest leading-none">Market Health</span>
               <div className="flex items-center gap-2 mt-1">
                  <div className="w-8 h-8 rounded-full border-2 border-[var(--primary)] flex items-center justify-center bg-white shadow-sm">
                     <span className="text-xs font-black text-[var(--primary-dark)]">{master.score}</span>
                  </div>
                  <span className="text-[10px] font-bold text-slate-600 uppercase tracking-tighter">AI Confidence</span>
               </div>
            </div>
            
            {/* Specific Asset Strength */}
            <div className="flex flex-col gap-1 p-3 bg-[var(--primary-soft)] rounded-xl border border-[var(--primary-soft)] bg-opacity-30">
               <span className="text-[9px] uppercase font-bold text-[var(--primary-dark)] opacity-60 tracking-widest leading-none">Setup Strength</span>
               <div className="flex items-baseline gap-1 mt-1">
                  <span className="text-xl font-black text-[var(--primary-dark)]">{setupScore}%</span>
                  <span className="text-[10px] font-bold text-[var(--primary-dark)] opacity-70 uppercase">Score</span>
               </div>
            </div>
          </div>

          <div className="border-t border-[var(--card-border)] mt-4 pt-4 px-1">
             <div className="flex items-center gap-2 mb-2">
                <BrainCircuit size={14} className="text-[var(--primary)]" />
                <span className="text-[10px] uppercase font-black text-slate-400 tracking-widest">Master Snippet</span>
             </div>
             <p className="text-[11px] leading-relaxed text-slate-700 font-medium italic">
               "{reportSnippet}"
             </p>
             <Link 
               href="/report"
               className="mt-3 text-[10px] uppercase font-black text-[var(--primary)] tracking-widest hover:underline flex items-center gap-1 group"
             >
               Explore Full Daily Report <ChevronRight size={10} className="group-hover:translate-x-1 transition-transform" />
             </Link>
          </div>
        </div>
      </CardWrapper>

      {/* 🤖 BOT STATUS (Conditional) */}
      {isBotActive && (
        <div className="bg-green-50 border border-green-100 p-3 rounded-xl flex items-center justify-between animate-pulse-subtle">
           <div className="flex items-center gap-2">
              <Bot size={16} className="text-green-600" />
              <span className="text-xs font-bold text-green-800 uppercase tracking-tight">Bot Active</span>
           </div>
           <span className="text-[10px] bg-green-200 text-green-800 px-2 py-0.5 rounded-full font-bold">
              {aiStatus.strategy}
           </span>
        </div>
      )}
    </div>
  );
}
