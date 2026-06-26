'use client';

import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "@/app/providers/I18nProvider";
import {
  CalendarRange,
  TrendingUp,
  PieChart,
  BarChart3
} from "lucide-react";

/* ===========================================================
   🎨 PRO-KLEUREN
   Zachtere pastel heatmap (TradingView style)
=========================================================== */
const heatmapColor = (value) => {
  if (value === null || value === undefined) return "bg-[var(--bg-soft)] text-[var(--text-light)]";

  if (value > 12) return "bg-green-200 text-green-900";       // sterke win
  if (value > 5) return "bg-green-100 text-green-800";        // lichte win
  if (value < -12) return "bg-red-300 text-red-900";          // sterke verlies
  if (value < -5) return "bg-red-200 text-red-900";           // lichte verlies

  return "bg-[var(--bg-soft)] text-[var(--text-dark)]";       // neutraal
};

const TAB_KEYS = ["week", "month", "quarter", "year"];

const formatPercentage = (value) => {
  if (value === null || value === undefined || isNaN(value)) return "–";
  return `${value.toFixed(1)}%`;
};

/* ===========================================================
   🌟 HOOFD COMPONENT
=========================================================== */
export default function MarketForwardReturnTabs({ data = {} }) {
  const { locale } = useTranslation();
  const isDutch = locale !== "en";
  const [active, setActive] = useState("month");
  const [selectedYears, setSelectedYears] = useState([]);

  const activeData = data[active] || [];
  const labelsByTab = useMemo(
    () => ({
      week: Array.from({ length: 53 }, (_, i) => `W${i + 1}`),
      month: isDutch
        ? ["JAN", "FEB", "MRT", "APR", "MEI", "JUN", "JUL", "AUG", "SEP", "OKT", "NOV", "DEC"]
        : ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"],
      quarter: ["Q1", "Q2", "Q3", "Q4"],
      year: [isDutch ? "JAAR" : "YEAR"],
    }),
    [isDutch]
  );
  const labels = labelsByTab[active] || [];

  const tabLabels = {
    week: isDutch ? "Week" : "Week",
    month: isDutch ? "Maand" : "Month",
    quarter: isDutch ? "Kwartaal" : "Quarter",
    year: isDutch ? "Jaar" : "Year",
  };

  const copy = {
    matrix: isDutch ? "Matrix" : "Matrix",
    computed: isDutch ? "Berekend" : "Computed",
    year: isDutch ? "Jaar" : "Year",
    yearAverage: isDutch ? "Gem. jaar" : "Avg. year",
    totalAverage: isDutch ? "Gem. totaal" : "Avg. total",
    forwardOverview: isDutch
      ? "Forward return overzicht (geselecteerde jaren)"
      : "Forward return overview (selected years)",
    metric: isDutch ? "Metriek" : "Metric",
    numberOfYears: isDutch ? "Aantal jaren" : "Number of years",
    positivePeriods: isDutch ? "Positieve periodes" : "Positive periods",
    negativePeriods: isDutch ? "Negatieve periodes" : "Negative periods",
    positiveChance: isDutch
      ? "Kans op positief resultaat"
      : "Chance of positive outcome",
  };

  useEffect(() => {
    setSelectedYears(activeData.map((row) => row.year));
  }, [active, activeData]);

  const toggleYear = (year) => {
    setSelectedYears((prev) =>
      prev.includes(year) ? prev.filter((y) => y !== year) : [...prev, year]
    );
  };

  const calculateYearAvg = (values) => {
    const valid = values.filter((v) => v !== null && v !== undefined);
    if (!valid.length) return null;
    return valid.reduce((a, b) => a + b, 0) / valid.length;
  };

  const calculateColumnAverages = () => {
    return labels.map((_, colIdx) => {
      const vals = activeData.map((row) => row.values[colIdx]);
      const valid = vals.filter((v) => v !== null && v !== undefined);
      if (!valid.length) return null;
      return valid.reduce((a, b) => a + b, 0) / valid.length;
    });
  };

  const colAverages = calculateColumnAverages();

  const selectedData = activeData.filter((row) =>
    selectedYears.includes(row.year)
  );

  const forwardStats = labels.map((_, idx) => {
    const vals = selectedData.map((row) => row.values[idx]);
    const valid = vals.filter((v) => v !== null && v !== undefined);
    const wins = valid.filter((v) => v > 0).length;
    const losses = valid.filter((v) => v <= 0).length;
    return {
      total: valid.length,
      wins,
      losses,
      rate: valid.length ? (wins / valid.length) * 100 : null,
    };
  });

  const displayData = activeData.length
    ? [...activeData].sort((a, b) => b.year - a.year)
    : [{ year: null, values: Array(labels.length).fill(null) }];

  return (
    <div className="space-y-6">
      {/* INDUSTRIAL CONTROL CONSOLE (Tabs) */}
      <div className="flex p-1.5 bg-slate-100/50 border border-slate-200 rounded-2xl w-fit">
        {TAB_KEYS.map((tab) => (
          <button
            key={tab}
            onClick={() => setActive(tab)}
            className={`px-8 py-2.5 rounded-xl text-[10px] font-black uppercase tracking-[0.2em] transition-all
              ${active === tab
                  ? "bg-card text-foreground shadow-sm border border-slate-200"
                  : "text-secondary hover:text-slate-600 hover:bg-white/50"
              }`}
          >
            {tabLabels[tab]}
          </button>
        ))}
      </div>

      {/* PERFORMANCE TERMINAL SYSTEM (Vertical Stack for Readability) */}
      <div className="space-y-8">
        
        {/* HEATMAP TERMINAL */}
        <div className="bg-card border border-slate-200 rounded-[2rem] shadow-sm overflow-hidden flex flex-col">
          <div className="px-8 py-5 border-b border-slate-100 flex items-center justify-between bg-slate-50/50">
             <div className="flex items-center gap-3">
                <div className="w-8 h-8 rounded-lg bg-card border border-slate-200 flex items-center justify-center text-slate-400">
                   <PieChart className="w-4 h-4" />
                </div>
                <div className="text-[10px] font-black text-muted uppercase tracking-widest leading-none">
                  {copy.matrix}: {tabLabels[active].toUpperCase()}
                </div>
             </div>
             <div className="text-[8px] font-black text-slate-300 uppercase tracking-[0.2em] whitespace-nowrap">
                {copy.computed}
             </div>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse">
              <thead>
                <tr className="border-b border-slate-100 text-[9px] font-black text-secondary uppercase tracking-widest">
                  <th className="px-6 py-4 w-12 text-center">
                     <CalendarRange className="w-3.5 h-3.5 mx-auto" />
                  </th>
                  <th className="px-6 py-4">{copy.year}</th>
                  {labels.map((label) => (
                    <th key={label} className="px-1 py-4 text-center">{label}</th>
                  ))}
                  <th className="px-6 py-4 text-center">{copy.yearAverage}</th>
                </tr>
              </thead>

              <tbody className="divide-y divide-slate-50">
                {displayData.map((row, idx) => {
                  const avg = calculateYearAvg(row.values);
                  return (
                    <tr key={idx} className="group hover:bg-slate-50/30 transition-colors">
                      <td className="px-6 py-4 text-center">
                        <input
                          type="checkbox"
                          checked={selectedYears.includes(row.year)}
                          onChange={() => toggleYear(row.year)}
                          disabled={row.year === null}
                          className="w-3.5 h-3.5 rounded border-slate-200 text-[var(--primary)] focus:ring-[var(--primary)]"
                        />
                      </td>
                      <td className="px-6 py-4 font-mono text-xs font-bold text-slate-800">{row.year ?? "—"}</td>
                      {row.values.map((val, i) => (
                        <td key={i} className="px-0.5 py-3 text-center">
                          <div className={`py-1.5 rounded-[4px] font-mono text-[10px] font-black ${heatmapColor(val)}`}>
                             {formatPercentage(val)}
                          </div>
                        </td>
                      ))}
                      <td className="px-6 py-4 text-center">
                         <div className="font-mono text-[10px] font-black text-slate-800">
                            {formatPercentage(avg)}
                         </div>
                      </td>
                    </tr>
                  );
                })}

                {/* FOOTER: COLUMN AVERAGES */}
                <tr className="bg-slate-50/80 font-black border-t border-slate-200">
                  <td className="px-6 py-5 text-center">—</td>
                  <td className="px-6 py-5 text-[10px] uppercase tracking-widest text-muted whitespace-nowrap">{copy.totalAverage}</td>
                  {colAverages.map((val, i) => (
                    <td key={i} className="px-0.5 py-5 text-center">
                       <div className={`py-1.5 rounded-[4px] font-mono text-[10px] font-black ${heatmapColor(val)}`}>
                          {formatPercentage(val)}
                       </div>
                    </td>
                  ))}
                  <td className="px-6 py-5 text-center">—</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>

        {/* STATS PANEL: FORWARD RETURN RESULTS */}
        <div className="bg-card border border-slate-200 rounded-[2rem] shadow-sm overflow-hidden flex flex-col animate-in fade-in duration-700">
          <div className="px-8 py-5 border-b border-slate-100 flex items-center gap-3 bg-slate-50/50">
             <BarChart3 size={16} className="text-[var(--primary)]" />
             <h3 className="text-[10px] font-black uppercase tracking-widest text-muted truncate">
                {copy.forwardOverview}
             </h3>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse">
              <thead>
                <tr className="border-b border-slate-100 text-[9px] font-black text-secondary uppercase tracking-widest">
                  <th className="px-8 py-4">{copy.metric}</th>
                  {labels.map((l) => (
                    <th key={l} className="px-1 py-4 text-center">{l}</th>
                  ))}
                </tr>
              </thead>

              <tbody className="divide-y divide-slate-50">
                <tr className="group hover:bg-slate-50/30">
                  <td className="px-8 py-4 text-[10px] font-black uppercase tracking-widest text-slate-400">{copy.numberOfYears}</td>
                  {forwardStats.map((s, i) => (
                    <td key={i} className="px-1 py-4 text-center font-mono text-[10px] font-bold text-slate-600">{s.total}</td>
                  ))}
                </tr>
                <tr className="group hover:bg-slate-50/30">
                  <td className="px-8 py-4 text-[10px] font-black uppercase tracking-widest text-green-500">{copy.positivePeriods}</td>
                  {forwardStats.map((s, i) => (
                    <td key={i} className="px-1 py-4 text-center font-mono text-[10px] font-bold text-green-600">{s.wins}</td>
                  ))}
                </tr>
                <tr className="group hover:bg-slate-50/30">
                  <td className="px-8 py-4 text-[10px] font-black uppercase tracking-widest text-red-500">{copy.negativePeriods}</td>
                  {forwardStats.map((s, i) => (
                    <td key={i} className="px-1 py-4 text-center font-mono text-[10px] font-bold text-red-600">{s.losses}</td>
                  ))}
                </tr>
                <tr className="group hover:bg-slate-50/30 bg-slate-50/50">
                  <td className="px-8 py-5 text-[10px] font-black uppercase tracking-widest text-foreground italic">{copy.positiveChance}</td>
                  {forwardStats.map((s, i) => (
                    <td key={i} className="px-1 py-5 text-center font-mono text-xs font-black text-foreground border-t border-slate-100/50">
                      {s.rate !== null ? `${s.rate.toFixed(1)}%` : "—"}
                    </td>
                  ))}
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
}
