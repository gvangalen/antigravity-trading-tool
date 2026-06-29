"use client";

import CardWrapper from "@/components/ui/CardWrapper";
import { useTranslation } from "@/app/providers/I18nProvider";

// PRO Tables
import TechnicalTerminalGrid from "@/components/technical/TechnicalTerminalGrid";
import WeekTable from "@/components/ui/WeekTable";
import MonthTable from "@/components/ui/MonthTable";
import QuarterTable from "@/components/ui/QuarterTable";

export default function MacroTabs({
  activeTab,
  setActiveTab,
  macroData,
  loading,
  error,
  handleRemove,
  onViewChart,
}) {
  const { t } = useTranslation();
  const tabsCopy = t?.pages?.macro?.tabs || {};
  const TABS = [
    { id: "day", label: tabsCopy.day },
    { id: "week", label: tabsCopy.week },
    { id: "month", label: tabsCopy.month },
    { id: "quarter", label: tabsCopy.quarter },
  ];
  // Always guard macroData
  const safeData = Array.isArray(macroData) ? macroData : [];

  // ---------------------------------------------------------
  // 🔍 Table selector
  // ---------------------------------------------------------
  const renderTable = () => {
    if (loading) {
      return (
        <TechnicalTerminalGrid
          title={tabsCopy.indicators}
          data={[]} 
          onRemove={() => {}} // veilige no-op functie
        />
      );
    }

    if (error) {
      console.error("MacroTabs error:", error);
    }

    switch (activeTab) {
      case "day":
        return (
          <TechnicalTerminalGrid
            title={tabsCopy.indicators}
            data={safeData}
            onRemove={handleRemove} // enige tab met delete
            onViewChart={onViewChart}
          />
        );

      case "week":
        return (
          <WeekTable
            data={safeData}
          />
        );

      case "month":
        return (
          <MonthTable
            data={safeData}
          />
        );

      case "quarter":
        return (
          <QuarterTable
            data={safeData}
          />
        );

      default:
        return (
          <TechnicalTerminalGrid
            title={tabsCopy.indicators}
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
         <div className="text-[10px] font-black text-secondary uppercase tracking-[0.2em] pl-1">{tabsCopy.title}</div>
         <div className="flex bg-[var(--color-border-subtle)] p-1 rounded-xl border border-slate-200">
            {TABS.map((tab) => (
               <button
                  key={tab.id}
                  onClick={() => setActiveTab(tab.id)}
                  className={`px-5 py-2 rounded-lg text-[10px] font-black uppercase tracking-widest transition-all ${
                     activeTab === tab.id
                        ? "bg-card text-foreground shadow-sm"
                        : "text-secondary hover:text-slate-600"
                  }`}
               >
                  {tab.label}
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
