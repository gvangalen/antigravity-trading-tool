"use client";

import { useEffect, useState } from "react";
import {
  BarChart3,
  LineChart,
} from "lucide-react";

import TradingViewChart from "@/components/charts/TradingViewChart";

// V2.1 Components
import CompactGauges from "@/components/dashboard/CompactGauges";
import TradingBrain from "@/components/dashboard/TradingBrain";
import TableTabs from "@/components/dashboard/TableTabs";
import DashboardErrorBoundary from "@/components/ui/DashboardErrorBoundary";

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

export default function DashboardPage() {
  const { t } = useTranslation();
  const { activeSetup, focusedBotId, setFocusedBotId } = useActiveSetup();
  const { configs: botConfigs } = useBotData();
  const {
    technicalData,
    removeTechnicalIndicator: handleRemove,
    loading: technicalLoading,
    error: technicalError,
    reload: technicalReload,
  } = useTechnicalData("Day");

  /* --------------------------------------------------------
     🔹 Afgeleide helpers (BELANGRIJK)
     GEFIXED: Altijd Array.isArray checken
  -------------------------------------------------------- */
  const activeTechnicalIndicatorNames = Array.isArray(technicalData) 
    ? technicalData.map((i) => i.name)
    : [];


  const { macroData, loading: macroLoading, error: macroError, reload: macroReload } =
    useMacroData();
  
   const { sevenDayData, btcLive, loading: marketLoading } = useMarketData();
 
   /* --------------------------------------------------------
     🔁 MAPPING & SYNC
  -------------------------------------------------------- */
  function mapSetupToTradingView(setup) {
    if (!setup) {
      return {
        symbol: "BINANCE:BTCUSDT",
        interval: "D",
      };
    }

    const symbolMap = {
      BTC: "BINANCE:BTCUSDT",
      ETH: "BINANCE:ETHUSDT",
    };

    const intervalMap = {
      "1W": "W",
      "1D": "D",
      "4H": "240",
      "1H": "60",
    };

    return {
      symbol: symbolMap[setup.symbol] ?? "BINANCE:BTCUSDT",
      interval: intervalMap[setup.timeframe] ?? "D",
    };
  }

  const tvConfig = mapSetupToTradingView(activeSetup);
  
  // 🔥 INDICATOR SYNC: Extract names and map to TV studies
  const activeIndicatorNames = Array.isArray(technicalData) 
    ? technicalData.map(i => i.name) 
    : [];
  const chartStudies = mapTechnicalToStudies(activeIndicatorNames);


  return (
    <div className="page-container bg-white dark:bg-[#020617] transition-colors min-h-screen">
      
      {/* 🟢 STANDARD PAGE HEADER */}
      <header className="page-header border-l-4 border-blue-600 pl-4 sm:pl-8 mb-8 sm:mb-16">
        <div className="page-label text-[10px] sm:text-[11px] font-black text-blue-600 dark:text-blue-500 uppercase tracking-[0.3em] mb-2 opacity-80 flex items-center gap-2">
           <BarChart3 size={12} />
           {t.dashboard.title}
        </div>
        <h1 className="page-title text-3xl sm:text-5xl font-black text-slate-900 dark:text-slate-100 tracking-tight leading-none mb-3 truncate">{t.dashboard.overview}</h1>
        <p className="page-subtitle text-sm sm:text-[15px] font-medium text-slate-400 dark:text-slate-500 max-w-2xl leading-relaxed">{t.dashboard.subtitle}</p>
      </header>

      {/* 🚀 QUICK STATS & GAUGES */}
      <div className="card bg-white dark:bg-[#0f172a] border-2 border-slate-100 dark:border-slate-800 rounded-2xl sm:rounded-3xl transition-all duration-300">
        <div className="card-p p-4 sm:p-10">
           <div className="flex items-center gap-4 mb-6 sm:mb-8">
              <div className="w-1.5 h-4 sm:h-6 bg-blue-600 rounded-full" />
              <span className="text-[10px] sm:text-[12px] font-black text-slate-900 dark:text-slate-100 uppercase tracking-widest">{t.dashboard.system_status}</span>
           </div>
           <DashboardErrorBoundary>
             <CompactGauges />
           </DashboardErrorBoundary>
        </div>
      </div>

      <div className="flex flex-col xl:flex-row gap-20 py-12">
        {/* 📈 MAIN: CHARTS & ANALYSIS */}
        <main className="flex-1 space-y-24">
          
          <div className="flex flex-col lg:flex-row gap-20">
             {/* LEFT: MARKET VIEW */}
             <div className="flex-1 space-y-6">
                <DashboardErrorBoundary>
                  <MarketLiveCard data={btcLive} loading={!btcLive} />
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
                  <TradingBrain />
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
                        btcLive={btcLive}
                        loading={marketLoading}
                      />
                    </div>
                 </div>
               }
               botsTable={
                 <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
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

        </main>
      </div>


    </div>
  );
}
