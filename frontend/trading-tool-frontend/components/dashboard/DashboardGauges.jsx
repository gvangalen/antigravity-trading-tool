"use client";

import React from "react";
import { useScoresData } from "@/hooks/useScoresData";
import GaugeChart from "@/components/ui/GaugeChart";
import TopSetupsMini from "@/components/setup/TopSetupsMini";
import CardWrapper from "@/components/ui/CardWrapper";
import { useTranslation } from "@/app/providers/I18nProvider";

// Icons
import { Globe2, LineChart, DollarSign, Settings2 } from "lucide-react";

/* =====================================================
   SCORE → TEKST (DE ENIGE WAARHEID)
===================================================== */

export default function DashboardGauges() {
  const { t } = useTranslation();
  const { macro, technical, market, setup } = useScoresData();
  const gaugesT = t?.dashboard?.gauges || {};

  const gauges = [
    {
      key: "macro",
      title: gaugesT.macro,
      icon: <Globe2 className="w-4 h-4" />,
      data: macro,
      emptyText: gaugesT.emptyState?.macro,
    },
    {
      key: "technical",
      title: gaugesT.technical,
      icon: <LineChart className="w-4 h-4" />,
      data: technical,
      emptyText: gaugesT.emptyState?.technical,
    },
    {
      key: "market",
      title: gaugesT.market,
      icon: <DollarSign className="w-4 h-4" />,
      data: market,
      emptyText: gaugesT.emptyState?.market,
    },
    {
      key: "setup",
      title: gaugesT.setup,
      icon: <Settings2 className="w-4 h-4" />,
      data: setup,
      emptyText: gaugesT.emptyState?.setup,
      showTopSetups: true,
    },
  ];

  return (
    <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
      {gauges.map((g, idx) => (
        <GaugeCard
          key={idx}
          areaKey={g.key}
          title={g.title}
          icon={g.icon}
          data={g.data}
          emptyText={g.emptyText}
          showTopSetups={g.showTopSetups}
        />
      ))}
    </div>
  );
}

/* =====================================================
   SINGLE GAUGE CARD
===================================================== */

function GaugeCard({ areaKey, title, icon, data, emptyText, showTopSetups = false }) {
  const { t } = useTranslation();
  const gaugesT = t?.dashboard?.gauges || {};
  const score = typeof data?.score === "number" ? data.score : null;

  const numericScore = score ?? 0;
  const displayScore = Math.round(numericScore);

  // 🔒 DEFINITIEVE TEKSTLOGICA (score → tekst)
  const explanationMap = {
    macro: {
      strong: gaugesT.explanations?.macroStrong,
      weak: gaugesT.explanations?.macroWeak,
      neutral: gaugesT.explanations?.macroNeutral,
    },
    technical: {
      strong: gaugesT.explanations?.technicalStrong,
      weak: gaugesT.explanations?.technicalWeak,
      neutral: gaugesT.explanations?.technicalNeutral,
    },
    market: {
      strong: gaugesT.explanations?.marketStrong,
      weak: gaugesT.explanations?.marketWeak,
      neutral: gaugesT.explanations?.marketNeutral,
    },
    setup: {
      strong: gaugesT.explanations?.setupStrong,
      weak: gaugesT.explanations?.setupWeak,
      neutral: gaugesT.explanations?.setupNeutral,
    },
  };

  const displayExplanation =
    score === null
      ? emptyText
      : score >= 75
        ? explanationMap[areaKey]?.strong
        : score < 40
          ? explanationMap[areaKey]?.weak
          : explanationMap[areaKey]?.neutral;

  const topContributors = Array.isArray(data?.top_contributors)
    ? data.top_contributors
    : [];

  const hasSetups = showTopSetups && topContributors.length > 0;

  return (
    <CardWrapper>
      {/* HEADER */}
      <div className="flex items-center gap-2 mb-3">
        <div
          className="
            h-7 w-7 rounded-full
            border border-[var(--card-border)]
            flex items-center justify-center
            text-[var(--text-light)]
            text-xs
          "
        >
          {icon}
        </div>
        <h2 className="text-sm font-semibold text-[var(--text-dark)] tracking-tight">
          {title}
        </h2>
        {score !== null && (
          <button 
            onClick={() => window.dispatchEvent(new CustomEvent("open-ai-assistant", { 
              detail: { query: gaugesT.askFinn.replace("{title}", title).replace("{score}", String(displayScore)) } 
            }))}
            className="ml-auto text-[9px] font-black uppercase tracking-widest px-2 py-1 rounded bg-[var(--color-border-subtle)] border border-slate-100 text-secondary hover:text-[var(--primary)] hover:border-[var(--primary)] hover:bg-white transition-all shadow-sm"
          >
            {gaugesT.explain}
          </button>
        )}
      </div>

      {/* GAUGE */}
      <div className="flex flex-col items-center justify-center mt-1 mb-2">
        <GaugeChart value={numericScore} displayValue={displayScore} />
      </div>

      {/* CONTRIBUTORS */}
      {topContributors.length > 0 && (
        <div className="mt-3">
          <p className="text-[11px] font-medium text-[var(--text-light)] uppercase tracking-wide mb-1">
            {gaugesT.topContributors}
          </p>

          <div className="space-y-1">
            {topContributors.map((c, i) => (
              <div
                key={i}
                className="
                  text-xs text-[var(--text-dark)]
                  pl-1 border-l-2 border-[var(--primary)]
                "
              >
                {c}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* TOP SETUPS */}
      {hasSetups && (
        <div className="mt-4">
          <TopSetupsMini />
        </div>
      )}

      {/* EXPLANATION */}
      <p className="mt-3 text-[11px] leading-relaxed text-[var(--text-light)] italic">
        {displayExplanation}
      </p>
    </CardWrapper>
  );
}
