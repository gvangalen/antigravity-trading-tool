"use client";

import { useState, useEffect } from "react";
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
import DashboardErrorBoundary from "@/components/ui/DashboardErrorBoundary";
import { trackAssistantEvent } from "@/lib/api/assistantAnalytics";
import { useTranslation } from "@/app/providers/I18nProvider";

export default function SetupPage() {
  const [search, setSearch] = useState("");
  const { t } = useTranslation();
  const copy = t?.setupPage || {};

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

  useEffect(() => {
    trackAssistantEvent({
      event_name: "screen_view",
      page: "/setup",
      surface: "web",
      flow_type: "setup",
    });
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
    <div className="page-container bg-white dark:bg-[#020617] transition-colors min-h-screen">
      <OnboardingBanner step="setup" />

      {/* 🟢 STANDARD PAGE HEADER */}
      <header className="page-header border-l-4 border-blue-600 pl-8 mb-16">
        <div className="page-label text-[11px] font-black text-blue-600 dark:text-blue-500 uppercase tracking-[0.3em] mb-2 opacity-80 flex items-center gap-2">
           <Settings size={12} />
           {copy.eyebrow}
        </div>
        <h1 className="page-title text-5xl font-black text-slate-900 dark:text-slate-100 tracking-tight leading-none mb-3">{copy.title}</h1>
        <p className="page-subtitle text-[15px] font-medium text-slate-400 dark:text-slate-500 max-w-2xl leading-relaxed">
          {copy.subtitle}
        </p>
      </header>

      {/* 🧠 AI INSIGHT + SETUP MATCH */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 items-stretch py-8">
        <DashboardErrorBoundary>
          <AgentInsightPanel category="setup" />
        </DashboardErrorBoundary>
        <DashboardErrorBoundary>
          <SetupMatchCard />
        </DashboardErrorBoundary>
      </div>

      <div className="grid grid-cols-1 gap-10 pb-24">
        
        {/* 📋 SETUP LIST */}
        <div className="card bg-white dark:bg-[#0f172a] border-2 border-slate-100 dark:border-slate-800 rounded-3xl overflow-hidden shadow-sm">
          <div className="card-header border-b border-slate-100 dark:border-slate-800 p-6 flex items-center justify-between">
            <div className="card-title text-slate-900 dark:text-white flex items-center gap-3">
              <ClipboardList className="text-blue-600" size={16} />
              <span>{copy.activeTitle}</span>
            </div>
            
            <div className="flex items-center px-4 py-2 bg-slate-50 dark:bg-slate-950/50 border border-slate-200 dark:border-slate-800 rounded-xl gap-2 focus-within:ring-4 focus-within:ring-blue-600/5 transition-all">
              <Search size={14} className="text-slate-400 dark:text-slate-500" />
              <input
                type="text"
                placeholder={copy.searchPlaceholder}
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                className="bg-transparent outline-none text-[11px] font-bold text-slate-700 dark:text-slate-300 w-40"
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

        {/* ➕ NEW SETUP */}
        <div className="card bg-white dark:bg-[#0f172a] border-2 border-slate-100 dark:border-slate-800 rounded-3xl overflow-hidden shadow-sm">
          <div className="card-header border-b border-slate-100 dark:border-slate-800 p-6">
            <div className="card-title text-slate-900 dark:text-white flex items-center gap-3">
              <PlusCircle className="text-blue-600" size={16} />
              <span>{copy.newTitle}</span>
            </div>
          </div>
          <div className="card-p p-8">
            <p className="text-[11px] font-black text-slate-400 dark:text-slate-500 uppercase tracking-widest mb-6 border-b border-slate-50 dark:border-slate-800/50 pb-4">
              {copy.newDescription}
            </p>
            <SetupForm onSaved={reloadSetups} />
          </div>
        </div>

      </div>
    </div>
  );
}
