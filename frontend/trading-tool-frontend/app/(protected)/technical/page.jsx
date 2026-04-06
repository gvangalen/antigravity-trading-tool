"use client";

import { useState, useEffect } from "react";
import { Activity, Brain, LayoutGrid, AlertTriangle } from "lucide-react";

import TechnicalTerminalHUD from "@/components/technical/TechnicalTerminalHUD";
import TechnicalTabs from "@/components/technical/TechnicalTabs";
import TechnicalTerminalGrid from "@/components/technical/TechnicalTerminalGrid";
import AgentInsightPanel from "@/components/agents/AgentInsightPanel";
import OnboardingBanner from "@/components/onboarding/OnboardingBanner";

import { useTechnicalData } from "@/hooks/useTechnicalData";
import { useScoresData } from "@/hooks/useScoresData";
import { useOnboarding } from "@/hooks/useOnboarding";
import { useModal } from "@/components/modal/ModalProvider";

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
    removeTechnicalIndicator,
    loading: loadingIndicators,
    error,
  } = useTechnicalData(activeTab);

  const { technical: technicalScore, loading: scoreLoading } = useScoresData();

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
  // 🗑️ DELETE MET MODAL
  // ===============================
  const handleRemoveIndicator = (name) => {
    if (!name) return;

    openConfirm({
      title: "Ontkoppelen",
      description: `Weet je zeker dat je '${name}' wilt ontkoppelen van je analyse?`,
      confirmText: "Ontkoppelen",
      cancelText: "Annuleren",
      tone: "danger",
      onConfirm: async () => {
        try {
          await removeTechnicalIndicator(name);
          showSnackbar(`'${name}' succesvol ontkoppeld`, "success");
        } catch (err) {
          console.error("❌ Ontkoppelen mislukt:", err);
          showSnackbar("Fout bij ontkoppelen", "danger");
        }
      },
    });
  };

  // ===============================
  // 🧱 RENDER
  // ===============================
  return (
    <div className="page-container">
      <OnboardingBanner step="technical" />

      {/* 🟢 STANDARD PAGE HEADER */}
      <header className="page-header">
        <div className="page-label">
           <Activity size={12} />
           Systeem-status
        </div>
        <h1 className="page-title">Techniek</h1>
        <p className="page-subtitle">Analyse van trends en technische indicatoren</p>
      </header>

      {/* 🚀 TECHNICAL HUD */}
      <TechnicalTerminalHUD 
        score={technicalScore?.score} 
        bias={technicalScore?.bias} 
        trend={technicalScore?.trend} 
      />

      {/* 🧠 ANALYSE */}
      <div className="space-y-6">
        <div className="flex items-center gap-3 mb-2">
           <div className="w-6 h-0.5 bg-blue-600/20" />
           <span className="text-[10px] font-black text-slate-400 uppercase tracking-[0.2em] opacity-80">Analyse</span>
        </div>
        <AgentInsightPanel category="technical" />
      </div>

      <div className="grid grid-cols-1 gap-16 pt-12">
         {/* 📊 INDICATOREN & TAB TERMINAL */}
         <div className="card">
            <div className="card-header">
              <div className="card-title">
                <LayoutGrid size={16} className="text-blue-600" />
                Indicatoren
              </div>
            </div>
            <div className="card-p">
              <TechnicalTabs activeTab={activeTab} setActiveTab={setActiveTab} />
            </div>
            <div className="border-t border-slate-100">
              <TechnicalTerminalGrid
                data={technicalData}
                loading={loadingIndicators}
                error={error}
                onRemoveIndicator={handleRemoveIndicator}
              />
            </div>
         </div>
      </div>

      {error && (
        <div className="fixed bottom-8 left-1/2 -translate-x-1/2 bg-red-50 border border-red-200 px-6 py-4 rounded-2xl shadow-xl flex items-center gap-4 text-red-700 z-50">
           <AlertTriangle size={24} />
           <div>
              <div className="text-[11px] font-black uppercase tracking-widest">Foutmelding</div>
              <div className="text-sm font-medium">{error}</div>
           </div>
        </div>
      )}
    </div>
  );
}
