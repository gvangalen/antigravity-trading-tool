"use client";

import { useEffect, useState } from "react";
import {
  BarChart3,
  LineChart,
  Activity,
} from "lucide-react";

import TradingViewChart from "@/components/charts/TradingViewChart";

// V2.1 Components
import CompactGauges from "@/components/dashboard/CompactGauges";
import TradingBrain from "@/components/dashboard/TradingBrain";
import TableTabs from "@/components/dashboard/TableTabs";
import SystemConnectivity from "@/components/dashboard/SystemConnectivity";
import DashboardErrorBoundary from "@/components/ui/DashboardErrorBoundary";
import FINNIntelligenceFeed from "@/components/dashboard/FINNIntelligenceFeed";
import GlobalMarketDecisionCard from "@/components/dashboard/GlobalMarketDecisionCard";

// Table Components
import TechnicalDayTableForDashboard from "@/components/technical/TechnicalDayTableForDashboard";
import MacroSummaryTableForDashboard from "@/components/macro/MacroSummaryTableForDashboard";
import MarketSummaryForDashboard from "@/components/market/MarketSummaryForDashboard";
import MarketLiveCard from "@/components/market/MarketLiveCard";


import { useTechnicalData } from "@/hooks/useTechnicalData";
import { useMacroData } from "@/hooks/useMacroData";
import { useMarketData } from "@/hooks/useMarketData";

import { useTranslation } from "@/app/providers/I18nProvider";
import { useActiveSetup } from "@/app/providers/SetupProvider";
import { mapTechnicalToStudies } from "@/config/indicator_mapping";
import TradingViewSmartChart from "@/components/charts/TradingViewSmartChart";
import BotCard from "@/components/bot/BotCard";
import useBotData from "@/hooks/useBotData";

import ScoreHistoryChart from "@/components/dashboard/ScoreHistoryChart";

import { useCurrentAsset } from "@/hooks/useCurrentAsset";

export default function DashboardPage() {
  const { t } = useTranslation();
  const searchParams = typeof window !== 'undefined' ? new URLSearchParams(window.location.search) : null;
  const urlSymbol = searchParams?.get("symbol")?.toUpperCase();
  
  const { selectedAsset, setSelectedAsset } = require("@/app/providers/AssetProvider").useAsset();
  const { activeSetup, focusedBotId, setFocusedBotId } = useActiveSetup();
  const { configs: botConfigs } = useBotData();
  const { symbol: activeSymbol } = useCurrentAsset();

  // Sync URL param to global state if they differ
  useEffect(() => {
    if (urlSymbol && urlSymbol !== selectedAsset) {
      setSelectedAsset(urlSymbol);
    }
  }, [urlSymbol, selectedAsset, setSelectedAsset]);

  const {
    technicalData,
    removeTechnicalIndicator: handleRemove,
    loading: technicalLoading,
    error: technicalError,
    reload: technicalReload,
  } = useTechnicalData("Day", activeSymbol);

  /* --------------------------------------------------------
     🔹 Afgeleide helpers (BELANGRIJK)
     GEFIXED: Altijd Array.isArray checken
  -------------------------------------------------------- */
  const activeTechnicalIndicatorNames = Array.isArray(technicalData) 
    ? technicalData.map((i) => i.name)
    : [];


  const { macroData, loading: macroLoading, error: macroError, reload: macroReload } =
    useMacroData("Dag", activeSymbol);
  
   const { sevenDayData, btcLive: assetLive, loading: marketLoading } = useMarketData(activeSymbol);
 
   /* --------------------------------------------------------
     🔁 MAPPING & SYNC
   -------------------------------------------------------- */
  function mapSetupToTradingView(setup, globalSymbol) {
    // Priority: 1. Setup/Bot Symbol, 2. Global Selected Asset
    const targetSymbol = setup?.symbol || globalSymbol || "BTC";
    
    const intervalMap = {
      "1W": "W",
      "1D": "D",
      "4H": "240",
      "1H": "60",
    };

    return {
      symbol: `BINANCE:${targetSymbol}USDT`,
      interval: intervalMap[setup?.timeframe] ?? "D",
    };
  }

  const tvConfig = mapSetupToTradingView(activeSetup, activeSymbol);
  
  // 🔥 INDICATOR SYNC: Extract names and map to TV studies
  const activeIndicatorNames = Array.isArray(technicalData) 
    ? technicalData.map(i => i.name) 
    : [];
  const chartStudies = mapTechnicalToStudies(activeIndicatorNames);


  return (
    <div key={activeSymbol} className="page-container bg-white dark:bg-[#020617] transition-colors min-h-screen">
      
      {/* 🟢 STANDARD PAGE HEADER */}
      <header className="page-header border-l-4 border-blue-600 pl-4 sm:pl-8 mb-8 sm:mb-16">
        <div className="page-label text-[10px] sm:text-[11px] font-black text-blue-600 dark:text-blue-500 uppercase tracking-[0.3em] mb-2 opacity-80 flex items-center gap-2">
           <BarChart3 size={12} />
           {t.dashboard.title}
        </div>
          <div className="max-w-2xl">
            <h1 className="page-title text-3xl sm:text-5xl font-black text-slate-900 dark:text-slate-100 tracking-tight leading-none mb-3 truncate">{t.dashboard.overview}</h1>
            <p className="page-subtitle text-sm sm:text-[15px] font-medium text-slate-400 dark:text-slate-500 leading-relaxed">{t.dashboard.subtitle}</p>
          </div>
      </header>

      {/* 🚀 QUICK STATS & GAUGES */}
      <div className="card bg-white dark:bg-[#0f172a] border-2 border-slate-100 dark:border-slate-800 rounded-2xl sm:rounded-3xl transition-all duration-300">
        <div className="card-p p-4 sm:p-10">
           <DashboardErrorBoundary>
             <CompactGauges symbol={activeSymbol} />
           </DashboardErrorBoundary>
        </div>
      </div>

      {/* 🌐 GLOBAL MARKET TELEMETRY (STANDALONE TERMINAL INTELLIGENCE) */}
      <div className="mt-8">
        <DashboardErrorBoundary>
          <div className="card bg-white dark:bg-[#0f172a] border-2 border-slate-100 dark:border-slate-800 rounded-2xl sm:rounded-3xl transition-all duration-300 overflow-hidden shadow-sm">
            <div className="card-p p-6 sm:p-10">
              <GlobalMarketDecisionCard symbol={activeSymbol} />
            </div>
          </div>
        </DashboardErrorBoundary>
      </div>

      {/* 🔮 LIVE INTELLIGENCE TERMINAL (V3.0) */}
      <div className="mt-12">
        <DashboardErrorBoundary>
          <FINNIntelligenceFeed />
        </DashboardErrorBoundary>
      </div>

      <div className="flex flex-col xl:flex-row gap-20 py-12">
        {/* 📈 MAIN: CHARTS & ANALYSIS */}
        <main className="flex-1 space-y-24">
          
          <div className="flex flex-col lg:flex-row gap-20">
             {/* LEFT: MARKET VIEW */}
             <div className="flex-1 space-y-6">
                <DashboardErrorBoundary>
                   <MarketLiveCard symbol={activeSymbol} data={assetLive} loading={!assetLive} />
                </DashboardErrorBoundary>

                <div className="card bg-white dark:bg-[#0f172a] border-2 border-slate-100 dark:border-slate-800 rounded-2xl sm:rounded-3xl overflow-hidden">
                  <div className="card-header border-b border-slate-100 dark:border-slate-800 p-4 sm:p-6">
                    <div className="card-title text-slate-900 dark:text-white">
                      <LineChart size={16} className="text-blue-600" />
                      {t.dashboard.live_market}
                    </div>
                  </div>
                  <div className="card-p p-4 sm:p-8">
                    <DashboardErrorBoundary>
                      <TradingViewSmartChart
                        key={`${tvConfig.symbol}-${tvConfig.interval}-${chartStudies.join(',')}-${focusedBotId}`}
                        symbol={tvConfig.symbol}
                        interval={tvConfig.interval}
                        indicators={chartStudies}
                        focusedBotId={focusedBotId}
                        setFocusedBotId={setFocusedBotId}
                        theme="light"
                        height={typeof window !== 'undefined' && window.innerWidth < 640 ? 300 : 580}
                      />
                    </DashboardErrorBoundary>
                  </div>
                </div>
             </div>

             {/* RIGHT: THE BRAIN */}
             <div className="w-full lg:w-[340px] shrink-0">
                <DashboardErrorBoundary>
                   <TradingBrain symbol={activeSymbol} />
                </DashboardErrorBoundary>
             </div>
          </div>

          {/* 📑 BOTTOM: DEEP ANALYSIS TABS */}
          <DashboardErrorBoundary>
            <TableTabs 
               technicalTable={
                 <TechnicalDayTableForDashboard
                   data={technicalData}
                   loading={technicalLoading}
                   error={technicalError}
                   onRetry={technicalReload}
                   onRemove={handleRemove}
                 />
               }
               macroTable={
                 <MacroSummaryTableForDashboard
                   data={macroData}
                   loading={macroLoading}
                   error={macroError}
                   onRetry={macroReload}
                 />
               }
               marketTable={
                 <div className="card bg-white dark:bg-[#0f172a] border-2 border-slate-100 dark:border-slate-800 rounded-3xl overflow-hidden">
                    <div className="card-header border-b border-slate-100 dark:border-slate-800 p-6">
                      <h3 className="card-title text-slate-900 dark:text-white uppercase tracking-widest text-[12px] font-black">{t.dashboard.market_data}</h3>
                    </div>
                    <div className="card-p p-8">
                      <MarketSummaryForDashboard
                        sevenDayData={sevenDayData}
                        btcLive={assetLive}
                        loading={marketLoading}
                      />
                    </div>
                 </div>
               }
               botsTable={
                 <div className="grid grid-cols-1 lg:grid-cols-2 xl:grid-cols-3 gap-6">
                    {botConfigs.map(bot => (
                      <BotCard 
                        key={bot.id} 
                        bot={bot} 
                        showActions={false}
                        onSelect={(id) => setFocusedBotId(id)}
                      />
                    ))}
                 </div>
               }
            />
          </DashboardErrorBoundary>

          {/* 📊 ANALYTICS: SCORE HISTORY (Moved to bottom) */}
          <DashboardErrorBoundary>
             <ScoreHistoryChart symbol={activeSymbol} />
          </DashboardErrorBoundary>

        </main>
      </div>


    </div>
  );
}
