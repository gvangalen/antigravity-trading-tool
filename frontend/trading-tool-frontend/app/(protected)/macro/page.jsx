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

// Icons
import { Globe, Brain, Activity } from "lucide-react";

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
  const { macro, loading: loadingScore } = useScoresData();
  const { openConfirm, showSnackbar } = useModal();

  // ===============================
  // 🔥 ONBOARDING TRIGGER (DE ESSENTIËLE FIX)
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
    trend: macro?.trend ?? "Onbekend",
    bias: macro?.bias ?? "Neutraal",
    risk: macro?.risk ?? "Onbekend",
    summary:
      macro?.summary ??
      "Nog geen macro-inzichten beschikbaar. Voeg indicatoren toe of wacht op de eerste AI-run.",
  };

  // ===============================
  // 🎨 SCORE KLEUR
  // ===============================
  const getScoreColor = (score) => {
    const n = typeof score === "number" ? score : Number(score);
    if (isNaN(n)) return "text-[var(--text-light)]";

    if (n >= 80) return "score-strong-buy";
    if (n >= 60) return "score-buy";
    if (n >= 40) return "score-neutral";
    if (n >= 20) return "score-sell";
    return "score-strong-sell";
  };

  // ===============================
  // 📈 ADVIES
  // ===============================
  const adviesText =
    (safeMacro.score ?? 0) >= 75
      ? "Positief"
      : (safeMacro.score ?? 0) <= 25
      ? "Negatief"
      : "Neutraal";

  // ===============================
  // 🗑️ DELETE MET MODAL & SNACKBAR
  // ===============================
  const handleRemoveMacro = (name) => {
    if (!name) return;

    openConfirm({
      title: "Indicator verwijderen",
      description: `Weet je zeker dat je '${name}' wilt verwijderen uit je macro analyse?`,
      confirmText: "Verwijderen",
      cancelText: "Annuleren",
      tone: "danger",
      onConfirm: async () => {
        try {
          await removeMacroIndicator(name);
          showSnackbar(`'${name}' succesvol verwijderd`, "success");
        } catch (err) {
          console.error("❌ Verwijderen mislukt:", err);
          showSnackbar("Fout bij verwijderen", "danger");
        }
      },
    });
  };

  // ===============================
  // 🧱 RENDER
  // ===============================
  return (
    <div className="page-container">

      {/* 📡 STANDARD PAGE HEADER */}
      <header className="page-header">
        <div className="page-label">
           <Globe size={12} />
           Systeem-status
        </div>
        <h1 className="page-title">Macro Dashboard</h1>
        <p className="page-subtitle">Analyse van wereldwijde economische trends en marktomstandigheden</p>
      </header>

      <div className="space-y-12">
        {/* 🛰️ MACRO HUD */}
        <MacroTerminalHUD 
          score={safeMacro.score} 
          bias={safeMacro.bias} 
          trend={safeMacro.trend} 
          risk={safeMacro.risk} 
        />
      </div>

      {/* 🧠 ANALYSE */}
      <div className="space-y-4">
        <div className="flex items-center gap-2 mb-2">
           <Brain size={14} className="text-slate-400" />
           <span className="text-[10px] font-black text-slate-400 uppercase tracking-widest">Analyse</span>
        </div>
        <AgentInsightPanel category="macro" />
      </div>

      <div className="grid grid-cols-1 gap-12 pt-8">
         {/* 🛠️ MODULE 2: SEARCH & CONFIGURATION */}
         <div className="space-y-4">
            <div className="flex items-center gap-2 mb-2">
               <Activity size={14} className="text-slate-400" />
               <span className="text-[10px] font-black text-slate-400 uppercase tracking-widest">Instellingen</span>
            </div>
            <MacroIndicatorScoreView
               addMacroIndicator={addMacroIndicator}
               activeMacroIndicatorNames={activeMacroIndicatorNames}
            />
         </div>

         {/* 📊 MODULE 3: GRID TERMINAL (TABS) */}
         <div className="space-y-4">
            <div className="flex items-center justify-between mb-2">
               <div className="flex items-center gap-2">
                  <Activity size={14} className="text-slate-400" />
                  <span className="text-[10px] font-black text-slate-400 uppercase tracking-widest">Signalen</span>
               </div>
               <div className="text-[9px] font-black text-slate-300 uppercase tracking-widest">Scroll voor andere periodes</div>
            </div>
            <MacroTabs
               activeTab={activeTab}
               setActiveTab={setActiveTab}
               macroData={macroData}
               loading={loadingIndicators}
               error={error}
               handleRemove={handleRemoveMacro}
            />
         </div>
      </div>

      <OnboardingBanner step="macro" />
    </div>
  );
}
