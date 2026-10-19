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
    <div className="grid w-full grid-cols-2 gap-1.5 rounded-2xl border border-slate-200/60 bg-slate-100/50 p-1 shadow-inner-light animate-in fade-in slide-in-from-left-4 duration-700 sm:flex sm:w-fit sm:items-center">
      {Object.entries(REPORT_TYPE_IDS).map(([key, id]) => {
        const isSelected = selected === key;
        
        return (
          <button
            key={key}
            type="button"
            onClick={() => onChange(key)}
            className={`
              group relative flex min-w-0 items-center justify-center gap-2 rounded-xl px-2 py-2.5 transition-all duration-300 sm:px-3.5
              ${isSelected 
                ? "bg-card text-foreground shadow-[0_4px_12px_rgba(0,0,0,0.08)] border border-slate-200" 
                : "text-muted hover:text-slate-800 hover:bg-white/50"
              }
            `}
          >
            <span className={`
              flex h-5 w-5 shrink-0 items-center justify-center rounded-md font-mono text-[10px] font-black transition-colors
              ${isSelected ? "bg-slate-900 text-white" : "bg-slate-200 text-muted group-hover:bg-slate-300"}
            `}>
              {id}
            </span>
            <span className={`min-w-0 break-words text-center text-xs font-black uppercase leading-tight tracking-wider sm:tracking-widest ${isSelected ? "opacity-100" : "opacity-60 group-hover:opacity-100"}`}>
              {reportTypes[key]}
            </span>
          </button>
        );
      })}
    </div>
  );
}
