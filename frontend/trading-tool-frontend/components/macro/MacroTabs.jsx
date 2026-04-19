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
      {/* 🛠️ TERMINAL CONTROL CONSOLE */}
      <div className="flex items-center justify-between bg-[var(--color-border-subtle)] border border-slate-200 p-2 rounded-2xl max-w-2xl">
         <div className="flex items-center gap-1 w-full">
            {TABS.map((tab) => (
               <button
                  key={tab}
                  onClick={() => setActiveTab(tab)}
                  className={`
                     flex-1 px-4 py-2 text-[10px] font-black uppercase tracking-[0.2em] rounded-xl transition-all duration-300
                     ${activeTab === tab 
                        ? "bg-card text-[var(--primary)] shadow-sm border border-slate-200 translate-y-[-1px]" 
                        : "text-secondary hover:text-slate-600 hover:bg-slate-100/50"
                     }
                  `}
               >
                  {tab === "Dag" ? "Session_Live" : tab.toUpperCase()}
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
