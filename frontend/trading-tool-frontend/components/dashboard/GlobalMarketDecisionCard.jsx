"use client";

import React from "react";
import { Activity } from "lucide-react";
import { useMarketIntelligence } from "@/hooks/useMarketIntelligence";
import MarketDecisionCard from "@/components/bot/MarketDecisionCard";
import { useTranslation } from "@/app/providers/I18nProvider";

export default function GlobalMarketDecisionCard({
  symbol = "BTC",
  snapshot = null,
  compact = false,
  fallbackMessage = null,
}) {
  const { t } = useTranslation();
  const snapshotData = snapshot?.data ?? null;
  const snapshotLoading = Boolean(snapshot?.loading);
  const snapshotNeedsFallback =
    !snapshotData
    || snapshotData?.available === false
    || snapshotData?.data_status === "pending_refresh"
    || (!snapshotData?.cycle && !snapshotData?.metrics && !snapshotData?.trend);
  const fallbackSnapshot = useMarketIntelligence(symbol, { enabled: !snapshot || snapshotNeedsFallback });
  const data = snapshotNeedsFallback
    ? (fallbackSnapshot.data ?? snapshotData)
    : (snapshotData ?? fallbackSnapshot.data);
  const loading = snapshotNeedsFallback
    ? ((snapshotLoading || fallbackSnapshot.loading) && !data)
    : (snapshotLoading || fallbackSnapshot.loading) && !data;
  const placeholderCopy = t?.ui?.marketDecision || {};

  if (loading) {
    return (
      <div className="flex items-center gap-3 text-xs font-black text-secondary uppercase tracking-widest p-12 justify-center">
        <div className="w-4 h-4 rounded-full border-2 border-slate-200 border-t-[var(--primary)] animate-spin" />
        {t.dashboard.loadingMarketContext}
      </div>
    );
  }

  if (
    !data
    || data?.data_status === "pending_refresh"
    || data?.available === false
    || data?.data_status === "insufficient_data"
    || data?.data_status === "fallback"
  ) {
    return (
      <div className="space-y-8">
        <div className="flex items-center justify-between border-b border-slate-100 pb-4 dark:border-slate-800">
          <div className="flex items-center gap-3">
            <div className="rounded-lg bg-blue-50 p-2 text-blue-600 dark:bg-blue-600/10">
              <Activity size={18} />
            </div>
            <div>
              <div className="mb-0.5 text-[10px] font-black uppercase tracking-widest text-muted">
                {placeholderCopy.title}
              </div>
              <div className="text-sm font-bold tracking-tight text-foreground">
                {placeholderCopy.subtitle}
              </div>
            </div>
          </div>

          <div className="rounded-xl border border-amber-200 bg-amber-50 px-3 py-1.5 text-[10px] font-black uppercase tracking-widest text-amber-700 dark:border-amber-900/40 dark:bg-amber-950/20 dark:text-amber-300">
            {placeholderCopy.buildingLabel}
          </div>
        </div>

        <div className="rounded-2xl border border-slate-200 bg-slate-50/75 p-5 dark:border-slate-800 dark:bg-slate-900/40">
          <div className="text-[10px] font-black uppercase tracking-[0.2em] text-secondary">
            {placeholderCopy.structuralPhase}
          </div>
          <div className="mt-2 text-base font-black text-foreground">
            {placeholderCopy.emptyHeadline}
          </div>
          <p className="mt-2 max-w-3xl text-sm font-medium leading-6 text-slate-600 dark:text-slate-300">
            {fallbackMessage || placeholderCopy.emptyBody || t?.common?.insufficientData || "Onvoldoende data"}
          </p>

          <div className="mt-5 grid grid-cols-4 gap-3">
            {[
              placeholderCopy.phases?.accumulation,
              placeholderCopy.phases?.expansion,
              placeholderCopy.phases?.distribution,
              placeholderCopy.phases?.correction,
            ].map((phaseLabel, index) => (
              <div key={`${phaseLabel}-${index}`} className="flex flex-col items-center gap-2">
                <div className={`h-2 w-full rounded-full ${index === 0 ? "bg-blue-500/70" : "bg-slate-200 dark:bg-slate-800"}`} />
                <div className={`text-[8px] font-black uppercase tracking-[0.12em] ${index === 0 ? "text-blue-600 dark:text-blue-300" : "text-slate-400 dark:text-slate-500"}`}>
                  {phaseLabel}
                </div>
              </div>
            ))}
          </div>

          <div className="mt-5 grid grid-cols-1 gap-3 md:grid-cols-3">
            {[
              placeholderCopy.shortTerm,
              placeholderCopy.mediumTerm,
              placeholderCopy.longTerm,
            ].map((label) => (
              <div key={label} className="rounded-2xl border border-slate-200 bg-white/80 p-4 dark:border-slate-800 dark:bg-slate-950/30">
                <div className="mb-1 text-[8px] font-black uppercase tracking-widest text-secondary opacity-70">
                  {label}
                </div>
                <div className="text-[11px] font-black uppercase tracking-tight text-slate-500 dark:text-slate-400">
                  {placeholderCopy.emptyTrend}
                </div>
              </div>
            ))}
          </div>

          <div className="mt-5 rounded-2xl border border-dashed border-slate-300 bg-white/70 px-4 py-4 text-sm font-medium text-slate-600 dark:border-slate-700 dark:bg-slate-950/30 dark:text-slate-300">
            {placeholderCopy.emptyFootnote}
          </div>
        </div>
      </div>
    );
  }

  return <MarketDecisionCard data={data} symbol={symbol} compact={compact} />;
}
