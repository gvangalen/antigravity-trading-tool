"use client";

import CardWrapper from "@/components/ui/CardWrapper";

// PRO Tables
import TechnicalTerminalGrid from "@/components/technical/TechnicalTerminalGrid";
import WeekTable from "@/components/ui/WeekTable";
import MonthTable from "@/components/ui/MonthTable";
import QuarterTable from "@/components/ui/QuarterTable";

const TABS = ["Dag", "Week", "Maand", "Kwartaal"];

export default function MacroTabs({
  activeTab,
  setActiveTab,
  macroData,
  loading,
  error,
  handleRemove,
  onViewChart,
}) {
  // Always guard macroData
  const safeData = Array.isArray(macroData) ? macroData : [];

  // ---------------------------------------------------------
  // 🔍 Table selector
  // ---------------------------------------------------------
  const renderTable = () => {
    if (loading) {
      return (
        <TechnicalTerminalGrid
          title="Macro Indicatoren"
          data={[]} 
          onRemove={() => {}} // veilige no-op functie
        />
      );
    }

    if (error) {
      console.error("MacroTabs error:", error);
    }

    switch (activeTab) {
      case "Dag":
        return (
          <TechnicalTerminalGrid
            title="Macro Indicatoren"
            data={safeData}
            onRemove={handleRemove} // enige tab met delete
            onViewChart={onViewChart}
          />
        );

      case "Week":
        return (
          <WeekTable
            title="Macro Indicatoren"
            data={safeData}
          />
        );

      case "Maand":
        return (
          <MonthTable
            title="Macro Indicatoren"
            data={safeData}
          />
        );

      case "Kwartaal":
        return (
          <QuarterTable
            title="Macro Indicatoren"
            data={safeData}
          />
        );

      default:
        return (
          <TechnicalTerminalGrid
            title="Macro Indicatoren"
            data={safeData}
            onRemove={handleRemove}
            onViewChart={onViewChart}
          />
        );
    }
  };

  // ---------------------------------------------------------
  // RENDER
  // ---------------------------------------------------------
  return (
    <div className="space-y-8">
      {/* 🔹 TABS: SEGMENTED CONTROL (Matching Technical Style) */}
      <div className="flex items-center gap-4">
         <div className="text-[10px] font-black text-secondary uppercase tracking-[0.2em] pl-1">Tijdsinterval</div>
         <div className="flex bg-[var(--color-border-subtle)] p-1 rounded-xl border border-slate-200">
            {TABS.map((tab) => (
               <button
                  key={tab}
                  onClick={() => setActiveTab(tab)}
                  className={`px-5 py-2 rounded-lg text-[10px] font-black uppercase tracking-widest transition-all ${
                     activeTab === tab
                        ? "bg-card text-foreground shadow-sm"
                        : "text-secondary hover:text-slate-600"
                  }`}
               >
                  {tab}
               </button>
            ))}
         </div>
      </div>

      <div className="animate-in fade-in slide-in-from-bottom-2 duration-700">
         {renderTable()}
      </div>
    </div>
  );
}
