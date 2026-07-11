"use client";

import { useState, useEffect } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { Activity, Brain, LayoutGrid, AlertTriangle, LineChart } from "lucide-react";
import TradingViewChart from "@/components/charts/TradingViewChart";
import { useTranslation } from "@/app/providers/I18nProvider";

import TechnicalTerminalHUD from "@/components/technical/TechnicalTerminalHUD";
import TechnicalTabs from "@/components/technical/TechnicalTabs";
import TechnicalTerminalGrid from "@/components/technical/TechnicalTerminalGrid";
import AgentInsightPanel from "@/components/agents/AgentInsightPanel";
import OnboardingBanner from "@/components/onboarding/OnboardingBanner";
import OnboardingStepGuide from "@/components/onboarding/OnboardingStepGuide";

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
  const [activeTab, setActiveTab] = useState("day");
  const router = useRouter();
  const searchParams = useSearchParams();
  const { openConfirm, showSnackbar } = useModal();
  const { symbol: selectedAsset } = useCurrentAsset();
  const { t } = useTranslation();
  const technicalT = t.pages.technical;
  const guideCopy = technicalT.onboardingGuide
    ? {
        ...technicalT.onboardingGuide,
        title: technicalT.onboardingGuide.title?.replace("{symbol}", selectedAsset),
        body: technicalT.onboardingGuide.body?.replace("{symbol}", selectedAsset),
        guidedIntro: technicalT.onboardingGuide.guidedIntro?.replace("{symbol}", selectedAsset),
        guidedConfigHint: technicalT.onboardingGuide.guidedConfigHint?.replace("{symbol}", selectedAsset),
        completionHint: technicalT.onboardingGuide.completionHint?.replace("{symbol}", selectedAsset),
        completedTitle: technicalT.onboardingGuide.completedTitle?.replace("{symbol}", selectedAsset),
        completedBody: technicalT.onboardingGuide.completedBody?.replace("{symbol}", selectedAsset),
        finnHint: technicalT.onboardingGuide.finnHint?.replace("{symbol}", selectedAsset),
        steps: Array.isArray(technicalT.onboardingGuide.steps)
          ? technicalT.onboardingGuide.steps.map((step) => step.replace("{symbol}", selectedAsset))
          : [],
      }
    : null;
  const nextSetupHref = `/setup?onboarding=1&step=setup&symbol=${encodeURIComponent(selectedAsset)}`;

  // ===============================
  // ⚙️ TECHNICAL DATA
  // ===============================
  const {
    technicalData,
    addTechnicalIndicator,
    removeTechnicalIndicator,
    loading: loadingIndicators,
    error,
  } = useTechnicalData(activeTab, selectedAsset, { includeScoreSummary: false });

  const { technical: technicalScore } = useScoresData(selectedAsset, {
    includeHistory: false,
    includeMaster: false,
  });
  const { status, completeStep } = useOnboarding();
  const technicalStepComplete = Boolean(status?.has_technical || technicalData?.length > 0);
  const technicalNeedsSetup = status?.has_technical === false && technicalData?.length === 0;
  const onboardingGuidedMode = searchParams.get("onboarding") === "1";
  const showOnboardingGuide = onboardingGuidedMode || technicalNeedsSetup;

  useEffect(() => {
    if (!status || status.has_asset) return;
    router.replace("/onboarding/asset?onboarding=1&step=asset");
  }, [status, router]);

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
      title: technicalT.viewChartTitle.replace("{name}", name),
      statusLabel: technicalT.readOnly,
      context: technicalT.viewChartContext.replace("{name}", name),
      impact: technicalT.viewChartImpact,
      safety: technicalT.viewChartSafety,
      consequence: technicalT.viewChartConsequence,
      description: (
        <div className="w-full h-[400px] mt-4">
          <TradingViewChart symbol={symbol} height={400} />
        </div>
      ),
      confirmText: technicalT.close,
      cancelText: technicalT.back,
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
      title: technicalT.removeTitle,
      context: technicalT.removeContext.replace("{name}", name).replace("{symbol}", selectedAsset),
      impact: technicalT.removeImpact,
      safety: technicalT.removeSafety,
      consequence: technicalT.removeConsequence,
      confirmText: technicalT.removeConfirm,
      cancelText: t.common.cancel,
      tone: "danger",
      onConfirm: async () => {
        try {
          await removeTechnicalIndicator(name);
          showSnackbar(technicalT.removeSuccess.replace("{name}", name), "success");
        } catch (err) {
          console.error("❌ Disconnect failed:", err);
          showSnackbar(technicalT.removeError, "danger");
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
           {technicalT.eyebrow}
        </div>
        <h1 className="page-title text-5xl font-black text-slate-900 dark:text-slate-100 tracking-tight leading-none mb-3">{technicalT.title}</h1>
        <p className="page-subtitle text-[15px] font-medium text-slate-400 dark:text-slate-500 max-w-2xl leading-relaxed">
          {technicalT.subtitle.replace("{symbol}", selectedAsset)}
        </p>
      </header>

      {showOnboardingGuide ? (
        <OnboardingStepGuide
          copy={guideCopy}
          anchorId="technical-config"
          guidedMode={onboardingGuidedMode}
          isComplete={technicalStepComplete}
          nextHref={nextSetupHref}
        />
      ) : null}

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
           <span className="text-[10px] font-black text-slate-400 dark:text-slate-500 uppercase tracking-widest">{technicalT.analysis}</span>
        </div>
        <DashboardErrorBoundary>
          <AgentInsightPanel category="technical" symbol={selectedAsset} />
        </DashboardErrorBoundary>
      </div>

      <div className="grid grid-cols-1 gap-12 pt-8 pb-24">
         {/* 🛠️ CONFIGURATION */}
         <div id="technical-config" className="space-y-4 scroll-mt-32">
            <div className="flex items-center gap-2 mb-2">
               <Activity size={14} className="text-slate-400 dark:text-slate-500" />
               <span className="text-[10px] font-black text-slate-400 dark:text-slate-500 uppercase tracking-widest">{technicalT.configuration}</span>
            </div>
            {showOnboardingGuide ? (
              <div className="rounded-2xl border border-blue-100 bg-blue-50 px-4 py-3 text-sm font-semibold leading-relaxed text-slate-700">
                {guideCopy?.guidedConfigHint}
              </div>
            ) : null}
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
                  <span className="text-[10px] font-black text-slate-400 dark:text-slate-500 uppercase tracking-widest">{technicalT.signals}</span>
               </div>
               <div className="text-[9px] font-black text-slate-300 dark:text-slate-600 uppercase tracking-widest">{technicalT.scrollOtherTimeframes}</div>
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
              <div className="text-[11px] font-black uppercase tracking-widest">{technicalT.errorLabel}</div>
              <div className="text-sm font-medium">{error}</div>
           </div>
        </div>
      )}
    </div>
  );
}
