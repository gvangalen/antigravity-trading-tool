"use client";

import { useState, useEffect } from "react";

// 🔥 Onboarding
import OnboardingBanner from "@/components/onboarding/OnboardingBanner";
import { useOnboarding } from "@/hooks/useOnboarding";

// Hooks
import { useMacroData } from "@/hooks/useMacroData";
import { useScoresData } from "@/hooks/useScoresData";

// Components
import MacroTabs from "@/components/macro/MacroTabs";
import MacroIndicatorScoreView from "@/components/macro/MacroIndicatorScoreView";
import MacroTerminalHUD from "@/components/macro/MacroTerminalHUD";
import AgentInsightPanel from "@/components/agents/AgentInsightPanel";
import { useModal } from "@/components/modal/ModalProvider";
import DashboardErrorBoundary from "@/components/ui/DashboardErrorBoundary";

// Icons
import { Globe, Brain, Activity, LineChart } from "lucide-react";
import TradingViewChart from "@/components/charts/TradingViewChart";

const SYMBOL_MAP = {
  // Technicals (shared/fallback)
  "vix": "TVC:VIX",
  "volatility_index_(vix)": "TVC:VIX",
  "rsi": "BINANCE:BTCUSDT",
  "ma_200": "BINANCE:BTCUSDT",
  "fear_&_greed_index": "GLOBAL:INDEX",
  "fear_greed_index": "GLOBAL:INDEX",
  
  // Macro - Widget-Friendly Symbols (Bypasses "Only on TradingView" restrictions)
  "gold_price": "CAPITALCOM:GOLD",
  "us10y": "TVC:US10Y",
  "us02y": "TVC:US02Y",
  "sp500": "CAPITALCOM:US500",
  "oil_price": "CAPITALCOM:UKOUSD",
  "dxy": "CAPITALCOM:DXY",
  "inflation_rate": "ECONOMICS:USCPI",
  "interest_rate": "ECONOMICS:USINTR",
  
  // Fallbacks/Legacy
  "gold": "OANDA:XAUUSD",
  "s&p_500": "CAPITALCOM:US500",
  "nasdaq": "CAPITALCOM:US100",
  "us_dollar_index": "CAPITALCOM:DXY",
  "oil": "OANDA:UK100GBP",
  "wti_oil": "CAPITALCOM:USOIL",
  "cpi": "ECONOMICS:USCPI",
  "m2_money_supply": "FED:M2SL",
  "btc_dominance": "CRYPTOCAP:BTC.D"
};

export default function MacroPage() {
  const [activeTab, setActiveTab] = useState("Dag");

  // ===============================
  // 🧭 ONBOARDING HOOK
  // ===============================
  const {
    status,
    completeStep,
  } = useOnboarding();

  // ===============================
  // 📊 MACRO DATA
  // ===============================
  const {
    macroData,
    addMacroIndicator,
    removeMacroIndicator,
    activeMacroIndicatorNames,
    loading: loadingIndicators,
    error,
  } = useMacroData(activeTab);

  // ===============================
  // 📈 SCORE DATA
  // ===============================
  const { macro } = useScoresData();
  const { openConfirm, showSnackbar } = useModal();

  // ===============================
  // 🔥 ONBOARDING TRIGGER
  // ===============================
  useEffect(() => {
    if (
      activeMacroIndicatorNames?.length > 0 &&
      status &&
      status.has_macro === false
    ) {
      console.log("🧭 Onboarding: macro step completed");
      completeStep("macro");
    }
  }, [activeMacroIndicatorNames, status, completeStep]);

  // ===============================
  // 🛡️ SAFE FALLBACK
  // ===============================
  const safeMacro = {
    score: macro?.score ?? null,
    trend: macro?.trend ?? "Unknown",
    bias: macro?.bias ?? "Neutral",
    risk: macro?.risk ?? "Unknown",
    summary:
      macro?.summary ??
      "No macro insights available. Add indicators or wait for the first AI analysis.",
  };

  // ===============================
  // 📈 VIEW CHART
  // ===============================
  const handleViewChart = (name) => {
    const normalized = name.toLowerCase().replace(/ /g, "_");
    const symbol = SYMBOL_MAP[normalized] || "BINANCE:BTCUSDT";

    openConfirm({
      title: `Live Chart: ${name}`,
      description: (
        <div className="w-full h-[400px] mt-4">
          <TradingViewChart symbol={symbol} height={400} />
        </div>
      ),
      confirmText: "Close",
      icon: <LineChart className="w-5 h-5 text-blue-500" />,
      tone: "info"
    });
  };

  // ===============================
  // 🗑️ DELETE WITH MODAL & SNACKBAR
  // ===============================
  const handleRemoveMacro = (name) => {
    if (!name) return;

    openConfirm({
      title: "Remove Indicator",
      description: `Are you sure you want to remove '${name}' from your macro analysis?`,
      confirmText: "Delete",
      cancelText: "Cancel",
      tone: "danger",
      onConfirm: async () => {
        try {
          await removeMacroIndicator(name);
          showSnackbar(`'${name}' successfully removed`, "success");
        } catch (err) {
          console.error("❌ Removal failed:", err);
          showSnackbar("Error removing indicator", "danger");
        }
      },
    });
  };

  // ===============================
  // 🧱 RENDER
  // ===============================
  return (
    <div className="page-container bg-white dark:bg-[#020617] transition-colors min-h-screen">
      
      {/* 📡 STANDARD PAGE HEADER */}
      <header className="page-header border-l-4 border-blue-600 pl-8 mb-16">
        <div className="page-label text-[11px] font-black text-blue-600 dark:text-blue-500 uppercase tracking-[0.3em] mb-2 opacity-80 flex items-center gap-2">
           <Globe size={12} />
           System Status
        </div>
        <h1 className="page-title text-5xl font-black text-slate-900 dark:text-slate-100 tracking-tight leading-none mb-3">Macro Dashboard</h1>
        <p className="page-subtitle text-[15px] font-medium text-slate-400 dark:text-slate-500 max-w-2xl leading-relaxed">
          Analysis of global economic trends and market conditions
        </p>
      </header>

      <div className="space-y-12">
        {/* 🛰️ MACRO HUD */}
        <DashboardErrorBoundary>
          <MacroTerminalHUD 
            score={safeMacro.score} 
            bias={safeMacro.bias} 
            trend={safeMacro.trend} 
            risk={safeMacro.risk} 
            loading={loadingIndicators || !macro}
          />
        </DashboardErrorBoundary>
      </div>

      {/* 🧠 ANALYSIS */}
      <div className="space-y-4 py-8">
        <div className="flex items-center gap-2 mb-2">
           <Brain size={14} className="text-slate-400 dark:text-slate-500" />
           <span className="text-[10px] font-black text-slate-400 dark:text-slate-500 uppercase tracking-widest">Analysis</span>
        </div>
        <DashboardErrorBoundary>
          <AgentInsightPanel category="macro" />
        </DashboardErrorBoundary>
      </div>

      <div className="grid grid-cols-1 gap-12 pt-8 pb-24">
         {/* 🛠️ CONFIGURATION */}
         <div className="space-y-4">
            <div className="flex items-center gap-2 mb-2">
               <Activity size={14} className="text-slate-400 dark:text-slate-500" />
               <span className="text-[10px] font-black text-slate-400 dark:text-slate-500 uppercase tracking-widest">Configuration</span>
            </div>
            <MacroIndicatorScoreView
               addMacroIndicator={addMacroIndicator}
               activeMacroIndicatorNames={activeMacroIndicatorNames}
            />
         </div>

         {/* 📊 SIGNALS */}
         <div className="space-y-4">
            <div className="flex items-center justify-between mb-2">
               <div className="flex items-center gap-2">
                  <Activity size={14} className="text-slate-400 dark:text-slate-500" />
                  <span className="text-[10px] font-black text-slate-400 dark:text-slate-500 uppercase tracking-widest">Signals</span>
               </div>
               <div className="text-[9px] font-black text-slate-300 dark:text-slate-600 uppercase tracking-widest">Scroll for other timeframes</div>
            </div>
            <DashboardErrorBoundary>
              <MacroTabs
                 activeTab={activeTab}
                 setActiveTab={setActiveTab}
                 macroData={macroData}
                 loading={loadingIndicators}
                 error={error}
                 handleRemove={handleRemoveMacro}
                 onViewChart={handleViewChart}
              />
            </DashboardErrorBoundary>
         </div>
      </div>

      <OnboardingBanner step="macro" />
    </div>
  );
}
