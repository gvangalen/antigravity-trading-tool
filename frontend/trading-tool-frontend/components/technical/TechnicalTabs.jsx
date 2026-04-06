"use client";

// PRO Terminal Grid
import TechnicalTerminalGrid from "@/components/technical/TechnicalTerminalGrid";
import { Activity, Layout, Layers, Box } from "lucide-react";

const TABS = [
  { id: "Dag", label: "Dag" },
  { id: "Week", label: "Week" },
  { id: "Maand", label: "Maand" },
  { id: "Kwartaal", label: "Kwartaal" },
];

export default function TechnicalTabs({
  activeTab,
  setActiveTab,
  technicalData,
  handleRemove,
  loading,
  error,
}) {

  const safeData = Array.isArray(technicalData) ? technicalData : [];

  const renderTable = () => {
    if (loading) {
      return (
        <TechnicalTerminalGrid
          title="Analyseren..."
          data={[]}
          onRemove={null}
        />
      );
    }

    if (error) {
      console.error("❌ TechnicalTabs error:", error);
    }

    switch (activeTab) {
      case "Dag":
        return (
          <TechnicalTerminalGrid
            title="Dagelijkse Analyse"
            icon={<Activity size={20} />}
            data={safeData}
            onRemove={handleRemove}
          />
        );

      case "Week":
        return (
          <TechnicalTerminalGrid
            title="Wekelijkse Analyse"
            icon={<Box size={20} />}
            data={safeData}
            onRemove={handleRemove}
          />
        );

      case "Maand":
        return (
          <TechnicalTerminalGrid
            title="Maandelijkse Analyse"
            icon={<Layers size={20} />}
            data={safeData}
            onRemove={handleRemove}
          />
        );

      case "Kwartaal":
        return (
          <TechnicalTerminalGrid
            title="Kwartaal Analyse"
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
         <div className="text-[10px] font-black text-slate-400 uppercase tracking-[0.2em] pl-1">Tijdsinterval</div>
         <div className="flex bg-slate-100 p-1 rounded-xl border border-slate-200">
            {TABS.map((tab) => (
               <button
                  key={tab.id}
                  onClick={() => setActiveTab(tab.id)}
                  className={`px-5 py-2 rounded-lg text-[10px] font-black uppercase tracking-widest transition-all ${
                     activeTab === tab.id
                        ? "bg-white text-slate-800 shadow-sm"
                        : "text-slate-400 hover:text-slate-600"
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
