"use client";

import ReportCard from "../ReportCard";
import { Activity } from "lucide-react";
import { useTranslation } from "@/app/providers/I18nProvider";
import { reportMarketLabel, scoreSourceSnapshot } from "@/lib/report/reportSourceSnapshot.mjs";

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

function formatPrice(v, pair) {
  if (!isNum(v)) return "–";
  const quote = String(pair || "").split("/")[1];
  return `${quote === "EUR" ? "€" : quote === "USD" ? "US$" : ""}${formatNumber(v, 2)}${quote && quote !== "EUR" && quote !== "USD" ? ` ${quote}` : ""}`;
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
    <div className="min-w-0 rounded-xl border border-slate-50 bg-white/50 p-3 flex flex-col items-center justify-center transition-all hover:bg-white hover:shadow-sm group">
      <div className="max-w-full break-words text-center text-[11px] font-bold text-secondary leading-tight mb-1 group-hover:text-slate-500">{label}</div>
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
}) {
  const { t } = useTranslation();
  const copy = t?.reports?.blocks?.marketSnapshot || {};
  if (!report || typeof report !== "object") return null;
  const assets = scoreSourceSnapshot(report)?.assets || [];
  if (assets.length > 1) {
    return (
      <ReportCard title={copy.cardTitle} icon={<Activity size={16} />}>
        <div className="space-y-4">
          {assets.map((asset, index) => {
            const scores = asset.reported_scores || {};
            const snapshot = asset.market_snapshot || {};
            const measured = snapshot.source_status === "fresh";
            const components = [
              [copy.marketLabel, scores.market_score],
              [copy.macroLabel, scores.macro_score],
              [copy.technicalLabel, scores.technical_score],
            ];
            return (
              <div key={`${reportMarketLabel(asset)}-${index}`} className="border-b border-slate-200 pb-3 last:border-0 last:pb-0">
                <strong className="text-foreground">{reportMarketLabel(asset)}</strong>
                {measured && isNum(snapshot.price) && (
                  <div className="text-sm">{copy.priceLabel}: {formatPrice(snapshot.price, asset.pair)}</div>
                )}
                <div className="mt-2 flex flex-wrap gap-x-3 text-sm">
                  {components.map(([label, value]) => (
                    <span key={label}>{label}: {scoreValue(value)}</span>
                  ))}
                </div>
              </div>
            );
          })}
        </div>
      </ReportCard>
    );
  }

  const {
    price,
    change_24h,
    volume,
    macro_score,
    technical_score,
    market_score,
  } = report;

  const hasAnyScores =
    isNum(macro_score) ||
    isNum(technical_score) ||
    isNum(market_score);

  if (!isNum(price) && !isNum(change_24h) && !isNum(volume) && !hasAnyScores) return null;

  const changeIsUp = isNum(change_24h) ? Number(change_24h) >= 0 : null;

  return (
    <ReportCard title={copy.cardTitle} icon={<Activity size={16} />}>
      {/* === PRICE & VOL TELEMETRY === */}
      <div className="flex flex-col gap-6 mb-10">
        
        {/* PRICE NODE */}
        <div>
          <div className="flex items-center gap-2 mb-1">
            <span className="text-[11px] font-bold text-secondary tracking-tight">{copy.priceLabel}</span>
          </div>
          <div className="flex items-baseline gap-3">
            <div className="text-3xl font-bold text-foreground tracking-tight font-mono">
              {formatPrice(price, assets[0]?.pair)}
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
             <span className="text-[11px] font-bold text-secondary tracking-tight">{copy.volumeLabel}</span>
           </div>
           <div className="text-2xl font-bold text-foreground font-mono tracking-tight">
             {formatNumber(volume, 0)}
           </div>
        </div>

      </div>

      {/* === SCORE ARCHITECTURE GRID === */}
      {hasAnyScores && (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 pt-6 border-t border-slate-50">
          <ScoreItem label={copy.macroLabel} value={macro_score} />
          <ScoreItem label={copy.technicalLabel} value={technical_score} />
          <ScoreItem label={copy.marketLabel} value={market_score} />
        </div>
      )}
    </ReportCard>
  );
}
