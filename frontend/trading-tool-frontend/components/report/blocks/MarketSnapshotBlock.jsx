import ReportCard from "../ReportCard";
import { Activity } from "lucide-react";

/* =====================================================
   HELPERS
===================================================== */

function isNum(v) {
  return v !== null && v !== undefined && v !== "" && !Number.isNaN(Number(v));
}

function formatNumber(v, decimals = 0) {
  if (!isNum(v)) return "–";
  return Number(v).toLocaleString(undefined, {
    maximumFractionDigits: decimals,
  });
}

function formatUSD(v) {
  if (!isNum(v)) return "–";
  return `$${formatNumber(v, 0)}`;
}

function formatPercent(v) {
  if (!isNum(v)) return "–";
  const n = Number(v);
  const sign = n > 0 ? "+" : "";
  return `${sign}${n.toFixed(2)}%`;
}

function scoreValue(v) {
  if (!isNum(v)) return "–";
  return Math.round(Number(v));
}

/* =====================================================
   SUB — SCORE ITEM
===================================================== */

function ScoreItem({ label, value }) {
  return (
    <div className="rounded-xl border border-slate-50 bg-white/50 p-3 flex flex-col items-center justify-center transition-all hover:bg-white hover:shadow-sm group">
      <div className="text-[11px] font-bold text-secondary tracking-tight mb-1 group-hover:text-slate-500">{label}</div>
      <div className="text-lg font-bold text-foreground font-mono tracking-tight">
        {scoreValue(value)}
      </div>
    </div>
  );
}

/* =====================================================
   BLOCK — MARKET SNAPSHOT (V2 PRO)
===================================================== */

export default function MarketSnapshotBlock({
  report,
  title = "Market_Audit_Log",
}) {
  if (!report || typeof report !== "object") return null;

  const {
    price,
    change_24h,
    volume,
    macro_score,
    technical_score,
    market_score,
    setup_score,
  } = report;

  const hasAnyScores =
    isNum(macro_score) ||
    isNum(technical_score) ||
    isNum(market_score) ||
    isNum(setup_score);

  const changeIsUp = isNum(change_24h) ? Number(change_24h) >= 0 : null;

  return (
    <ReportCard title="Marktanalyse" icon={<Activity size={16} />}>
      {/* === PRICE & VOL TELEMETRY === */}
      <div className="flex flex-col gap-6 mb-10">
        
        {/* PRICE NODE */}
        <div>
          <div className="flex items-center gap-2 mb-1">
            <span className="text-[11px] font-bold text-secondary tracking-tight">Bitcoin Prijs</span>
          </div>
          <div className="flex items-baseline gap-3">
            <div className="text-3xl font-bold text-foreground tracking-tight font-mono">
              {formatUSD(price)}
            </div>
            <div className={`text-sm font-bold font-mono ${
              changeIsUp === null ? "text-secondary" : changeIsUp ? "text-green-600" : "text-red-600"
            }`}>
              {formatPercent(change_24h)}
            </div>
          </div>
        </div>

        {/* VOLUME NODE */}
        <div>
           <div className="flex items-center gap-2 mb-1">
             <span className="text-[11px] font-bold text-secondary tracking-tight">Totaal Volume</span>
           </div>
           <div className="text-2xl font-bold text-foreground font-mono tracking-tight">
             {formatNumber(volume, 0)}
           </div>
        </div>

      </div>

      {/* === SCORE ARCHITECTURE GRID === */}
      {hasAnyScores && (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 pt-6 border-t border-slate-50">
          <ScoreItem label="Macro" value={macro_score} />
          <ScoreItem label="Technisch" value={technical_score} />
          <ScoreItem label="Markt" value={market_score} />
          <ScoreItem label="Setup" value={setup_score} />
        </div>
      )}
    </ReportCard>
  );
}
