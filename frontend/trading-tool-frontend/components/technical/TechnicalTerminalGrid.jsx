import { Info, Activity, AlertTriangle, RefreshCcw, Trash2 } from "lucide-react";
import dayjs from "dayjs";
import TrendSparkline from "@/components/dashboard/TrendSparkline";
import SkeletonTable from "@/components/ui/SkeletonTable";

export default function TechnicalTerminalGrid({
  title = null,
  icon = null,
  data = [],
  error = null,
  onRetry = null,
  onRemove = null,
  onViewChart = null,
  loading = false,
}) {
  if (loading) {
    return (
      <div className="card card-p">
        <SkeletonTable rows={5} columns={6} />
      </div>
    );
  }
  const safeData = Array.isArray(data) ? data : [];

  const getDayLabel = () => {
    if (!safeData.length) return "LIVE";
    const ts = safeData[0]?.timestamp || safeData[0]?.created_at || safeData[0]?.date;
    return ts ? dayjs(ts).format("DD MMM YYYY") : "LIVE";
  };

  if (error) {
    return (
      <div className="card card-p flex flex-col items-center justify-center text-center py-12">
        <AlertTriangle className="w-10 h-10 mb-4 text-red-500" />
        <h3 className="text-lg font-semibold text-foreground mb-2">Geen verbinding</h3>
        <p className="text-sm text-muted mb-6 max-w-xs">{error}</p>
        {onRetry && (
          <button onClick={onRetry} className="btn-primary flex items-center gap-2">
            <RefreshCcw className="w-4 h-4" /> Herstellen
          </button>
        )}
      </div>
    );
  }

  return (
    <div className="card overflow-hidden">
      {/* 🟢 CARD HEADER */}
      <div className="card-header">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-[var(--color-border-subtle)] border border-slate-200 flex items-center justify-center text-blue-600">
             {icon || <Activity size={16} />}
          </div>
          <div>
            <h2 className="text-sm font-semibold text-slate-900">{title || "Overzicht"}</h2>
            <div className="text-[10px] font-bold text-secondary uppercase tracking-widest">{getDayLabel()}</div>
          </div>
        </div>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-left border-collapse table-auto">
          <thead>
            <tr className="border-b border-slate-100 text-[10px] font-bold text-secondary uppercase tracking-widest">
              <th className="px-6 py-4">Indicator</th>
              <th className="px-6 py-4 text-center">Waarde</th>
              <th className="px-6 py-4 text-center">Trend</th>
              <th className="px-6 py-4 text-center">Score</th>
              <th className="px-6 py-4">Signaal</th>
              <th className="px-6 py-4">Toelichting</th>
              <th className="px-6 py-4 text-right w-12"></th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-50">
            {safeData.length === 0 ? (
              <tr>
                <td colSpan={7} className="px-8 py-20 text-center text-[11px] font-bold text-slate-300 uppercase tracking-widest italic animate-pulse">
                   Geen signalen beschikbaar
                </td>
              </tr>
            ) : (
              safeData.map((item, idx) => (
                <TerminalRow 
                  key={idx} 
                  item={item} 
                  onRemove={onRemove} 
                  onViewChart={onViewChart} 
                />
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function TerminalRow({ item, onRemove, onViewChart }) {
  const { name, indicator, value, score, action, interpretation } = item;
  const displayName = name || indicator || "—";
  const scoreNum = Number(score ?? 0);

  const formatValue = (val) => {
    if (val === null || val === undefined) return "—";
    if (typeof val !== "number") {
      const num = Number(val.toString().replace(/[^0-9.-]+/g,""));
      if (!isNaN(num) && num > 1000000) return formatShorthand(num);
      return val;
    }
    if (val > 1000000) return formatShorthand(val);
    return val.toLocaleString();
  };

  const formatShorthand = (n) => {
    if (n >= 1e12) return (n / 1e12).toFixed(2) + "T";
    if (n >= 1e9) return (n / 1e9).toFixed(2) + "B";
    if (n >= 1e6) return (n / 1e6).toFixed(2) + "M";
    return n.toLocaleString();
  };

  const getStatusClass = (a, s) => {
    const act = (a || "").toLowerCase();
    if (act.includes("buy") || s >= 70) return { cls: "status-active", label: "Actief" };
    if (act.includes("sell") || s <= 30) return { cls: "status-weak", label: "Zwak" };
    return { cls: "status-neutral", label: "Neutraal" };
  };

  const status = getStatusClass(action, scoreNum);

  return (
    <tr className="group hover:bg-slate-50/50 transition-colors">
      <td className="px-6 py-5">
        <div 
          className="flex items-center gap-3 cursor-pointer group/item"
          onClick={() => onViewChart && onViewChart(displayName)}
        >
           <div className="w-7 h-7 rounded-md bg-[var(--color-border-subtle)] border border-slate-100 flex items-center justify-center text-secondary group-hover/item:text-blue-600 group-hover/item:bg-blue-50 transition-colors">
              <Info size={12} />
           </div>
           <div className="font-semibold text-foreground text-xs truncate max-w-[140px] group-hover/item:text-blue-600 transition-colors" title={displayName}>
              {displayName}
           </div>
        </div>
      </td>

      <td className="px-6 py-5 text-center font-mono text-[10px] font-bold text-slate-500">
        {formatValue(value)}
      </td>

      <td className="px-6 py-5">
        <div className="flex justify-center">
          <TrendSparkline indicatorName={displayName} score={scoreNum} />
        </div>
      </td>

      <td className={`px-6 py-5 text-center font-semibold text-base ${
        scoreNum >= 75 ? "text-green-600" : scoreNum <= 25 ? "text-red-600" : "text-secondary"
      }`}>
        {score ?? "—"}
      </td>

      <td className="px-6 py-5">
        <span className={`status ${status.cls}`}>
          {status.label}
        </span>
      </td>

      <td className="px-6 py-5">
        <p className="text-[10px] text-muted leading-normal max-w-[240px] font-medium italic">
          {interpretation || "Analyse in afwachting..."}
        </p>
      </td>

      <td className="px-6 py-5 text-right">
        <button
          onClick={() => onRemove && onRemove(displayName)}
          className="p-1.5 rounded-md text-slate-300 hover:text-red-500 hover:bg-red-50 transition-all opacity-0 group-hover:opacity-100"
        >
          <Trash2 size={14} />
        </button>
      </td>
    </tr>
  );
}
