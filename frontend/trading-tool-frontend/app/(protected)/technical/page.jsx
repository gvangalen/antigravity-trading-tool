"use client";

import { useState, useEffect } from "react";
import { Activity, Brain, LayoutGrid, AlertTriangle, LineChart } from "lucide-react";
import TradingViewChart from "@/components/charts/TradingViewChart";

import TechnicalTerminalHUD from "@/components/technical/TechnicalTerminalHUD";
import TechnicalTabs from "@/components/technical/TechnicalTabs";
import TechnicalTerminalGrid from "@/components/technical/TechnicalTerminalGrid";
import AgentInsightPanel from "@/components/agents/AgentInsightPanel";
import OnboardingBanner from "@/components/onboarding/OnboardingBanner";

import { useTechnicalData } from "@/hooks/useTechnicalData";
import { useScoresData } from "@/hooks/useScoresData";
import { useOnboarding } from "@/hooks/useOnboarding";
import { useModal } from "@/components/modal/ModalProvider";
import DashboardErrorBoundary from "@/components/ui/DashboardErrorBoundary";

import TechnicalIndicatorScoreView from "@/components/technical/TechnicalIndicatorScoreView";

const SYMBOL_MAP = {
  "vix": "TVC:VIX",
  "volatility_index_(vix)": "TVC:VIX",
  "rsi": "BINANCE:BTCUSDT",
  "ma_200": "BINANCE:BTCUSDT",
};

export default function TechnicalPage() {
  const [activeTab, setActiveTab] = useState("Dag");
  const { openConfirm, showSnackbar } = useModal();

  // ===============================
  // 🧭 ONBOARDING HOOK
  // ===============================
  const { status, completeStep } = useOnboarding();

  // ===============================
  // ⚙️ TECHNICAL DATA
  // ===============================
  const {
    technicalData,
    addTechnicalIndicator,
    removeTechnicalIndicator,
    loading: loadingIndicators,
    error,
  } = useTechnicalData(activeTab);

  const { technical: technicalScore } = useScoresData();

  // ===============================
  // 🔥 ONBOARDING TRIGGER
  // ===============================
  useEffect(() => {
    if (
      technicalData?.length > 0 &&
      status &&
      status.has_technical === false
    ) {
      console.log("🧭 Onboarding: technical step completed");
      completeStep("technical");
    }
  }, [technicalData, status, completeStep]);

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
  // 🗑️ DELETE WITH MODAL
  // ===============================
  const handleRemoveIndicator = (name) => {
    if (!name) return;

    openConfirm({
      title: "Disconnect",
      description: `Are you sure you want to disconnect '${name}' from your analysis?`,
      confirmText: "Disconnect",
      cancelText: "Cancel",
      tone: "danger",
      onConfirm: async () => {
        try {
          await removeTechnicalIndicator(name);
          showSnackbar(`'${name}' successfully disconnected`, "success");
        } catch (err) {
          console.error("❌ Disconnect failed:", err);
          showSnackbar("Error disconnecting", "danger");
        }
      },
    });
  };

  // ===============================
  // 🧱 RENDER
  // ===============================
  return (
    <div className="page-container bg-white dark:bg-[#020617] transition-colors min-h-screen">
      <OnboardingBanner step="technical" />

      {/* 🟢 STANDARD PAGE HEADER */}
      <header className="page-header border-l-4 border-blue-600 pl-8 mb-16">
        <div className="page-label text-[11px] font-black text-blue-600 dark:text-blue-500 uppercase tracking-[0.3em] mb-2 opacity-80 flex items-center gap-2">
           <Activity size={12} />
           System Status
        </div>
        <h1 className="page-title text-5xl font-black text-slate-900 dark:text-slate-100 tracking-tight leading-none mb-3">Technical</h1>
        <p className="page-subtitle text-[15px] font-medium text-slate-400 dark:text-slate-500 max-w-2xl leading-relaxed">
          Analysis of trends and technical indicators
        </p>
      </header>

      {/* 🚀 TECHNICAL HUD */}
      <DashboardErrorBoundary>
        <TechnicalTerminalHUD 
          score={technicalScore?.score} 
          bias={technicalScore?.bias} 
          trend={technicalScore?.trend} 
          loading={loadingIndicators || !technicalScore}
        />
      </DashboardErrorBoundary>

      {/* 🧠 ANALYSIS */}
      <div className="space-y-6 py-8">
        <div className="flex items-center gap-3 mb-2">
           <div className="w-6 h-0.5 bg-blue-600/20" />
           <span className="text-[10px] font-black text-slate-400 dark:text-slate-500 uppercase tracking-[0.2em] opacity-80">Analysis</span>
        </div>
        <DashboardErrorBoundary>
          <AgentInsightPanel category="technical" />
        </DashboardErrorBoundary>
      </div>

      <div className="space-y-12 pb-24">
         {/* 📊 INDICATORS TERMINAL (Main Focus) */}
         <div className="space-y-6">
            <div className="flex items-center justify-between px-2">
               <div className="flex items-center gap-3">
                  <LayoutGrid size={18} className="text-blue-600" />
                  <span className="text-[12px] font-black text-slate-900 dark:text-white uppercase tracking-widest">Indicator Dashboard</span>
               </div>
               <TechnicalTabs activeTab={activeTab} setActiveTab={setActiveTab} />
            </div>

            <DashboardErrorBoundary>
               <TechnicalTerminalGrid
                  data={technicalData}
                  loading={loadingIndicators}
                  error={error}
                  onRemove={handleRemoveIndicator}
                  onViewChart={handleViewChart}
               />
            </DashboardErrorBoundary>
         </div>

         {/* 🧱 CONFIGURATION & LOGIC ENGINE (Subordinate) */}
         <div className="pt-8 border-t border-slate-100 dark:border-slate-800">
            <div className="flex items-center gap-3 mb-8 px-2">
               <Brain size={18} className="text-slate-400" />
               <span className="text-[12px] font-black text-slate-400 dark:text-slate-500 uppercase tracking-widest">Logic Engine Configuration</span>
            </div>
            
            <TechnicalIndicatorScoreView
               addTechnicalIndicator={addTechnicalIndicator}
               activeTechnicalIndicatorNames={technicalData.map(i => i.name)}
            />
         </div>
      </div>

      {error && (
        <div className="fixed bottom-8 left-1/2 -translate-x-1/2 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-900/30 px-6 py-4 rounded-2xl shadow-xl flex items-center gap-4 text-red-700 dark:text-red-300 z-50 transition-colors">
           <AlertTriangle size={24} />
           <div>
              <div className="text-[11px] font-black uppercase tracking-widest">Error Message</div>
              <div className="text-sm font-medium">{error}</div>
           </div>
        </div>
      )}
    </div>
  );
}
