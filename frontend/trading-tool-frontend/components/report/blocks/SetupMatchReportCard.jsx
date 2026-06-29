"use client";

import ReportCard from "../ReportCard";
import { CheckCircle2, Layers } from "lucide-react";
import { useTranslation } from "@/app/providers/I18nProvider";

/* -------------------------------------------------------
   Helper
   - Refined V2 PRO ScoreBar
------------------------------------------------------- */
function ScoreBar({ score }) {
  const pct = Math.max(0, Math.min(100, Number(score) || 0));

  let color = "bg-slate-400";
  if (pct >= 80) color = "bg-green-500";
  else if (pct <= 40) color = "bg-red-500";

  return (
    <div className="w-full h-1 bg-[var(--color-border-subtle)] rounded-full overflow-hidden">
      <div
        className={`h-full ${color} transition-all duration-1000 ease-out shadow-sm`}
        style={{ width: `${pct}%` }}
      />
    </div>
  );
}

/* =======================================================
   Setup Match — REPORT (V2 PRO REFINED)
======================================================= */
export default function SetupMatchReportCard({ report }) {
  const { t } = useTranslation();
  const copy = t?.reports?.blocks?.setupMatch || {};
  const best = report?.best_setup;
  const topSetups = report?.top_setups || [];

  if (!best) {
    return (
      <ReportCard title={copy.cardTitle} icon={<Layers size={16} />}>
        <p className="text-sm text-secondary italic">
          {copy.empty}
        </p>
      </ReportCard>
    );
  }

  return (
    <ReportCard title={copy.cardTitle} icon={<Layers size={16} />}>
      
      {/* BESTE OPTIE */}
      <div className="mb-8 p-5 rounded-2xl bg-card border border-slate-50 shadow-sm">
        <div className="flex items-center gap-2 mb-3">
          <CheckCircle2 className="w-4 h-4 text-green-600" />
          <span className="text-[11px] font-bold text-secondary tracking-tight">
            {copy.bestMatch}
          </span>
        </div>

        <div className="flex items-baseline gap-2 mb-4">
          <span className="text-xl font-bold text-foreground tracking-tight">{best.name}</span>
          <span className="text-xs font-medium text-secondary font-mono">
            · {best.symbol} · {best.timeframe}
          </span>
        </div>

        <div className="space-y-2">
           <div className="flex justify-between items-end">
              <span className="text-[11px] font-bold text-secondary tracking-tight">{copy.matchScore}</span>
              <span className="text-sm font-bold text-foreground font-mono tracking-tight">{best.score}%</span>
           </div>
           <ScoreBar score={best.score} />
        </div>
      </div>

      {/* VERGELIJKING (Top Setups) */}
      {topSetups.length > 0 && (
        <div className="space-y-6">
          <h4 className="text-[11px] font-bold text-secondary tracking-tight mb-4">
            {copy.comparison}
          </h4>

          <div className="space-y-5">
            {topSetups.map((s) => (
              <div key={s.id} className="group">
                <div className="flex justify-between items-center mb-1.5">
                  <span className="text-[13px] font-bold text-dim group-hover:text-slate-900 transition-colors">
                    {s.name}
                  </span>
                  <span className="text-sm font-bold text-foreground font-mono tracking-tight">
                    {s.score}%
                  </span>
                </div>
                <ScoreBar score={s.score} />
              </div>
            ))}
          </div>
        </div>
      )}

      {/* TOELICHTING */}
      <div className="mt-8 pt-6 border-t border-slate-50 text-[12px] text-muted leading-relaxed italic">
        {copy.explanation}
      </div>
    </ReportCard>
  );
}
