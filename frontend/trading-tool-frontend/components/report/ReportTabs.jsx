"use client";

import { useTranslation } from "@/app/providers/I18nProvider";

/**
 * 🛰️ Refined Report Tabs V2 PRO
 * - Industrial minimalist navigation
 * - Monospaced shortcuts (D/W/M/Q)
 * - Professional Dutch labels
 */
const REPORT_TYPE_IDS = {
  daily: "D",
  weekly: "W",
  monthly: "M",
  quarterly: "Q",
};

export default function ReportTabs({ selected, onChange }) {
  const { t } = useTranslation();
  const reportTypes = t.pages.report.types;

  return (
    <div className="flex items-center gap-1.5 p-1 bg-slate-100/50 rounded-2xl border border-slate-200/60 w-fit shadow-inner-light animate-in fade-in slide-in-from-left-4 duration-700">
      {Object.entries(REPORT_TYPE_IDS).map(([key, id]) => {
        const isSelected = selected === key;
        
        return (
          <button
            key={key}
            type="button"
            onClick={() => onChange(key)}
            className={`
              relative px-3.5 py-2.5 rounded-xl transition-all duration-300 flex items-center gap-2 group
              ${isSelected 
                ? "bg-card text-foreground shadow-[0_4px_12px_rgba(0,0,0,0.08)] border border-slate-200" 
                : "text-muted hover:text-slate-800 hover:bg-white/50"
              }
            `}
          >
            <span className={`
              font-mono text-[10px] font-black w-5 h-5 rounded-md flex items-center justify-center transition-colors
              ${isSelected ? "bg-slate-900 text-white" : "bg-slate-200 text-muted group-hover:bg-slate-300"}
            `}>
              {id}
            </span>
            <span className={`text-xs font-black uppercase tracking-widest ${isSelected ? "opacity-100" : "opacity-60 group-hover:opacity-100"}`}>
              {reportTypes[key]}
            </span>
          </button>
        );
      })}
    </div>
  );
}
