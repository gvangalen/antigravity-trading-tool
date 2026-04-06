import ReportCard from "../ReportCard";
import {
  Target,
  Shield,
  TrendingUp,
  ArrowUpRight,
  ArrowDownRight,
  ChevronRight
} from "lucide-react";

/* =======================================================
   Active Strategy — REPORT (V2 PRO REFINED)
======================================================= */
export default function ActiveStrategyReportCard({ report }) {
  const strategy = report?.active_strategy;
  const currentPrice = report?.market_snapshot?.price ?? null;

  if (!strategy) {
    return (
      <ReportCard title="Actieve Strategie" icon={<TrendingUp size={16} />}>
        <p className="text-sm text-slate-400 italic">
          Geen actieve strategie voor deze periode.
        </p>
      </ReportCard>
    );
  }

  const {
    setup_name,
    symbol,
    timeframe,
    entry,
    targets,
    stop_loss,
    adjustment_reason,
    confidence_score,
  } = strategy;

  const isDCA = entry === null || entry === undefined;
  const referencePrice = isDCA ? currentPrice : entry;

  const priceDiff =
    currentPrice && referencePrice
      ? ((currentPrice - referencePrice) / referencePrice) * 100
      : null;

  const isPositive = priceDiff !== null && priceDiff >= 0;

  return (
    <ReportCard title="Actieve Strategie" icon={<TrendingUp size={16} />}>
      
      {/* HEADER: IDENTITY */}
      <div className="mb-6">
        <div className="text-[11px] font-bold text-slate-400 tracking-tight mb-1">Strategie</div>
        <div className="flex items-baseline gap-2">
           <span className="text-xl font-bold text-slate-900 tracking-tight">{setup_name}</span>
           <span className="text-xs font-medium text-slate-400 font-mono">· {symbol} · {timeframe}</span>
        </div>
      </div>

      <div className="space-y-6">
        
        {/* ENTRY & PERFORMANCE */}
        <div className="p-4 rounded-xl bg-white border border-slate-50 shadow-sm flex justify-between items-center">
            <div className="flex flex-col">
              <span className="text-[11px] font-bold text-slate-400 tracking-tight leading-none mb-2">
                {isDCA ? "Referentieprijs" : "Instapprijs"}
              </span>
              <span className="text-xl font-bold text-slate-800 font-mono tracking-tight">
                ${referencePrice?.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 }) ?? "—"}
              </span>
            </div>

            {priceDiff !== null && (
              <div className={`flex flex-col items-end px-4 py-2 rounded-xl border ${
                isPositive ? "bg-green-500/5 border-green-500/10 text-green-700" : "bg-red-500/5 border-red-500/10 text-red-700"
              }`}>
                <span className="text-[10px] font-bold tracking-tight leading-none mb-1 opacity-70">Koerswijziging</span>
                <div className="flex items-center gap-1 font-bold font-mono text-[15px]">
                   {isPositive ? <ArrowUpRight size={14} /> : <ArrowDownRight size={14} />}
                   {priceDiff.toFixed(2)}%
                </div>
              </div>
            )}
        </div>

        {/* TARGETS */}
        {targets && (
          <div className="space-y-3">
             <div className="text-[11px] font-bold text-slate-400 tracking-tight">Targets</div>
             <div className="flex flex-wrap gap-2">
                {targets.split(",").map((t, i) => (
                   <div key={i} className="flex items-center gap-2 px-3 py-1.5 bg-slate-50/50 border border-slate-100 rounded-lg">
                    <Target size={12} className="text-slate-400" />
                    <span className="text-xs font-bold text-slate-700 font-mono">{t.trim()}</span>
                  </div>
                ))}
             </div>
          </div>
        )}

        {/* RISK MANAGEMENT */}
        <div className="grid grid-cols-2 gap-4 pt-4 border-t border-slate-50">
           <div className="flex flex-col">
              <span className="text-[11px] font-bold text-slate-400 tracking-tight leading-none mb-2">Stop-loss</span>
              <div className="flex items-center gap-2">
                 <Shield size={14} className="text-red-500" />
                 <span className="text-[15px] font-bold text-slate-900 font-mono">
                    ${stop_loss?.toLocaleString(undefined, { maximumFractionDigits: 2 }) ?? "—"}
                 </span>
              </div>
           </div>

           {confidence_score !== null && (
             <div className="flex flex-col items-end">
                <span className="text-[11px] font-bold text-slate-400 tracking-tight leading-none mb-2">Vertrouwen</span>
                <span className="text-[15px] font-bold text-slate-900 font-mono">{confidence_score}%</span>
             </div>
           )}
        </div>

      </div>
    </ReportCard>
  );
}
