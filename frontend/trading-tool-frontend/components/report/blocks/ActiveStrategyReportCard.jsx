"use client";

import ReportCard from "../ReportCard";
import {
  Target,
  Shield,
  TrendingUp,
  ArrowUpRight,
  ArrowDownRight,
} from "lucide-react";
import { useTranslation } from "@/app/providers/I18nProvider";
import { formatCurrency } from "@/lib/i18n";

function formatPairPrice(value, locale, quote) {
  if (!Number.isFinite(Number(value))) return "—";
  if (quote === "USDT") return `${Number(value).toLocaleString(locale, { maximumFractionDigits: 2 })} USDT`;
  return formatCurrency(Number(value), locale, quote === "EUR" ? "EUR" : "USD", { maximumFractionDigits: 2 });
}

/* =======================================================
   Active Strategy — REPORT (V2 PRO REFINED)
======================================================= */
export default function ActiveStrategyReportCard({ report }) {
  const { t, locale } = useTranslation();
  const copy = t?.reports?.blocks?.activeStrategy || {};
  const strategy = report?.active_strategy;
  const currentPrice = report?.watchlist?.length === 1
    ? report?.market_snapshot?.price ?? report?.kpi_metrics?.price ?? null : null;

  if (!strategy) {
    return (
      <ReportCard title={copy.cardTitle} icon={<TrendingUp size={16} />}>
        <p className="text-sm text-secondary italic">
          {copy.empty}
        </p>
      </ReportCard>
    );
  }

  if (Array.isArray(strategy.strategies)) {
    return (
      <ReportCard title={copy.multipleTitle || copy.cardTitle} icon={<TrendingUp size={16} />}>
        <ul className="space-y-3">
          {strategy.strategies.slice(0, 5).map((item, index) => (
            <li key={`${item.symbol || "asset"}-${index}`} className="rounded-xl border border-slate-100 p-3">
              <div className="text-sm font-bold text-foreground">{item.strategy_name}</div>
              <div className="text-xs text-secondary">
                {copy.linkedSetup || "Setup"}: {item.setup_name || "—"} · {item.symbol || "—"} · {item.timeframe || "—"}
              </div>
            </li>
          ))}
        </ul>
        {strategy.strategies.length > 5 && (
          <p className="mt-3 text-xs text-secondary">+{strategy.strategies.length - 5} {copy.moreStrategies || "strategieën"}</p>
        )}
      </ReportCard>
    );
  }

  const {
    strategy_name,
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
  const dca = String(strategy.setup_type || "").toLowerCase() === "dca";
  if (dca) {
    const days = copy.weekdays || [];
    const frequency = strategy.dca_frequency;
    const day = Number(strategy.dca_day);
    const cadence = frequency === "weekly"
      ? `${copy.weekly || "Weekly"}${days[day - 1] ? ` · ${days[day - 1]}` : ""}`
      : frequency === "monthly"
        ? `${copy.monthly || "Monthly"}${strategy.dca_month_day ? ` · ${strategy.dca_month_day}` : ""}`
        : frequency === "daily" ? copy.daily : copy.unknownCadence;
    const points = Array.isArray(strategy.decision_curve?.points)
      ? [...strategy.decision_curve.points].sort((a, b) => Number(a.x) - Number(b.x)) : [];
    const smart = strategy.execution_mode === "custom";
    return (
      <ReportCard title={copy.cardTitle} icon={<TrendingUp size={16} />}>
        <div className="text-lg font-bold text-foreground">{strategy_name || setup_name}</div>
        <div className="text-xs text-secondary">{strategy.pair || symbol} · {timeframe}</div>
        <dl className="mt-4 space-y-3 text-sm">
          <div><dt className="text-secondary">{copy.purchaseSchedule}</dt><dd className="font-semibold">{cadence}</dd></div>
          <div><dt className="text-secondary">{copy.baseAmount}</dt><dd className="font-semibold">{strategy.base_amount != null ? formatCurrency(Number(strategy.base_amount), locale, "EUR") : "—"}</dd></div>
          <div><dt className="text-secondary">{copy.amountRule}</dt><dd className="font-semibold">{smart ? copy.scoreBased : strategy.execution_mode === "fixed" ? copy.fixedAmount : copy.unknownCadence}</dd></div>
        </dl>
        {smart && points.length > 0 && <div className="mt-4 border-t border-slate-100 pt-3 text-sm">
          <div className="font-semibold">{copy.scoreBands}</div>
          <ul className="mt-2 space-y-1">
            {points.map((point) => <li key={point.x} className="flex justify-between gap-3">
              <span>{copy.fromScore} {point.x}</span><span>{Math.round(Number(point.y) * 100)}%</span>
            </li>)}
          </ul>
        </div>}
      </ReportCard>
    );
  }
  const referencePrice = isDCA ? currentPrice : entry;
  const quoteCurrency = String(strategy.pair || "").split("/")[1] || "USD";

  const priceDiff =
    currentPrice && referencePrice
      ? ((currentPrice - referencePrice) / referencePrice) * 100
      : null;

  const isPositive = priceDiff !== null && priceDiff >= 0;

  return (
    <ReportCard title={copy.cardTitle} icon={<TrendingUp size={16} />}>
      
      {/* HEADER: IDENTITY */}
      <div className="mb-6">
        <div className="text-[11px] font-bold text-secondary tracking-tight mb-1">{copy.strategyLabel}</div>
        <div className="flex items-baseline gap-2">
           <span className="text-xl font-bold text-foreground tracking-tight">{strategy_name || setup_name}</span>
           <span className="text-xs font-medium text-secondary font-mono">· {symbol} · {timeframe}</span>
        </div>
      </div>

      <div className="space-y-6">
        
        {/* ENTRY & PERFORMANCE */}
        <div className="p-4 rounded-xl bg-card border border-slate-50 shadow-sm flex justify-between items-center">
            <div className="flex flex-col">
              <span className="text-[11px] font-bold text-secondary tracking-tight leading-none mb-2">
                {isDCA ? copy.referencePrice : copy.entryPrice}
              </span>
              <span className="text-xl font-bold text-foreground font-mono tracking-tight">
                {referencePrice !== null && referencePrice !== undefined
                  ? formatPairPrice(referencePrice, locale, quoteCurrency)
                  : "—"}
              </span>
            </div>

            {priceDiff !== null && (
              <div className={`flex flex-col items-end px-4 py-2 rounded-xl border ${
                isPositive ? "bg-green-500/5 border-green-500/10 text-green-700" : "bg-red-500/5 border-red-500/10 text-red-700"
              }`}>
                <span className="text-[10px] font-bold tracking-tight leading-none mb-1 opacity-70">{copy.priceChange}</span>
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
             <div className="text-[11px] font-bold text-secondary tracking-tight">{copy.targets}</div>
             <div className="flex flex-wrap gap-2">
                {(Array.isArray(targets) ? targets : String(targets).split(",")).map((t, i) => (
                   <div key={i} className="flex items-center gap-2 px-3 py-1.5 bg-slate-50/50 border border-slate-100 rounded-lg">
                    <Target size={12} className="text-secondary" />
                    <span className="text-xs font-bold text-slate-700 font-mono">{String(typeof t === "object" ? t.price ?? "" : t).trim()}</span>
                  </div>
                ))}
             </div>
          </div>
        )}

        {/* RISK MANAGEMENT */}
        <div className="grid grid-cols-2 gap-4 pt-4 border-t border-slate-50">
           <div className="flex flex-col">
              <span className="text-[11px] font-bold text-secondary tracking-tight leading-none mb-2">{copy.stopLoss}</span>
              <div className="flex items-center gap-2">
                 <Shield size={14} className="text-red-500" />
                 <span className="text-[15px] font-bold text-foreground font-mono">
                    {stop_loss !== null && stop_loss !== undefined
                      ? formatPairPrice(stop_loss, locale, quoteCurrency)
                      : "—"}
                 </span>
              </div>
           </div>

           {confidence_score !== null && (
             <div className="flex flex-col items-end">
                <span className="text-[11px] font-bold text-secondary tracking-tight leading-none mb-2">{copy.confidence}</span>
                <span className="text-[15px] font-bold text-foreground font-mono">{confidence_score}%</span>
             </div>
           )}
        </div>

      </div>
    </ReportCard>
  );
}
