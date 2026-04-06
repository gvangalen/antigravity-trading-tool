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

  const adviesText = 
    (safeMarketScore ?? 50) >= 75 ? "Positief" : 
    (safeMarketScore ?? 50) <= 25 ? "Negatief" : "Neutraal";

  // ===============================
  // 🧱 RENDER
  // ===============================
  return (
    <div className="page-container">
      <OnboardingBanner step="market" />

      {/* 🟢 STANDARD PAGE HEADER */}
      <header className="page-header">
        <div className="page-label">
           <Activity size={12} />
           Status: Verbonden
        </div>
        <h1 className="page-title">Markt</h1>
        <p className="page-subtitle">Analyse van marktsentiment en prijsactie</p>
      </header>

      {/* 🚀 MARKET HUD */}
      <MarketTerminalHUD 
        score={safeMarketScore} 
        bias={adviesText}
        loading={loading}
      />

      {/* 🧠 ANALYSE (HERO SECTION) */}
      <div className="space-y-8 px-4">
         <div className="flex items-center gap-4 mb-2">
            <div className="w-8 h-0.5 bg-blue-600/30" />
            <span className="text-[11px] font-black text-slate-400 uppercase tracking-[0.25em] opacity-90">Analyse</span>
         </div>
         <AgentInsightPanel category="market" />
      </div>

      <div className="grid grid-cols-1 gap-20 pt-16">
        {/* 🛠️ INSTELLINGEN */}
        <div className="card">
          <div className="card-header">
             <div className="card-title">
               <LayoutGrid size={16} className="text-blue-600" />
               Instellingen
             </div>
          </div>
          <div className="card-p">
            <MarketIndicatorScoreView
              availableIndicators={availableIndicators || []}
              loading={loading}
            />
          </div>
        </div>

        {/* 📊 SIGNALEN (DAGELIJKSE ANALYSE) */}
        <div className="card">
           <div className="card-header">
              <div className="card-title">
                <Activity size={16} className="text-blue-600" />
                Signalen
              </div>
           </div>
           <div className="card-p p-0">
              <TechnicalTerminalGrid
                title="Market Signal Monitor"
                onRemoveIndicator={() => {}}
              />
           </div>
        </div>

        <div className="grid grid-cols-1 gap-12">
          {/* 📅 GESCHIEDENIS */}
          <div className="card">
             <div className="card-header">
                <div className="card-title">
                  <History size={16} className="text-blue-600" />
                  Geschiedenis
                </div>
             </div>
             <div className="card-p">
               <MarketSevenDayTable history={safeSevenDay} />
             </div>
          </div>

          {/* 🔮 PROGNOSE */}
          <div className="card">
             <div className="card-header">
                <div className="card-title">
                  <TrendingUp size={16} className="text-blue-600" />
                  Prognose
                </div>
             </div>
             <div className="card-p">
               <MarketForwardReturnTabs data={safeForward} />
             </div>
          </div>
        </div>
      </div>

      {loading && (
        <div className="fixed bottom-8 right-8 bg-white border border-slate-200 px-6 py-3 rounded-2xl shadow-xl flex items-center gap-3 animate-bounce z-50">
           <div className="w-2 h-2 rounded-full bg-blue-600 animate-pulse" />
           <span className="text-[10px] font-black text-slate-600 uppercase tracking-widest">Gegevens laden...</span>
        </div>
      )}
    </div>
  );
}
