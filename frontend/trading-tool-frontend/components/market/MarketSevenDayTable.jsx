"use client";

import { formatChange, formatNumber } from "@/components/market/utils";
import { useMemo } from "react";
import SkeletonTable from "@/components/ui/SkeletonTable";
import { useTranslation } from "@/app/providers/I18nProvider";
import { formatCurrency, formatDate, getIntlLocale } from "@/lib/i18n";

export default function MarketSevenDayTable({ history, loading = false }) {
  const { t, locale } = useTranslation();

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
      const formattedDate = formatDate(date, locale, {
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
  }, [history, locale]);

  /* ------------------------------
     Scorekleur volgens PRO 2.2
  ------------------------------ */
  const getChangeColor = (n) => {
    if (n === null || isNaN(n)) return "text-[var(--text-light)]";
    if (n > 0) return "text-green-600";
    if (n < 0) return "text-red-600";
    return "text-[var(--text-light)]";
  };

  const copy = t?.pages?.market?.historyTable || {};

  return (
    <div className="overflow-x-auto">
        <table className="w-full text-left border-collapse">
          <thead>
            <tr className="border-b border-slate-100 text-[10px] font-black text-secondary uppercase tracking-widest">
              <th className="px-8 py-5">{copy.date}</th>
              <th className="px-8 py-5 text-right">{copy.open}</th>
              <th className="px-8 py-5 text-right">{copy.high}</th>
              <th className="px-8 py-5 text-right">{copy.low}</th>
              <th className="px-8 py-5 text-right">{copy.close}</th>
              <th className="px-8 py-5 text-right">{copy.change}</th>
              <th className="px-8 py-5 text-right">{copy.volume}</th>
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
                  {typeof day.volume === "number"
                    ? new Intl.NumberFormat(getIntlLocale(locale), {
                        minimumFractionDigits: 1,
                        maximumFractionDigits: 1,
                      }).format(day.volume / 1e9) + "B"
                    : "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
    </div>
  );
}
