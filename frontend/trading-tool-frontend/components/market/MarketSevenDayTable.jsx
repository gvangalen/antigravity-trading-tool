"use client";

import CardWrapper from "@/components/ui/CardWrapper";
import { CalendarDays } from "lucide-react";
import { formatChange, formatNumber } from "@/components/market/utils";
import { useMemo } from "react";
import SkeletonTable from "@/components/ui/SkeletonTable";

export default function MarketSevenDayTable({ history, loading = false }) {
  if (loading) {
    return <SkeletonTable rows={7} columns={7} />;
  }
  const MAX_ROWS = 7;

  const rows = useMemo(() => {
    const today = new Date();
    const result = [];

    for (let i = 0; i < MAX_ROWS; i++) {
      const date = new Date(today);
      date.setDate(today.getDate() - i);

      const isoDate = date.toISOString().slice(0, 10);
      const formattedDate = date.toLocaleDateString("nl-NL", {
        day: "2-digit",
        month: "short",
      });

      const record = history?.find(
        (d) => new Date(d.date).toISOString().slice(0, 10) === isoDate
      );

      result.push({
        date: formattedDate,
        open: record?.open ?? null,
        high: record?.high ?? null,
        low: record?.low ?? null,
        close: record?.close ?? null,
        change: record?.change ?? null,
        volume: record?.volume ?? null,
      });
    }
    return result;
  }, [history]);

  /* ------------------------------
     Scorekleur volgens PRO 2.2
  ------------------------------ */
  const getChangeColor = (n) => {
    if (n === null || isNaN(n)) return "text-[var(--text-light)]";
    if (n > 0) return "text-green-600";
    if (n < 0) return "text-red-600";
    return "text-[var(--text-light)]";
  };

  return (
    <div className="bg-card border border-slate-200 rounded-[2.5rem] shadow-sm overflow-hidden">
      {/* TERMINAL HEADER */}
      <div className="px-8 py-6 border-b border-slate-100 flex items-center justify-between bg-slate-50/50">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-card border border-slate-200 flex items-center justify-center text-[var(--primary)] shadow-sm">
             <CalendarDays className="w-5 h-5" />
          </div>
          <div>
            <div className="text-[10px] font-black text-secondary uppercase tracking-widest leading-none">Historisch Log</div>
            <h2 className="text-xl font-black text-foreground tracking-tight uppercase leading-none mt-1">Markt Historie (7 Dagen)</h2>
          </div>
        </div>
        <div className="text-[10px] font-black text-blue-600 uppercase tracking-[0.2em] bg-blue-50 px-4 py-2 rounded-xl border border-blue-100 shadow-sm">
           SYSTEEM STATUS: LIVE
        </div>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-left border-collapse">
          <thead>
            <tr className="border-b border-slate-100 text-[10px] font-black text-secondary uppercase tracking-widest">
              <th className="px-8 py-5">Datum</th>
              <th className="px-8 py-5 text-right">Open</th>
              <th className="px-8 py-5 text-right">Hoog</th>
              <th className="px-8 py-5 text-right">Laag</th>
              <th className="px-8 py-5 text-right">Sluit</th>
              <th className="px-8 py-5 text-right">Verandering</th>
              <th className="px-8 py-5 text-right">Volume</th>
            </tr>
          </thead>

          <tbody className="divide-y divide-slate-50">
            {rows.map((day, idx) => (
              <tr key={idx} className="group hover:bg-slate-50/50 transition-colors">
                <td className="px-8 py-5">
                   <div className="font-black text-foreground tracking-tight text-xs uppercase">{day.date}</div>
                </td>

                <td className="px-8 py-5 text-right font-mono text-[10px] font-bold text-slate-500">
                  {typeof day.open === "number" ? formatNumber(day.open) : "—"}
                </td>

                <td className="px-8 py-5 text-right font-mono text-[10px] font-bold text-slate-500">
                  {typeof day.high === "number" ? formatNumber(day.high) : "—"}
                </td>

                <td className="px-8 py-5 text-right font-mono text-[10px] font-bold text-slate-500">
                  {typeof day.low === "number" ? formatNumber(day.low) : "—"}
                </td>

                <td className="px-8 py-5 text-right font-mono text-[10px] font-bold text-slate-800">
                  {typeof day.close === "number" ? formatNumber(day.close) : "—"}
                </td>

                <td className={`px-8 py-5 text-right font-black text-xs uppercase tracking-tighter ${getChangeColor(day.change)}`}>
                  {typeof day.change === "number" ? formatChange(day.change) : "—"}
                </td>

                <td className="px-8 py-5 text-right font-mono text-[10px] font-bold text-slate-400">
                  {typeof day.volume === "number" ? `$${(day.volume / 1e9).toFixed(1)}B` : "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
