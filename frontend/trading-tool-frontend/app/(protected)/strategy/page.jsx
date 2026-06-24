"use client";

import { useState, useEffect } from "react";
import { useModal } from "@/components/modal/ModalProvider";

import { 
  ClipboardList,
  PlusCircle,
  Activity,
  ShieldCheck,
  Zap,
  Search,
} from "lucide-react";

import StrategyList from "@/components/strategy/StrategyList";
import StrategyForm from "@/components/strategy/StrategyForm";
import ActiveStrategyTodayCard from "@/components/strategy/ActiveStrategyTodayCard";

import { useSetupData } from "@/hooks/useSetupData";
import { useStrategyData } from "@/hooks/useStrategyData";
import { useOnboarding } from "@/hooks/useOnboarding";

import {
  createStrategy,
  updateStrategy,
  deleteStrategy,
} from "@/lib/api/strategy";

import AgentInsightPanel from "@/components/agents/AgentInsightPanel";
import OnboardingBanner from "@/components/onboarding/OnboardingBanner";
import Drawer from "@/components/ui/Drawer";
import DashboardErrorBoundary from "@/components/ui/DashboardErrorBoundary";

export default function StrategyPage() {
  const { showSnackbar } = useModal();
  const { status, completeStep } = useOnboarding();

  const [search, setSearch] = useState("");
  const [refreshKey, setRefreshKey] = useState(0);
  const [editingStrategy, setEditingStrategy] = useState(null);

  const { setups, loadSetups, loading: setupsLoading } = useSetupData();
  const { strategies, loadStrategies, loading: strategyLoading } = useStrategyData();

  const safeSetups = Array.isArray(setups) ? setups : [];
  const safeStrategies = Array.isArray(strategies) ? strategies : [];

  useEffect(() => {
    loadSetups();
    loadStrategies();
  }, []);

  useEffect(() => {
    if (safeStrategies.length > 0 && status && status.has_strategy === false) {
      completeStep("strategy");
    }
  }, [safeStrategies, status, completeStep]);

  const refreshEverything = () => {
    loadStrategies();
    loadSetups();
    setTimeout(() => setRefreshKey((k) => k + 1), 30);
  };

  const handleDeleteStrategy = async (id) => {
    try {
      await deleteStrategy(id);
      showSnackbar("Strategie verwijderd", "success");
      refreshEverything();
    } catch {
      showSnackbar("Verwijderen van de strategie mislukt", "danger");
    }
  };

  const handleUpdateStrategy = async (id, data) => {
    try {
      await updateStrategy(id, data);
      showSnackbar("Strategie bijgewerkt", "success");
      setEditingStrategy(null);
      refreshEverything();
    } catch {
      showSnackbar("Bijwerken van de strategie mislukt", "danger");
    }
  };

  const handleStrategySubmit = async (strategy) => {
    try {
      const setup = safeSetups.find(
        (s) => String(s.id) === String(strategy.setup_id)
      );
      if (!setup) {
        showSnackbar("Kies eerst een geldige setup", "danger");
        return;
      }
      await createStrategy({
        ...strategy,
        setup_id: setup.id,
        setup_type: setup.setup_type,
      });
      showSnackbar("Strategie opgeslagen ✔", "success");
      refreshEverything();
    } catch {
      showSnackbar("Opslaan van de strategie mislukt", "danger");
    }
  };

  return (
    <div className="page-container bg-white dark:bg-[#020617] transition-colors min-h-screen">
      <OnboardingBanner step="strategy" />

      {/* 🟢 STANDARD PAGE HEADER */}
      <header className="page-header border-l-4 border-blue-600 pl-8 mb-16">
        <div className="page-label text-[11px] font-black text-blue-600 dark:text-blue-500 uppercase tracking-[0.3em] mb-2 opacity-80 flex items-center gap-2">
           <Activity size={12} />
           Uitvoering
        </div>
        <h1 className="page-title text-5xl font-black text-slate-900 dark:text-slate-100 tracking-tight leading-none mb-3">Strategieën</h1>
        <p className="page-subtitle text-[15px] font-medium text-slate-400 dark:text-slate-500 max-w-2xl leading-relaxed">
          Zet je setups om in duidelijke uitvoering en houd je handelsdiscipline strak.
        </p>
      </header>

      {/* 🚀 QUICK STATS GRID */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6 py-8">
        <div className="card p-8 flex flex-col items-center justify-center text-center bg-white dark:bg-[#0f172a] border-2 border-slate-100 dark:border-slate-800 rounded-3xl shadow-sm transition-all">
            <div className="text-[10px] font-black text-slate-400 dark:text-slate-500 uppercase tracking-[0.25em] mb-4">Actieve plannen</div>
            <div className="text-5xl font-black text-blue-600 dark:text-blue-400 tracking-tighter tabular-nums">
              {safeStrategies.filter(s => s.is_active).length}
            </div>
        </div>
        <div className="card p-8 flex flex-col items-center justify-center text-center bg-white dark:bg-[#0f172a] border-2 border-slate-100 dark:border-slate-800 rounded-3xl shadow-sm transition-all">
            <div className="text-[10px] font-black text-slate-400 dark:text-slate-500 uppercase tracking-[0.25em] mb-4">Totaal</div>
            <div className="text-5xl font-black text-slate-900 dark:text-slate-100 tracking-tighter tabular-nums">
              {safeStrategies.length}
            </div>
        </div>
      </div>

      {/* 🧠 AGENT INSIGHTS */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8 items-stretch pt-4">
         <div className="lg:col-span-2">
            <DashboardErrorBoundary>
               <AgentInsightPanel category="strategy" key={refreshKey} />
            </DashboardErrorBoundary>
         </div>
         <div className="lg:col-span-1">
            <DashboardErrorBoundary>
               <ActiveStrategyTodayCard />
            </DashboardErrorBoundary>
         </div>
      </div>

      <div className="grid grid-cols-1 gap-12 pt-12 pb-24">
        
        {/* 📋 STRATEGY LIST */}
        <section className="card bg-white dark:bg-[#0f172a] border-2 border-slate-100 dark:border-slate-800 rounded-3xl overflow-hidden shadow-sm">
          <div className="card-header border-b border-slate-100 dark:border-slate-800 p-6 flex items-center justify-between">
             <div className="card-title text-slate-900 dark:text-white flex items-center gap-3">
               <ClipboardList size={16} className="text-blue-600" />
               Overzicht
             </div>
             
             <div className="flex items-center bg-slate-50 dark:bg-slate-950/50 border border-slate-200 dark:border-slate-800 px-4 py-2 rounded-xl focus-within:ring-4 focus-within:ring-blue-600/5 transition-all">
                <Search size={14} className="text-slate-400 dark:text-slate-500 mr-2" />
                <input
                  type="text"
                  placeholder="Zoek strategieën..."
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  className="bg-transparent outline-none text-[11px] font-bold text-slate-700 dark:text-slate-300 w-40"
                />
             </div>
          </div>

          <div className="card-p p-0">
            <DashboardErrorBoundary>
              <StrategyList
                strategies={safeStrategies}
                searchTerm={search}
                onRefresh={refreshEverything}
                onDelete={handleDeleteStrategy}
                onUpdate={handleUpdateStrategy}
                onEdit={setEditingStrategy}
                loading={strategyLoading}
                key={refreshKey}
              />
            </DashboardErrorBoundary>
          </div>
        </section>

        {/* ➕ CREATE NEW STRATEGY */}
        <section className="card bg-white dark:bg-[#0f172a] border-2 border-slate-100 dark:border-slate-800 rounded-3xl overflow-hidden shadow-sm">
           <div className="card-header border-b border-slate-100 dark:border-slate-800 p-6">
              <div className="card-title text-slate-900 dark:text-white flex items-center gap-3">
                <PlusCircle size={16} className="text-blue-600" />
                Nieuwe strategie
              </div>
           </div>

           <div className="card-p p-8">
             <p className="text-[11px] font-black text-slate-400 dark:text-slate-500 uppercase tracking-widest mb-6 border-b border-slate-50 dark:border-slate-800/50 pb-4">
               Voeg een nieuwe strategie toe die past bij je setup en uitvoeringsstijl
             </p>
             <StrategyForm
               key={refreshKey}
               onSubmit={handleStrategySubmit}
               setups={safeSetups}
             />
           </div>
        </section>
      </div>

      {/* 🛸 STRATEGY TUNING DRAWER */}
      <Drawer
        isOpen={!!editingStrategy}
        onClose={() => setEditingStrategy(null)}
        title={editingStrategy?.name || "Strategie aanpassen"}
        subtitle="Configuratie"
      >
        {editingStrategy && (
          <StrategyForm
            strategy={editingStrategy}
            setups={safeSetups}
            onSubmit={(data) => handleUpdateStrategy(editingStrategy.id, data)}
            isEdit
          />
        )}
      </Drawer>

      <footer className="flex items-center justify-center gap-12 py-16 border-t border-slate-100 dark:border-slate-800 opacity-60">
         <div className="flex items-center gap-3 text-[10px] font-black uppercase tracking-[0.2em] text-slate-400 dark:text-slate-500">
            <Zap size={14} className="text-blue-500" /> Snelle uitvoering
         </div>
         <div className="flex items-center gap-3 text-[10px] font-black uppercase tracking-[0.2em] text-slate-400 dark:text-slate-500">
            <ShieldCheck size={14} className="text-blue-600" /> Beveiligd systeem
         </div>
      </footer>
    </div>
  );
}
