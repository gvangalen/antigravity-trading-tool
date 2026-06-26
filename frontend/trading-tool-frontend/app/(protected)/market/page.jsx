"use client";

import { useState, useEffect } from "react";
import { Activity, LayoutGrid, History, TrendingUp } from "lucide-react";
import { useTranslation } from "@/app/providers/I18nProvider";

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
import { trackAssistantEvent } from "@/lib/api/assistantAnalytics";

import { useCurrentAsset } from "@/hooks/useCurrentAsset";

export default function MarketPage() {
  const { symbol: activeSymbol } = useCurrentAsset();
  const { t } = useTranslation();
  const marketT = t.pages.market;

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
    btcLive,
    loading
  } = useMarketData(activeSymbol);

  // ===============================
  // 📈 SCORE DATA
  // ===============================
  const { market: marketScore } = useScoresData(activeSymbol);

  useEffect(() => {
    trackAssistantEvent({
      event_name: "screen_view",
      page: "/market",
      surface: "web",
      flow_type: "market",
      asset: activeSymbol || null,
    });
  }, [activeSymbol]);

  // ===============================
  // 🔥 ONBOARDING TRIGGER
  // ===============================
  useEffect(() => {
    if (
      availableIndicators?.length > 0 && 
      status && 
      status.has_market === false
    ) {
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
    (safeMarketScore ?? 50) >= 75 ? marketT.biasPositive : 
    (safeMarketScore ?? 50) <= 25 ? marketT.biasNegative : marketT.biasNeutral;

  // ===============================
  // 🧱 RENDER
  // ===============================
  return (
    <div className="page-container bg-white dark:bg-[#020617] transition-colors min-h-screen">
      <OnboardingBanner step="market" />

      {/* 🟢 STANDARD PAGE HEADER */}
      <header className="page-header border-l-4 border-blue-600 pl-8 mb-16 flex flex-col md:flex-row md:items-end justify-between gap-8">
        <div className="flex-1">
          <div className="page-label text-[11px] font-black text-blue-600 dark:text-blue-500 uppercase tracking-[0.3em] mb-2 opacity-80 flex items-center gap-2">
             <Activity size={12} />
             {marketT.statusConnected}
          </div>
          <h1 className="page-title text-5xl font-black text-slate-900 dark:text-slate-100 tracking-tight leading-none mb-3">{marketT.title}</h1>
          <p className="page-subtitle text-[15px] font-medium text-slate-400 dark:text-slate-500 max-w-2xl leading-relaxed">{marketT.subtitle.replace("{symbol}", activeSymbol)}</p>
        </div>
      </header>

      {/* 🚀 MARKET HUD */}
      <DashboardErrorBoundary>
        <MarketTerminalHUD 
          score={safeMarketScore} 
          bias={biasText}
          btc={btcLive}
          loading={loading || !marketScore}
          symbol={activeSymbol}
        />
      </DashboardErrorBoundary>

      {/* 🧠 ANALYSIS (HERO SECTION) */}
      <div className="space-y-8 px-4">
         <div className="flex items-center gap-4 mb-2">
            <div className="w-8 h-0.5 bg-blue-600/30" />
            <span className="text-[11px] font-black text-slate-400 dark:text-slate-500 uppercase tracking-[0.25em] opacity-90">{marketT.analysis.replace("{symbol}", activeSymbol)}</span>
         </div>
         <DashboardErrorBoundary>
           <AgentInsightPanel category="market" symbol={activeSymbol} />
         </DashboardErrorBoundary>
      </div>

      <div className="grid grid-cols-1 gap-20 pt-16">
        {/* 🛠️ CONFIG */}
        <div className="card bg-white dark:bg-[#0f172a] border-2 border-slate-100 dark:border-slate-800 rounded-3xl overflow-hidden shadow-sm">
          <div className="card-header border-b border-slate-100 dark:border-slate-800 p-6">
             <div className="card-title text-slate-900 dark:text-white flex items-center gap-3">
               <LayoutGrid size={16} className="text-blue-600" />
               {marketT.configuration.replace("{symbol}", activeSymbol)}
             </div>
          </div>
          <div className="card-p p-8">
            <MarketIndicatorScoreView
              availableIndicators={availableIndicators || []}
              loading={loading}
              symbol={activeSymbol}
            />
          </div>
        </div>

        {/* 📊 SIGNALS */}
        <div className="card bg-white dark:bg-[#0f172a] border-2 border-slate-100 dark:border-slate-800 rounded-3xl overflow-hidden shadow-sm">
           <div className="card-header border-b border-slate-100 dark:border-slate-800 p-6">
              <div className="card-title text-slate-900 dark:text-white flex items-center gap-3">
                <Activity size={16} className="text-blue-600" />
                {marketT.signals}
              </div>
           </div>
           <div className="card-p p-0">
              <DashboardErrorBoundary>
                <TechnicalTerminalGrid
                  title={marketT.signalMonitor.replace("{symbol}", activeSymbol)}
                  onRemoveIndicator={() => {}}
                  loading={loading}
                  symbol={activeSymbol}
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
                  {marketT.priceHistory.replace("{symbol}", activeSymbol)}
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
                  {marketT.forecast.replace("{symbol}", activeSymbol)}
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
           <span className="text-[10px] font-black text-slate-600 dark:text-slate-300 uppercase tracking-widest">{marketT.processing.replace("{symbol}", activeSymbol)}</span>
        </div>
      )}
    </div>
  );
}
