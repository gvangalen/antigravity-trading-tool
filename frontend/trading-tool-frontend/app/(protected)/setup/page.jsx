"use client";

import { useState, useEffect } from "react";
import { useModal } from "@/components/modal/ModalProvider";

import {
  Settings,
  Search,
  ClipboardList,
  PlusCircle,
} from "lucide-react";

import SetupForm from "@/components/setup/SetupForm";
import SetupList from "@/components/setup/SetupList";
import SetupMatchCard from "@/components/setup/SetupMatchCard";

import { useSetupData } from "@/hooks/useSetupData";
import { useOnboarding } from "@/hooks/useOnboarding";

// ⭐ Onboarding component
import OnboardingBanner from "@/components/onboarding/OnboardingBanner";
import AgentInsightPanel from "@/components/agents/AgentInsightPanel";

export default function SetupPage() {
  const [search, setSearch] = useState("");
  const { showSnackbar } = useModal();

  // ===============================
  // 🧭 ONBOARDING
  // ===============================
  const { status, completeStep } = useOnboarding();

  // ===============================
  // ⚙️ SETUP DATA
  // ===============================
  const {
    setups,
    loading,
    error,
    loadSetups,
    saveSetup,
    removeSetup,
  } = useSetupData();

  /* =====================================================
     INITIAL LOAD
  ===================================================== */
  useEffect(() => {
    loadSetups();
  }, []);

  /* =====================================================
     🔥 ONBOARDING TRIGGER
  ===================================================== */
  useEffect(() => {
    if (
      Array.isArray(setups) &&
      setups.length > 0 &&
      status &&
      status.has_setup === false
    ) {
      console.log("🧭 Onboarding: setup step completed");
      completeStep("setup");
    }
  }, [setups, status, completeStep]);

  /* =====================================================
     REFRESH
  ===================================================== */
  const reloadSetups = async () => {
    await loadSetups();
  };

  const safeSetups = Array.isArray(setups) ? setups : [];

  /* =====================================================
     RENDER
  ===================================================== */
  return (
    <div className="page-container">
      <OnboardingBanner step="setup" />

      {/* 🟢 STANDARD PAGE HEADER */}
      <header className="page-header">
        <div className="page-label">
           <Settings size={12} />
           Configuratie
        </div>
        <h1 className="page-title">Setups</h1>
        <p className="page-subtitle">Beheer je trading-strategieën en marktmodellen</p>
      </header>

      {/* 🧠 AI INSIGHT + SETUP MATCH */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 items-stretch">
        <AgentInsightPanel category="setup" />
        <SetupMatchCard />
      </div>

      <div className="grid grid-cols-1 gap-10">
        
        {/* 📋 SETUP LIST */}
        <div className="card">
          <div className="card-header">
            <div className="card-title">
              <ClipboardList className="text-blue-600" size={16} />
              <span>Huidige Setups</span>
            </div>
            
            <div className="flex items-center px-3 py-1.5 bg-slate-50 border border-slate-200 rounded-lg gap-2 focus-within:ring-2 focus-within:ring-blue-600/10 transition-all">
              <Search size={14} className="text-slate-400" />
              <input
                type="text"
                placeholder="Zoek setup..."
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                className="bg-transparent outline-none text-[11px] font-semibold w-32"
              />
            </div>
          </div>

          <div className="card-p p-0">
            <SetupList
              setups={safeSetups}
              loading={loading}
              error={error}
              searchTerm={search}
              saveSetup={saveSetup}
              removeSetup={removeSetup}
              reload={reloadSetups}
            />
          </div>
        </div>

        {/* ➕ NIEUWE SETUP */}
        <div className="card">
          <div className="card-header">
            <div className="card-title">
              <PlusCircle className="text-blue-600" size={16} />
              <span>Nieuwe Setup</span>
            </div>
          </div>
          <div className="card-p">
            <p className="text-[11px] font-black text-slate-400 uppercase tracking-widest mb-6">
              Voeg een nieuw handelsmodel toe
            </p>
            <SetupForm onSaved={reloadSetups} />
          </div>
        </div>

      </div>
    </div>
  );
}
