"use client";

import { useState, useEffect } from "react";
import { Activity, LayoutGrid, History, TrendingUp } from "lucide-react";

// Hooks
import { useMarketData } from "@/hooks/useMarketData";
import { useScoresData } from "@/hooks/useScoresData";
import { useOnboarding } from "@/hooks/useOnboarding";

// Components
import MarketIndicatorScoreView from "@/components/market/MarketIndicatorScoreView";
import MarketTerminalHUD from "@/components/market/MarketTerminalHUD";
import TechnicalTerminalGrid from "@/components/technical/TechnicalTerminalGrid";
import MarketSevenDayTable from "@/components/market/MarketSevenDayTable";
import MarketForwardReturnTabs from "@/components/market/MarketForwardReturnTabs";
import AgentInsightPanel from "@/components/agents/AgentInsightPanel";
import OnboardingBanner from "@/components/onboarding/OnboardingBanner";
import DashboardErrorBoundary from "@/components/ui/DashboardErrorBoundary";

export default function MarketPage() {
  // ===============================
  // 🧭 ONBOARDING HOOK
  // ===============================
  const { status, completeStep } = useOnboarding();

  // ===============================
  // 📊 MARKET DATA
  // ===============================
  const { 
    sevenDayData, 
    forwardReturns, 
    availableIndicators,
    loading 
  } = useMarketData();

  // ===============================
  // 📈 SCORE DATA
  // ===============================
  const { market: marketScore } = useScoresData();

  // ===============================
  // 🔥 ONBOARDING TRIGGER
  // ===============================
  useEffect(() => {
    if (
      availableIndicators?.length > 0 && 
      status && 
      status.has_market === false
    ) {
      console.log("🧭 Onboarding: market step completed");
      completeStep("market");
    }
  }, [availableIndicators, status, completeStep]);

  // ===============================
  // 🛡️ SAFE FALLBACKS
  // ===============================
  const safeMarketScore = marketScore?.score ?? null;
  const safeSevenDay = Array.isArray(sevenDayData) ? sevenDayData : [];
  const safeForward = forwardReturns || {};

  const biasText = 
    (safeMarketScore ?? 50) >= 75 ? "Positive" : 
    (safeMarketScore ?? 50) <= 25 ? "Negative" : "Neutral";

  // ===============================
  // 🧱 RENDER
  // ===============================
  return (
    <div className="page-container bg-white dark:bg-[#020617] transition-colors min-h-screen">
      <OnboardingBanner step="market" />

      {/* 🟢 STANDARD PAGE HEADER */}
      <header className="page-header border-l-4 border-blue-600 pl-8 mb-16">
        <div className="page-label text-[11px] font-black text-blue-600 dark:text-blue-500 uppercase tracking-[0.3em] mb-2 opacity-80 flex items-center gap-2">
           <Activity size={12} />
           Status: Connected
        </div>
        <h1 className="page-title text-5xl font-black text-slate-900 dark:text-slate-100 tracking-tight leading-none mb-3">Market</h1>
        <p className="page-subtitle text-[15px] font-medium text-slate-400 dark:text-slate-500 max-w-2xl leading-relaxed">Analysis of market sentiment and price action</p>
      </header>

      {/* 🚀 MARKET HUD */}
      <DashboardErrorBoundary>
        <MarketTerminalHUD 
          score={safeMarketScore} 
          bias={biasText}
          loading={loading || !marketScore}
        />
      </DashboardErrorBoundary>

      {/* 🧠 ANALYSIS (HERO SECTION) */}
      <div className="space-y-8 px-4">
         <div className="flex items-center gap-4 mb-2">
            <div className="w-8 h-0.5 bg-blue-600/30" />
            <span className="text-[11px] font-black text-slate-400 dark:text-slate-500 uppercase tracking-[0.25em] opacity-90">Analysis</span>
         </div>
         <DashboardErrorBoundary>
           <AgentInsightPanel category="market" />
         </DashboardErrorBoundary>
      </div>

      <div className="grid grid-cols-1 gap-20 pt-16">
        {/* 🛠️ CONFIG */}
        <div className="card bg-white dark:bg-[#0f172a] border-2 border-slate-100 dark:border-slate-800 rounded-3xl overflow-hidden shadow-sm">
          <div className="card-header border-b border-slate-100 dark:border-slate-800 p-6">
             <div className="card-title text-slate-900 dark:text-white flex items-center gap-3">
               <LayoutGrid size={16} className="text-blue-600" />
               Configuration
             </div>
          </div>
          <div className="card-p p-8">
            <MarketIndicatorScoreView
              availableIndicators={availableIndicators || []}
              loading={loading}
            />
          </div>
        </div>

        {/* 📊 SIGNALS */}
        <div className="card bg-white dark:bg-[#0f172a] border-2 border-slate-100 dark:border-slate-800 rounded-3xl overflow-hidden shadow-sm">
           <div className="card-header border-b border-slate-100 dark:border-slate-800 p-6">
              <div className="card-title text-slate-900 dark:text-white flex items-center gap-3">
                <Activity size={16} className="text-blue-600" />
                Signals
              </div>
           </div>
           <div className="card-p p-0">
              <DashboardErrorBoundary>
                <TechnicalTerminalGrid
                  title="Market Signal Monitor"
                  onRemoveIndicator={() => {}}
                  loading={loading}
                />
              </DashboardErrorBoundary>
           </div>
        </div>

        <div className="grid grid-cols-1 gap-12 pb-24">
          {/* 📅 HISTORY */}
          <div className="card bg-white dark:bg-[#0f172a] border-2 border-slate-100 dark:border-slate-800 rounded-3xl overflow-hidden shadow-sm">
             <div className="card-header border-b border-slate-100 dark:border-slate-800 p-6">
                <div className="card-title text-slate-900 dark:text-white flex items-center gap-3">
                  <History size={16} className="text-blue-600" />
                  History
                </div>
             </div>
             <div className="card-p p-8">
               <DashboardErrorBoundary>
                 <MarketSevenDayTable history={safeSevenDay} loading={loading} />
               </DashboardErrorBoundary>
             </div>
          </div>

          {/* 🔮 FORECAST */}
          <div className="card bg-white dark:bg-[#0f172a] border-2 border-slate-100 dark:border-slate-800 rounded-3xl overflow-hidden shadow-sm">
             <div className="card-header border-b border-slate-100 dark:border-slate-800 p-6">
                <div className="card-title text-slate-900 dark:text-white flex items-center gap-3">
                  <TrendingUp size={16} className="text-blue-600" />
                  Forecast
                </div>
             </div>
             <div className="card-p p-8">
               <MarketForwardReturnTabs data={safeForward} />
             </div>
          </div>
        </div>
      </div>

      {loading && (
        <div className="fixed bottom-8 right-8 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 px-6 py-3 rounded-2xl shadow-xl flex items-center gap-3 animate-bounce z-50 transition-colors">
           <div className="w-2 h-2 rounded-full bg-blue-600 animate-pulse" />
           <span className="text-[10px] font-black text-slate-600 dark:text-slate-300 uppercase tracking-widest">Loading Data...</span>
        </div>
      )}
    </div>
  );
}
