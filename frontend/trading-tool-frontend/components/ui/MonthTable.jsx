"use client";

import { Info, Trash2 } from "lucide-react";
import dayjs from "dayjs";

/**
 * 📅 MonthTable — PRO Style 2.2
 * Zelfde look & feel als DayTable en WeekTable, gegroepeerd per maand.
 */
export default function MonthTable({ data = [], onRemove }) {
  const groups = groupByMonth(data);

  if (!groups || groups.length === 0) {
    return (
      <div className="bg-white border border-slate-200 rounded-[2rem] p-12 text-center text-xs font-black text-slate-400 uppercase tracking-widest italic opacity-60">
         NO_MONTHLY_TELEMETRY_DETECTED
      </div>
    );
  }

  return (
    <div className="space-y-10 w-full">
      {groups.map((group, gIdx) => (
        <div key={gIdx} className="bg-white border border-slate-200 rounded-[2rem] shadow-sm overflow-hidden group/table">
          {/* TERMINAL HEADER */}
          <div className="px-8 py-5 border-b border-slate-100 flex items-center justify-between bg-slate-50/50">
            <div className="flex items-center gap-3">
              <div className="w-8 h-8 rounded-lg bg-white border border-slate-200 flex items-center justify-center text-slate-400 shadow-sm">
                 <Info className="w-4 h-4" />
              </div>
              <div className="text-[10px] font-black text-slate-500 uppercase tracking-widest leading-none">
                 MONTHLY_LOG_NODE: {group.label.toUpperCase()}
              </div>
            </div>
            <div className="text-[8px] font-black text-slate-300 uppercase tracking-[0.2em]">
               STATUS: ARCHIVAL_SYNC_COMPLETED
            </div>
          </div>

          <table className="w-full text-left border-collapse">
            <thead>
              <tr className="border-b border-slate-100 text-[10px] font-black text-slate-400 uppercase tracking-widest">
                <th className="px-8 py-4">Indicator Node</th>
                <th className="px-8 py-4 text-center">Value</th>
                <th className="px-8 py-4 text-center">Score</th>
                <th className="px-8 py-4">Decision_Signal</th>
                <th className="px-8 py-4">System_Interpretation</th>
                {onRemove && <th className="px-8 py-4 text-right">Actions</th>}
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-50">
              {group.items.map((item, idx) => (
                <MonthRow key={idx} item={item} onRemove={onRemove} />
              ))}
            </tbody>
          </table>
        </div>
      ))}
    </div>
  );
}

function MonthRow({ item, onRemove }) {
  const { name = "—", indicator, value = "—", score = null, interpretation = "—", action = "—" } = item;
  const displayName = name || indicator || "—";
  const scoreNum = Number(score ?? 0);

  const getSignalConfig = (s) => {
    if (s >= 70) return { bg: "bg-green-500", color: "text-green-600" };
    if (s <= 30) return { bg: "bg-red-500", color: "text-red-600" };
    return { bg: "bg-slate-400", color: "text-slate-400" };
  };

  const signal = getSignalConfig(scoreNum);

  return (
    <tr className="group hover:bg-slate-50/30 transition-colors">
      <td className="px-8 py-5">
        <div className="font-black text-slate-800 tracking-tight text-xs">{displayName}</div>
      </td>

      <td className="px-8 py-5 text-center font-mono text-[10px] font-bold text-slate-500">
        {value}
      </td>

      <td className={`px-8 py-5 text-center font-black text-sm tracking-tighter ${
        scoreNum >= 75 ? "text-green-600" : scoreNum <= 25 ? "text-red-600" : "text-slate-400"
      }`}>
        {score ?? "—"}
      </td>

      <td className="px-8 py-5 min-w-[150px]">
        <div className="flex flex-col gap-1">
           <div className="h-3 w-full bg-slate-100 rounded-full p-0.5 border border-slate-100 overflow-hidden">
              <div className={`h-full rounded-full transition-all duration-700 ${signal.bg}`} style={{ width: `${scoreNum}%` }} />
           </div>
           <div className={`text-[8px] font-black uppercase tracking-widest ${signal.color}`}>
              {action || "NEUTRAL"}
           </div>
        </div>
      </td>

      <td className="px-8 py-5">
        <p className="text-[10px] text-slate-500 leading-relaxed max-w-sm font-medium italic">
          {interpretation}
        </p>
      </td>

      {onRemove && (
        <td className="px-8 py-5 text-right">
           <button
             onClick={() => onRemove?.(displayName)}
             className="p-1.5 rounded-lg text-slate-300 hover:text-red-500 hover:bg-red-50 transition-all opacity-0 group-hover:opacity-100"
           >
             <Trash2 size={14} />
           </button>
        </td>
      )}
    </tr>
  );
}

/* =====================================================
   MONTH GROUPING — PRO versie
===================================================== */
function groupByMonth(items) {
  if (!Array.isArray(items)) return [];

  const groups = {};

  items.forEach((item) => {
    const ts = item.timestamp || item.date;
    if (!ts) return;

    const d = dayjs(ts);
    const monthName = d.format("MMMM");
    const year = d.year();
    const key = `${year}-${d.month()}`;

    if (!groups[key]) {
      groups[key] = {
        label: `${monthName} – ${year}`,
        items: [],
      };
    }

    groups[key].items.push(item);
  });

  return Object.values(groups);
}
