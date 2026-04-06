"use client";

import { useEffect, useState } from "react";
import {
  BarChart3,
  LineChart,
  ChevronsUp,
} from "lucide-react";

import TradingViewChart from "@/components/charts/TradingViewChart";

// V2.1 Components
import CompactGauges from "@/components/dashboard/CompactGauges";
import TradingBrain from "@/components/dashboard/TradingBrain";
import TableTabs from "@/components/dashboard/TableTabs";
import CardWrapper from "@/components/ui/CardWrapper";

// Table Components
import TechnicalDayTableForDashboard from "@/components/technical/TechnicalDayTableForDashboard";
import MacroSummaryTableForDashboard from "@/components/macro/MacroSummaryTableForDashboard";
import MarketSummaryForDashboard from "@/components/market/MarketSummaryForDashboard";
import MarketLiveCard from "@/components/market/MarketLiveCard";


import { useTechnicalData } from "@/hooks/useTechnicalData";
import { useMacroData } from "@/hooks/useMacroData";
import { useMarketData } from "@/hooks/useMarketData";

import { useActiveSetup } from "@/app/providers/SetupProvider";

export default function DashboardPage() {
  const [showScroll, setShowScroll] = useState(false);
  const { activeSetup } = useActiveSetup();

  /* --------------------------------------------------------
     📊 GEGEVENS
  -------------------------------------------------------- */
  const {
    technicalData,
    removeTechnicalIndicator: handleRemove,
    loading: technicalLoading,
    error: technicalError,
    reload: technicalReload,
  } = useTechnicalData("Dag");

  const { macroData, loading: macroLoading, error: macroError, reload: macroReload } =
    useMacroData();

  const { sevenDayData, btcLive } = useMarketData();



  /* --------------------------------------------------------
     🔁 MAPPING
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

  /* --------------------------------------------------------
     ⬆️ Scroll-to-top
  -------------------------------------------------------- */
  useEffect(() => {
    const handler = () => setShowScroll(window.scrollY > 300);
    window.addEventListener("scroll", handler);
    return () => window.removeEventListener("scroll", handler);
  }, []);

  const scrollToTop = () =>
    window.scrollTo({ top: 0, behavior: "smooth" });

  return (
    <div className="page-container">
      
      {/* 🟢 STANDARD PAGE HEADER */}
      <header className="page-header">
        <div className="page-label">
           <BarChart3 size={12} />
           Dashboard
        </div>
        <h1 className="page-title">Overzicht</h1>
        <p className="page-subtitle">Data-analyse & Marktsentiment</p>
      </header>

      {/* 🚀 QUICK STATS & GAUGES */}
      <div className="card">
        <div className="card-p">
           <div className="flex items-center gap-4 mb-8">
              <div className="w-1.5 h-6 bg-blue-600 rounded-full" />
              <span className="text-[12px] font-black text-slate-900 uppercase tracking-widest">Systeemstatus</span>
           </div>
           <CompactGauges />
        </div>
      </div>

      <div className="flex flex-col xl:flex-row gap-20">
        {/* 📈 MAIN: CHARTS & ANALYSIS */}
        <main className="flex-1 space-y-24">
          
          <div className="flex flex-col lg:flex-row gap-20">
             {/* LEFT: MARKET VIEW */}
             <div className="flex-1 space-y-6">
                <MarketLiveCard data={btcLive} loading={!btcLive} />

                <div className="card">
                  <div className="card-header">
                    <div className="card-title">
                      <LineChart size={16} className="text-blue-600" />
                      Markt
                    </div>
                  </div>
                  <div className="card-p">
                    <TradingViewChart
                      key={`${tvConfig.symbol}-${tvConfig.interval}`}
                      symbol={tvConfig.symbol}
                      interval={tvConfig.interval}
                      theme="light"
                      height={580}
                    />
                  </div>
                </div>
             </div>

             {/* RIGHT: THE BRAIN */}
             <div className="w-full lg:w-[340px] shrink-0">
                <TradingBrain />
             </div>
          </div>

          {/* 📑 BOTTOM: DEEP ANALYSIS TABS */}
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
               <div className="card">
                  <div className="card-header">
                    <h3 className="card-title">Markt Gegevens</h3>
                  </div>
                  <div className="card-p">
                    <MarketSummaryForDashboard
                      sevenDayData={sevenDayData}
                      btcLive={btcLive}
                    />
                  </div>
               </div>
             }
          />

        </main>
      </div>


      {showScroll && (
        <button
          onClick={scrollToTop}
          className="fixed bottom-6 right-6 bg-blue-600 text-white p-3 rounded-full shadow-lg hover:bg-blue-700 transition-all z-50"
        >
          <ChevronsUp className="w-5 h-5" />
        </button>
      )}
    </div>
  );
}
