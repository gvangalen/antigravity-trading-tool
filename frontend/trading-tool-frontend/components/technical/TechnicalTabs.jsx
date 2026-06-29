"use client";

// PRO Terminal Grid
import TechnicalTerminalGrid from "@/components/technical/TechnicalTerminalGrid";
import { Activity, Layout, Layers, Box } from "lucide-react";
import { useTranslation } from "@/app/providers/I18nProvider";

export default function TechnicalTabs({
  activeTab,
  setActiveTab,
  technicalData,
  handleRemove,
  loading,
  error,
}) {
  const { t } = useTranslation();
  const tabsCopy = t?.pages?.technical?.tabs || {};
  const TABS = [
    { id: "day", label: tabsCopy.day },
    { id: "week", label: tabsCopy.week },
    { id: "month", label: tabsCopy.month },
    { id: "quarter", label: tabsCopy.quarter },
  ];

  const safeData = Array.isArray(technicalData) ? technicalData : [];

  const renderTable = () => {
    if (loading) {
      return (
        <TechnicalTerminalGrid
          title={tabsCopy.loading}
          data={[]}
          onRemove={null}
        />
      );
    }

    if (error) {
      console.error("❌ TechnicalTabs error:", error);
    }

    switch (activeTab) {
      case "day":
        return (
          <TechnicalTerminalGrid
            title={tabsCopy.dailyAnalysis}
            icon={<Activity size={20} />}
            data={safeData}
            onRemove={handleRemove}
          />
        );

      case "week":
        return (
          <TechnicalTerminalGrid
            title={tabsCopy.weeklyAnalysis}
            icon={<Box size={20} />}
            data={safeData}
            onRemove={handleRemove}
          />
        );

      case "month":
        return (
          <TechnicalTerminalGrid
            title={tabsCopy.monthlyAnalysis}
            icon={<Layers size={20} />}
            data={safeData}
            onRemove={handleRemove}
          />
        );

      case "quarter":
        return (
          <TechnicalTerminalGrid
            title={tabsCopy.quarterlyAnalysis}
            icon={<Layout size={20} />}
            data={safeData}
            onRemove={handleRemove}
          />
        );

      default:
        return null;
    }
  };

  return (
    <div className="space-y-8">
      {/* 🔹 TABS: SEGMENTED CONTROL */}
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

      {/* 🔹 SIGNAL GRID */}
      <div>
         {renderTable()}
      </div>
    </div>
  );
}
