"use client";

import { useState, useEffect } from "react";
import { useModal } from "@/components/modal/ModalProvider";

import { 
  ClipboardList,
  PlusCircle,
  Activity,
  ShieldCheck,
  Zap,
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

export default function StrategyPage() {
  const { showSnackbar } = useModal();
  const { status, completeStep } = useOnboarding();

  const [search, setSearch] = useState("");
  const [refreshKey, setRefreshKey] = useState(0);
  const [editingStrategy, setEditingStrategy] = useState(null);

  const { setups, loadSetups } = useSetupData();
  const { strategies, loadStrategies } = useStrategyData();

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
      showSnackbar("Strategie verwijderen mislukt", "danger");
    }
  };

  const handleUpdateStrategy = async (id, data) => {
    try {
      await updateStrategy(id, data);
      showSnackbar("Strategie bijgewerkt", "success");
      setEditingStrategy(null);
      refreshEverything();
    } catch {
      showSnackbar("Strategie bijwerken mislukt", "danger");
    }
  };

  const handleStrategySubmit = async (strategy) => {
    try {
      const setup = safeSetups.find(
        (s) => String(s.id) === String(strategy.setup_id)
      );
      if (!setup) {
        showSnackbar("Geen geldige setup geselecteerd.", "danger");
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
      showSnackbar("Strategie opslaan mislukt.", "danger");
    }
  };

  return (
    <div className="page-container">
      <OnboardingBanner step="strategy" />

      {/* 🟢 STANDARD PAGE HEADER */}
      <header className="page-header">
        <div className="page-label">
           <Activity size={12} />
           Uitvoering
        </div>
        <h1 className="page-title">Strategieën</h1>
        <p className="page-subtitle">Vertaal je plannen naar acties en bewaar je discipline</p>
      </header>

      {/* 🚀 QUICK STATS GRID */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div className="card p-8 flex flex-col items-center justify-center text-center bg-gradient-to-br from-white to-slate-50/50">
            <div className="text-[10px] font-black text-slate-400 uppercase tracking-[0.25em] mb-4">Actieve plannen</div>
            <div className="text-5xl font-black text-blue-600 tracking-tighter tabular-nums">{safeStrategies.filter(s => s.is_active).length}</div>
        </div>
        <div className="card p-8 flex flex-col items-center justify-center text-center bg-gradient-to-br from-white to-slate-50/50">
            <div className="text-[10px] font-black text-slate-400 uppercase tracking-[0.25em] mb-4">Totaal</div>
            <div className="text-5xl font-black text-slate-900 tracking-tighter tabular-nums">{safeStrategies.length}</div>
        </div>
      </div>

      {/* 🧠 AGENT INSIGHTS */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8 items-stretch">
         <div className="lg:col-span-2">
            <AgentInsightPanel category="strategy" key={refreshKey} />
         </div>
         <div className="lg:col-span-1">
            <ActiveStrategyTodayCard />
         </div>
      </div>

      <div className="grid grid-cols-1 gap-12 pt-6">
        
        {/* 📋 STRATEGY LIST */}
        <section className="card">
          <div className="card-header">
             <div className="card-title">
               <ClipboardList size={16} className="text-blue-600" />
               Overzicht
             </div>
             
             <div className="flex items-center bg-slate-50 border border-slate-200 px-3 py-1.5 rounded-lg focus-within:ring-2 focus-within:ring-blue-600/10 transition-all">
                <input
                  type="text"
                  placeholder="Zoek plan..."
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  className="bg-transparent outline-none text-[11px] font-semibold w-full"
                />
             </div>
          </div>

          <div className="card-p p-0">
            <StrategyList
              strategies={safeStrategies}
              searchTerm={search}
              onRefresh={refreshEverything}
              onDelete={handleDeleteStrategy}
              onUpdate={handleUpdateStrategy}
              onEdit={setEditingStrategy}
              key={refreshKey}
            />
          </div>
        </section>

        {/* ➕ CREATE NEW STRATEGY */}
        <section className="card">
           <div className="card-header">
              <div className="card-title">
                <PlusCircle size={16} className="text-blue-600" />
                Nieuwe Strategie
              </div>
           </div>

           <div className="card-p">
             <p className="text-[11px] font-black text-slate-400 uppercase tracking-widest mb-6">Voeg een nieuw handelsplan toe</p>
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
        title={editingStrategy?.name || "Aanpassen"}
        subtitle="Instellingen"
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

      <footer className="flex items-center justify-center gap-6 pt-12 opacity-40 grayscale">
         <div className="flex items-center gap-2 text-[10px] font-black uppercase tracking-widest">
            <Zap size={14} /> Snelle uitvoering
         </div>
         <div className="flex items-center gap-2 text-[10px] font-black uppercase tracking-widest">
            <ShieldCheck size={14} /> Beveiligd
         </div>
      </footer>
    </div>
  );
}
