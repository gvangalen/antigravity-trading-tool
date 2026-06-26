"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import {
  BarChart3,
  LineChart,
  Loader2,
} from "lucide-react";

// V2.1 Components
import CompactGauges from "@/components/dashboard/CompactGauges";
import TradingBrain from "@/components/dashboard/TradingBrain";
import TableTabs from "@/components/dashboard/TableTabs";
import DashboardErrorBoundary from "@/components/ui/DashboardErrorBoundary";
import GlobalMarketDecisionCard from "@/components/dashboard/GlobalMarketDecisionCard";

// Table Components
import TechnicalDayTableForDashboard from "@/components/technical/TechnicalDayTableForDashboard";
import MacroSummaryTableForDashboard from "@/components/macro/MacroSummaryTableForDashboard";
import MarketSummaryForDashboard from "@/components/market/MarketSummaryForDashboard";
import MarketLiveCard from "@/components/market/MarketLiveCard";


import { useTechnicalData } from "@/hooks/useTechnicalData";
import { useMacroData } from "@/hooks/useMacroData";
import { useMarketData } from "@/hooks/useMarketData";
import { useScoresData } from "@/hooks/useScoresData";
import { useOverviewSnapshot } from "@/hooks/useOverviewSnapshot";

import { useTranslation } from "@/app/providers/I18nProvider";
import { useActiveSetup } from "@/app/providers/SetupProvider";
import TradingViewSmartChart from "@/components/charts/TradingViewSmartChart";
import BotCard from "@/components/bot/BotCard";
import { fetchBotConfigs } from "@/lib/api/botApi";

import ScoreHistoryChart from "@/components/dashboard/ScoreHistoryChart";

import { useCurrentAsset } from "@/hooks/useCurrentAsset";
import { trackAssistantEvent } from "@/lib/api/assistantAnalytics";

export default function DashboardPage() {
  const { t } = useTranslation();
  const searchParams = typeof window !== 'undefined' ? new URLSearchParams(window.location.search) : null;
  const urlSymbol = searchParams?.get("symbol")?.toUpperCase();
  
  const { selectedAsset, setSelectedAsset } = require("@/app/providers/AssetProvider").useAsset();
  const { activeSetup, focusedBotId, setFocusedBotId } = useActiveSetup();
  const { symbol: activeSymbol } = useCurrentAsset({ includeFocusedBotLookup: false });
  const [showSecondaryPanels, setShowSecondaryPanels] = useState(false);
  const [showTelemetryPanel, setShowTelemetryPanel] = useState(false);
  const [showDeepAnalysis, setShowDeepAnalysis] = useState(false);
  const [showScoreHistory, setShowScoreHistory] = useState(false);
  const [showPrimaryChart, setShowPrimaryChart] = useState(false);
  const loadStartedAtRef = useRef(Date.now());
  const shellReadyLoggedRef = useRef(null);
  const primaryCardsLoggedRef = useRef(null);
  const chartReadyLoggedRef = useRef(null);
  const deepAnalysisLoggedRef = useRef(null);

  useEffect(() => {
    trackAssistantEvent({
      event_name: "screen_view",
      page: "/dashboard",
      surface: "web",
      flow_type: "dashboard",
      asset: activeSymbol || null,
    });
  }, [activeSymbol]);

  // Sync URL param to global state if they differ
  useEffect(() => {
    if (urlSymbol && urlSymbol !== selectedAsset) {
      setSelectedAsset(urlSymbol);
    }
  }, [urlSymbol, selectedAsset, setSelectedAsset]);

  useEffect(() => {
    loadStartedAtRef.current = performance.now();
    shellReadyLoggedRef.current = null;
    primaryCardsLoggedRef.current = null;
    chartReadyLoggedRef.current = null;
    deepAnalysisLoggedRef.current = null;
    setShowSecondaryPanels(false);
    setShowTelemetryPanel(false);
    setShowDeepAnalysis(false);
    setShowScoreHistory(false);
    setShowPrimaryChart(false);

    const secondaryTimer = window.setTimeout(() => setShowSecondaryPanels(true), 650);
    const telemetryTimer = window.setTimeout(() => setShowTelemetryPanel(true), 1600);
    const chartTimer = window.setTimeout(() => setShowPrimaryChart(true), 900);
    const analysisTimer = window.setTimeout(() => setShowDeepAnalysis(true), 2800);
    return () => {
      window.clearTimeout(secondaryTimer);
      window.clearTimeout(telemetryTimer);
      window.clearTimeout(chartTimer);
      window.clearTimeout(analysisTimer);
    };
  }, [activeSymbol]);

  const { snapshot: marketSnapshot, loading: marketSnapshotLoading } = useOverviewSnapshot(activeSymbol);
  const scoreSnapshot = useScoresData(activeSymbol, { includeHistory: false });
  const intelligenceSnapshot = useMemo(
    () => ({
      data: marketSnapshot?.intelligence ?? null,
      loading: marketSnapshotLoading && !marketSnapshot?.intelligence,
    }),
    [marketSnapshot, marketSnapshotLoading]
  );

  useEffect(() => {
    if (shellReadyLoggedRef.current === activeSymbol) return;
    shellReadyLoggedRef.current = activeSymbol;
    void trackAssistantEvent({
      event_name: "overview_shell_ready",
      page: "/dashboard",
      surface: "web",
      flow_type: "dashboard",
      asset: activeSymbol || null,
      duration_ms: Math.round(performance.now() - loadStartedAtRef.current),
    });
  }, [activeSymbol]);

  useEffect(() => {
    if (
      !marketSnapshot?.live ||
      !scoreSnapshot?.master ||
      primaryCardsLoggedRef.current === activeSymbol
    ) {
      return;
    }

    primaryCardsLoggedRef.current = activeSymbol;
    void trackAssistantEvent({
      event_name: "overview_primary_cards_ready",
      page: "/dashboard",
      surface: "web",
      flow_type: "dashboard",
      asset: activeSymbol || null,
      duration_ms: Math.round(performance.now() - loadStartedAtRef.current),
    });
  }, [activeSymbol, marketSnapshot?.live, scoreSnapshot?.master]);

  useEffect(() => {
    if (!showPrimaryChart || chartReadyLoggedRef.current === activeSymbol) return;
    chartReadyLoggedRef.current = activeSymbol;
    void trackAssistantEvent({
      event_name: "overview_chart_ready",
      page: "/dashboard",
      surface: "web",
      flow_type: "dashboard",
      asset: activeSymbol || null,
      duration_ms: Math.round(performance.now() - loadStartedAtRef.current),
    });
  }, [activeSymbol, showPrimaryChart]);

  useEffect(() => {
    if (!showDeepAnalysis || deepAnalysisLoggedRef.current === activeSymbol) return;
    deepAnalysisLoggedRef.current = activeSymbol;
    void trackAssistantEvent({
      event_name: "overview_deep_analysis_ready",
      page: "/dashboard",
      surface: "web",
      flow_type: "dashboard",
      asset: activeSymbol || null,
      duration_ms: Math.round(performance.now() - loadStartedAtRef.current),
    });
  }, [activeSymbol, showDeepAnalysis]);
 
   /* --------------------------------------------------------
     🔁 MAPPING & SYNC
   -------------------------------------------------------- */
  function mapSetupToTradingView(setup, globalSymbol) {
    // Priority: 1. Global Active Symbol (already resolves URL/bot/setup/global), 2. Setup Symbol
    const targetSymbol = globalSymbol || setup?.symbol || "BTC";
    
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
             <CompactGauges symbol={activeSymbol} snapshot={scoreSnapshot} />
           </DashboardErrorBoundary>
        </div>
      </div>

      {/* 🌐 GLOBAL MARKET TELEMETRY (STANDALONE TERMINAL INTELLIGENCE) */}
      <div className="mt-8">
        <DashboardErrorBoundary>
          <div className="card bg-white dark:bg-[#0f172a] border-2 border-slate-100 dark:border-slate-800 rounded-2xl sm:rounded-3xl transition-all duration-300 overflow-hidden shadow-sm">
            <div className="card-p p-6 sm:p-10">
              {showTelemetryPanel ? (
                <GlobalMarketDecisionCard symbol={activeSymbol} snapshot={intelligenceSnapshot} />
              ) : (
                <DeferredPanelPlaceholder title={t.dashboard.placeholders.terminalIntelligence} lines={3} />
              )}
            </div>
          </div>
        </DashboardErrorBoundary>
      </div>

      <div className="flex flex-col xl:flex-row gap-20 py-12">
        {/* 📈 MAIN: CHARTS & ANALYSIS */}
        <main className="flex-1 space-y-24">
          
          <div className="flex flex-col lg:flex-row gap-20">
             {/* LEFT: MARKET VIEW */}
             <div className="flex-1 space-y-6">
                <DashboardErrorBoundary>
                   <MarketLiveCard
                     symbol={activeSymbol}
                     data={marketSnapshot?.live ?? null}
                     loading={Boolean(marketSnapshot?.liveLoading) && !showSecondaryPanels}
                   />
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
                      {showPrimaryChart ? (
                        <TradingViewSmartChart
                          key={`${tvConfig.symbol}-${tvConfig.interval}-${focusedBotId}`}
                          symbol={tvConfig.symbol}
                          interval={tvConfig.interval}
                          indicators={[]}
                          focusedBotId={focusedBotId}
                          setFocusedBotId={setFocusedBotId}
                          theme="light"
                          height={typeof window !== 'undefined' && window.innerWidth < 640 ? 300 : 580}
                        />
                      ) : (
                        <DeferredPanelPlaceholder title={t.dashboard.placeholders.chartPreparing} lines={5} />
                      )}
                    </DashboardErrorBoundary>
                  </div>
                </div>
             </div>

             {/* RIGHT: THE BRAIN */}
             <div className="w-full lg:w-[340px] shrink-0">
                {showSecondaryPanels ? (
                  <DashboardErrorBoundary>
                     <TradingBrain symbol={activeSymbol} scoresSnapshot={scoreSnapshot} />
                  </DashboardErrorBoundary>
                ) : (
                  <DeferredPanelPlaceholder title={t.dashboard.placeholders.brainLoading} lines={4} />
                )}
             </div>
          </div>

          {/* 📑 BOTTOM: DEEP ANALYSIS TABS */}
          {showDeepAnalysis ? (
            <DeferredDashboardAnalysis
              activeSymbol={activeSymbol}
              marketSnapshot={marketSnapshot}
              focusedBotId={focusedBotId}
              setFocusedBotId={setFocusedBotId}
            />
          ) : (
            <DeferredPanelPlaceholder title={t.dashboard.placeholders.deepAnalysisLoading} lines={6} />
          )}

          {/* 📊 ANALYTICS: SCORE HISTORY (Moved to bottom) */}
          <ScoreHistorySection
            symbol={activeSymbol}
            isLoaded={showScoreHistory}
            onLoad={() => setShowScoreHistory(true)}
          />

        </main>
      </div>


    </div>
  );
}

function DeferredDashboardAnalysis({
  activeSymbol,
  marketSnapshot,
  focusedBotId,
  setFocusedBotId,
}) {
  const [activeAnalysisTab, setActiveAnalysisTab] = useState("technical");
  return (
    <>
      <DashboardErrorBoundary>
        <TableTabs 
          onActiveTabChange={setActiveAnalysisTab}
          technicalTable={() => (
            <DeferredTechnicalPanel
              symbol={activeSymbol}
              isActive={activeAnalysisTab === "technical"}
            />
          )}
          macroTable={() => (
            <DeferredMacroPanel
              symbol={activeSymbol}
              isActive={activeAnalysisTab === "macro"}
            />
          )}
          marketTable={() => (
            <DeferredMarketAnalysisPanel
              symbol={activeSymbol}
              snapshot={marketSnapshot}
              isActive={activeAnalysisTab === "market"}
            />
          )}
          botsTable={() => (
            <DeferredBotsPanel
              isActive={activeAnalysisTab === "bots"}
              onSelectBot={setFocusedBotId}
            />
          )}
        />
      </DashboardErrorBoundary>

    </>
  );
}

function DeferredTechnicalPanel({ symbol, isActive }) {
  const { t } = useTranslation();
  if (!isActive) {
    return <DeferredPanelPlaceholder title={t.dashboard.placeholders.technicalDeferred} lines={3} />;
  }

  return <ActiveTechnicalPanel symbol={symbol} />;
}

function ActiveTechnicalPanel({ symbol }) {
  const {
    technicalData,
    removeTechnicalIndicator: handleRemove,
    loading: technicalLoading,
    error: technicalError,
    reload: technicalReload,
  } = useTechnicalData("Day", symbol, { includeScoreSummary: false });

  return (
    <TechnicalDayTableForDashboard
      data={technicalData}
      loading={technicalLoading}
      error={technicalError}
      onRetry={technicalReload}
      onRemove={handleRemove}
    />
  );
}

function DeferredMacroPanel({ symbol, isActive }) {
  const { t } = useTranslation();
  if (!isActive) {
    return <DeferredPanelPlaceholder title={t.dashboard.placeholders.macroDeferred} lines={3} />;
  }

  return <ActiveMacroPanel symbol={symbol} />;
}

function ActiveMacroPanel({ symbol }) {
  const { macroData, loading: macroLoading, error: macroError, reload: macroReload } =
    useMacroData("Dag", symbol);

  return (
    <MacroSummaryTableForDashboard
      data={macroData}
      loading={macroLoading}
      error={macroError}
      onRetry={macroReload}
    />
  );
}

function DeferredPanelPlaceholder({ title, lines = 4 }) {
  return (
    <div className="card bg-white dark:bg-[#0f172a] border-2 border-slate-100 dark:border-slate-800 rounded-2xl sm:rounded-3xl overflow-hidden">
      <div className="card-p p-6 sm:p-8">
        <div className="text-[11px] font-black uppercase tracking-[0.2em] text-secondary mb-4">
          {title}
        </div>
        <div className="space-y-3 animate-pulse">
          {Array.from({ length: lines }).map((_, idx) => (
            <div key={idx} className="h-4 rounded-full bg-slate-100 dark:bg-slate-800" />
          ))}
        </div>
      </div>
    </div>
  );
}

function DeferredMarketAnalysisPanel({ symbol, snapshot, isActive }) {
  const { t } = useTranslation();
  const { sevenDayData, loading } = useMarketData(symbol, {
    includeExtendedData: isActive,
    includeSevenDayData: isActive,
    includeForwardData: false,
    includeDailyScores: false,
    includeMarketDayData: false,
    includeIndicators: false,
  });

  if (!isActive) {
    return (
      <div className="card bg-white dark:bg-[#0f172a] border-2 border-slate-100 dark:border-slate-800 rounded-3xl overflow-hidden">
        <div className="card-header border-b border-slate-100 dark:border-slate-800 p-6">
          <h3 className="card-title text-slate-900 dark:text-white uppercase tracking-widest text-[12px] font-black">
            {t.dashboard.market_data}
          </h3>
        </div>
        <div className="card-p p-8">
          <DeferredPanelPlaceholder title={t.dashboard.placeholders.marketDeferred} lines={3} />
        </div>
      </div>
    );
  }

  return (
    <div className="card bg-white dark:bg-[#0f172a] border-2 border-slate-100 dark:border-slate-800 rounded-3xl overflow-hidden">
      <div className="card-header border-b border-slate-100 dark:border-slate-800 p-6">
        <h3 className="card-title text-slate-900 dark:text-white uppercase tracking-widest text-[12px] font-black">
          {t.dashboard.market_data}
        </h3>
      </div>
      <div className="card-p p-8">
        <MarketSummaryForDashboard
          sevenDayData={sevenDayData}
          btcLive={snapshot?.live}
          loading={loading}
        />
      </div>
    </div>
  );
}

function DeferredBotsPanel({ isActive, onSelectBot }) {
  const { t } = useTranslation();
  const [bots, setBots] = useState([]);
  const [loading, setLoading] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!isActive || loaded) return;

    let cancelled = false;

    async function loadBots() {
      setLoading(true);
      setError("");
      try {
        const data = await fetchBotConfigs();
        if (!cancelled) {
          setBots(Array.isArray(data) ? data : []);
          setLoaded(true);
        }
      } catch (err) {
        if (!cancelled) {
          console.error("❌ bots tab load error:", err);
          setError("Kon bots niet laden.");
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    void loadBots();

    return () => {
      cancelled = true;
    };
  }, [isActive, loaded]);

  if (!isActive) {
    return <DeferredPanelPlaceholder title={t.dashboard.placeholders.botsDeferred} lines={3} />;
  }

  if (loading && !loaded) {
    return <DeferredPanelPlaceholder title={t.dashboard.placeholders.botsLoading} lines={4} />;
  }

  if (error) {
    return (
      <div className="card bg-white dark:bg-[#0f172a] border-2 border-slate-100 dark:border-slate-800 rounded-2xl sm:rounded-3xl overflow-hidden">
        <div className="card-p p-6 sm:p-8">
          <p className="text-sm font-semibold text-rose-600">{error}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 xl:grid-cols-3 gap-6">
      {bots.map((bot) => (
        <BotCard
          key={bot.id}
          bot={bot}
          showActions={false}
          onSelect={(id) => onSelectBot(id)}
        />
      ))}
    </div>
  );
}

function ScoreHistorySection({ symbol, isLoaded, onLoad }) {
  const { t } = useTranslation();
  if (isLoaded) {
    return (
      <DashboardErrorBoundary>
        <ScoreHistoryChart symbol={symbol} />
      </DashboardErrorBoundary>
    );
  }

  return (
    <div className="card bg-white dark:bg-[#0f172a] border-2 border-slate-100 dark:border-slate-800 rounded-2xl sm:rounded-3xl overflow-hidden">
      <div className="card-p p-6 sm:p-8 space-y-5">
        <div className="text-[11px] font-black uppercase tracking-[0.2em] text-secondary">
          {t.dashboard.scoreHistory.title}
        </div>
        <p className="text-sm sm:text-base text-slate-600 dark:text-slate-300 max-w-2xl">
          {t.dashboard.scoreHistory.description}
        </p>
        <button
          type="button"
          onClick={onLoad}
          className="inline-flex items-center gap-2 rounded-2xl bg-blue-600 px-5 py-3 text-[11px] font-black uppercase tracking-[0.18em] text-white transition hover:bg-blue-700 active:scale-[0.98]"
        >
          <Loader2 size={14} className="animate-spin" />
          {t.dashboard.scoreHistory.load}
        </button>
      </div>
    </div>
  );
}
