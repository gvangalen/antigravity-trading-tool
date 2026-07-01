"use client";

import { useState, useEffect } from "react";
import { useSearchParams } from "next/navigation";
import { useTranslation } from "@/app/providers/I18nProvider";

// 🔥 Onboarding
import OnboardingBanner from "@/components/onboarding/OnboardingBanner";
import OnboardingStepGuide from "@/components/onboarding/OnboardingStepGuide";
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
import { trackAssistantEvent } from "@/lib/api/assistantAnalytics";

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

import { useCurrentAsset } from "@/hooks/useCurrentAsset";

export default function MacroPage() {
  const [activeTab, setActiveTab] = useState("day");
  const { symbol: selectedAsset } = useCurrentAsset();
  const searchParams = useSearchParams();
  const { t } = useTranslation();
  const macroT = t.pages.macro;

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
  } = useMacroData(activeTab, selectedAsset);
  const macroNeedsSetup = status?.has_macro === false && activeMacroIndicatorNames?.length === 0;
  const onboardingGuidedMode = searchParams.get("onboarding") === "1";
  const showOnboardingGuide = onboardingGuidedMode || macroNeedsSetup;

  // ===============================
  // 📈 SCORE DATA
  // ===============================
  const { macro } = useScoresData(selectedAsset);
  const { openConfirm, showSnackbar } = useModal();

  useEffect(() => {
    trackAssistantEvent({
      event_name: "screen_view",
      page: "/macro",
      surface: "web",
      flow_type: "macro",
      asset: selectedAsset || null,
    });
  }, [selectedAsset]);

  // ===============================
  // 🔥 ONBOARDING TRIGGER
  // ===============================
  useEffect(() => {
    if (
      activeMacroIndicatorNames?.length > 0 &&
      status &&
      status.has_macro === false
    ) {
      completeStep("macro");
    }
  }, [activeMacroIndicatorNames, status, completeStep]);

  // ===============================
  // 🛡️ SAFE FALLBACK
  // ===============================
  const safeMacro = {
    score: macro?.score ?? null,
    trend: macro?.trend ?? macroT.unknown,
    bias: macro?.bias ?? macroT.neutral,
    risk: macro?.risk ?? macroT.unknown,
    summary:
      macro?.summary ??
      macroT.noInsights,
  };

  // ===============================
  // 📈 VIEW CHART
  // ===============================
  const handleViewChart = (name) => {
    const normalized = name.toLowerCase().replace(/ /g, "_");
    const symbol = SYMBOL_MAP[normalized] || "BINANCE:BTCUSDT";

    openConfirm({
      title: macroT.viewChartTitle.replace("{name}", name),
      statusLabel: macroT.readOnly,
      context: macroT.viewChartContext.replace("{name}", name),
      impact: macroT.viewChartImpact,
      safety: macroT.viewChartSafety,
      consequence: macroT.viewChartConsequence,
      description: (
        <div className="w-full h-[400px] mt-4">
          <TradingViewChart symbol={symbol} height={400} />
        </div>
      ),
      confirmText: macroT.close,
      cancelText: macroT.back,
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
      title: macroT.removeTitle,
      context: macroT.removeContext.replace("{name}", name).replace("{symbol}", selectedAsset),
      impact: macroT.removeImpact,
      safety: macroT.removeSafety,
      consequence: macroT.removeConsequence,
      confirmText: macroT.removeConfirm,
      cancelText: t.common.cancel,
      tone: "danger",
      onConfirm: async () => {
        const result = await removeMacroIndicator(name);

        if (result?.ok) {
          showSnackbar(macroT.removeSuccess.replace("{name}", name), "success");
          return;
        }

        if (result?.reason !== "missing_name") {
          console.error("❌ Removal failed:", result?.error);
          showSnackbar(macroT.removeError, "danger");
        }
      },
    });
  };

  // ===============================
  // 🧱 RENDER
  // ===============================
  return (
    <div className="page-container bg-white dark:bg-[#020617] transition-colors min-h-screen">
      <OnboardingBanner step="macro" />
      
      {/* 📡 STANDARD PAGE HEADER */}
      <header className="page-header border-l-4 border-blue-600 pl-8 mb-16">
        <div className="page-label text-[11px] font-black text-blue-600 dark:text-blue-500 uppercase tracking-[0.3em] mb-2 opacity-80 flex items-center gap-2">
           <Globe size={12} />
           {macroT.eyebrow}
        </div>
        <h1 className="page-title text-5xl font-black text-slate-900 dark:text-slate-100 tracking-tight leading-none mb-3">{macroT.title}</h1>
        <p className="page-subtitle text-[15px] font-medium text-slate-400 dark:text-slate-500 max-w-2xl leading-relaxed">
          {macroT.subtitle.replace("{symbol}", selectedAsset)}
        </p>
      </header>

      {showOnboardingGuide ? (
        <OnboardingStepGuide copy={macroT.onboardingGuide} anchorId="macro-config" guidedMode={onboardingGuidedMode} />
      ) : null}

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
           <span className="text-[10px] font-black text-slate-400 dark:text-slate-500 uppercase tracking-widest">{macroT.analysis}</span>
        </div>
        <DashboardErrorBoundary>
          <AgentInsightPanel category="macro" symbol={selectedAsset} />
        </DashboardErrorBoundary>
      </div>

      <div className="grid grid-cols-1 gap-12 pt-8 pb-24">
         {/* 🛠️ CONFIGURATION */}
         <div id="macro-config" className="space-y-4 scroll-mt-32">
            <div className="flex items-center gap-2 mb-2">
               <Activity size={14} className="text-slate-400 dark:text-slate-500" />
               <span className="text-[10px] font-black text-slate-400 dark:text-slate-500 uppercase tracking-widest">{macroT.configuration}</span>
            </div>
            {showOnboardingGuide ? (
              <div className="rounded-2xl border border-blue-100 bg-blue-50 px-4 py-3 text-sm font-semibold leading-relaxed text-slate-700">
                {macroT.onboardingGuide.guidedConfigHint}
              </div>
            ) : null}
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
                  <span className="text-[10px] font-black text-slate-400 dark:text-slate-500 uppercase tracking-widest">{macroT.signals}</span>
               </div>
               <div className="text-[9px] font-black text-slate-300 dark:text-slate-600 uppercase tracking-widest">{macroT.scrollOtherTimeframes}</div>
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

    </div>
  );
}
