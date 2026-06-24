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
import { trackAssistantEvent } from "@/lib/api/assistantAnalytics";

import TechnicalIndicatorScoreView from "@/components/technical/TechnicalIndicatorScoreView";

const SYMBOL_MAP = {
  "vix": "TVC:VIX",
  "volatility_index_(vix)": "TVC:VIX",
  "rsi": "BINANCE:BTCUSDT",
  "ma_200": "BINANCE:BTCUSDT",
};

import { useCurrentAsset } from "@/hooks/useCurrentAsset";

export default function TechnicalPage() {
  const [activeTab, setActiveTab] = useState("Dag");
  const { openConfirm, showSnackbar } = useModal();
  const { symbol: selectedAsset } = useCurrentAsset();

  // ===============================
  // ⚙️ TECHNICAL DATA
  // ===============================
  const {
    technicalData,
    addTechnicalIndicator,
    removeTechnicalIndicator,
    loading: loadingIndicators,
    error,
  } = useTechnicalData(activeTab, selectedAsset);

  const { technical: technicalScore } = useScoresData(selectedAsset);
  const { status, completeStep } = useOnboarding();

  useEffect(() => {
    trackAssistantEvent({
      event_name: "screen_view",
      page: "/technical",
      surface: "web",
      flow_type: "technical",
      asset: selectedAsset || null,
    });
  }, [selectedAsset]);

  // ===============================
  // 🔥 ONBOARDING TRIGGER
  // ===============================
  useEffect(() => {
    if (
      technicalData?.length > 0 &&
      status &&
      status.has_technical === false
    ) {
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
      title: `Bekijk chart: ${name}`,
      statusLabel: "Alleen lezen",
      context: `Je bekijkt de live chart van ${name} binnen Technical.`,
      impact: "Er verandert niets aan je indicatoren of analyse. Dit opent alleen een visuele controlelaag.",
      safety: "Veilig om te gebruiken tijdens review. Er worden geen datafeeds aangepast.",
      consequence: "Na sluiten keer je terug naar je huidige technical context.",
      description: (
        <div className="w-full h-[400px] mt-4">
          <TradingViewChart symbol={symbol} height={400} />
        </div>
      ),
      confirmText: "Sluiten",
      cancelText: "Terug",
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
      title: "Indicator loskoppelen",
      context: `Je verwijdert ${name} uit je technische analyse voor ${selectedAsset}.`,
      impact: "Deze indicator telt niet meer mee in je technische overzicht en bijbehorende conclusies.",
      safety: "Dit verandert geen marktdata of trades. Alleen je analyse-opbouw wordt bijgewerkt.",
      consequence: "Na bevestigen wordt de pagina vernieuwd met de aangepaste indicatorenset.",
      confirmText: "Koppel los",
      cancelText: "Annuleren",
      tone: "danger",
      onConfirm: async () => {
        try {
          await removeTechnicalIndicator(name);
          showSnackbar(`'${name}' losgekoppeld`, "success");
        } catch (err) {
          console.error("❌ Disconnect failed:", err);
          showSnackbar("Loskoppelen mislukt", "danger");
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
           Marktcontext
        </div>
        <h1 className="page-title text-5xl font-black text-slate-900 dark:text-slate-100 tracking-tight leading-none mb-3">Technisch overzicht</h1>
        <p className="page-subtitle text-[15px] font-medium text-slate-400 dark:text-slate-500 max-w-2xl leading-relaxed">
          Analyse van trends en technische indicatoren voor {selectedAsset}
        </p>
      </header>

      {/* 🚀 TECHNICAL HUD */}
      <div className="space-y-12">
        <DashboardErrorBoundary>
          <TechnicalTerminalHUD 
            score={technicalScore?.score} 
            bias={technicalScore?.bias} 
            trend={technicalScore?.trend} 
            risk={technicalScore?.risk} 
            loading={loadingIndicators || !technicalScore}
          />
        </DashboardErrorBoundary>
      </div>
 
      {/* 🧠 ANALYSIS */}
      <div className="space-y-4 py-8">
        <div className="flex items-center gap-2 mb-2">
           <Brain size={14} className="text-slate-400 dark:text-slate-500" />
           <span className="text-[10px] font-black text-slate-400 dark:text-slate-500 uppercase tracking-widest">Analyse</span>
        </div>
        <DashboardErrorBoundary>
          <AgentInsightPanel category="technical" symbol={selectedAsset} />
        </DashboardErrorBoundary>
      </div>
 
      <div className="grid grid-cols-1 gap-12 pt-8 pb-24">
         {/* 🛠️ CONFIGURATION */}
         <div className="space-y-4">
            <div className="flex items-center gap-2 mb-2">
               <Activity size={14} className="text-slate-400 dark:text-slate-500" />
               <span className="text-[10px] font-black text-slate-400 dark:text-slate-500 uppercase tracking-widest">Configuratie</span>
            </div>
            <TechnicalIndicatorScoreView
               addTechnicalIndicator={addTechnicalIndicator}
               activeTechnicalIndicatorNames={technicalData.map(i => i.name)}
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
              <TechnicalTabs 
                activeTab={activeTab} 
                setActiveTab={setActiveTab} 
                technicalData={technicalData}
                loading={loadingIndicators}
                error={error}
                handleRemove={handleRemoveIndicator}
              />
            </DashboardErrorBoundary>
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
