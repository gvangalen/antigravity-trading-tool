"use client";

import React from "react";
import { useScoresData } from "@/hooks/useScoresData";
import GaugeChart from "@/components/ui/GaugeChart";
import TopSetupsMini from "@/components/setup/TopSetupsMini";
import CardWrapper from "@/components/ui/CardWrapper";

// Icons
import { Globe2, LineChart, DollarSign, Settings2 } from "lucide-react";

/* =====================================================
   SCORE → TEKST (DE ENIGE WAARHEID)
===================================================== */

const SCORE_TEXT = {
  Macro: (score) => {
    if (score >= 75)
      return "Macro-omgeving is duidelijk ondersteunend voor risico-assets.";
    if (score < 40)
      return "Macro-omgeving is ongunstig en verhoogt neerwaarts risico.";
    return "Macro-omgeving is neutraal en geeft geen duidelijke richting.";
  },
  Technical: (score) => {
    if (score >= 75)
      return "Technische structuur is sterk en ondersteunt hogere prijzen.";
    if (score < 40)
      return "Technische structuur is zwak en vraagt om voorzichtigheid.";
    return "Technische signalen zijn gemengd zonder duidelijke trend.";
  },
  Market: (score) => {
    if (score >= 75)
      return "Marktdynamiek is positief met ondersteunend momentum.";
    if (score < 40)
      return "Marktdynamiek is zwak en mist overtuiging.";
    return "Marktdynamiek is zijwaarts en afwachtend.";
  },
  Setup: (score) => {
    if (score >= 75)
      return "Meerdere setups zijn actief en kansrijk.";
    if (score < 40)
      return "Weinig of geen setups voldoen aan de voorwaarden.";
    return "Beperkt aantal setups actief, selectief handelen.";
  },
};

/* =====================================================
   DASHBOARD GAUGES
===================================================== */

export default function DashboardGauges() {
  const { macro, technical, market, setup } = useScoresData();

  const gauges = [
    {
      title: "Macro",
      icon: <Globe2 className="w-4 h-4" />,
      data: macro,
      emptyText:
        "Nog geen macrodata beschikbaar. Voeg macro-indicatoren toe op de Macro-pagina.",
    },
    {
      title: "Technical",
      icon: <LineChart className="w-4 h-4" />,
      data: technical,
      emptyText:
        "Nog geen technische analyse beschikbaar. Voeg indicatoren toe op de Technisch-pagina.",
    },
    {
      title: "Market",
      icon: <DollarSign className="w-4 h-4" />,
      data: market,
      emptyText:
        "Nog geen marktdata beschikbaar. Market data wordt automatisch opgehaald.",
    },
    {
      title: "Setup",
      icon: <Settings2 className="w-4 h-4" />,
      data: setup,
      emptyText:
        "Geen actieve setups gevonden. Maak een setup aan op de Setup-pagina.",
      showTopSetups: true,
    },
  ];

  return (
    <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
      {gauges.map((g, idx) => (
        <GaugeCard
          key={idx}
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

function GaugeCard({ title, icon, data, emptyText, showTopSetups = false }) {
  const score = typeof data?.score === "number" ? data.score : null;

  const numericScore = score ?? 0;
  const displayScore = Math.round(numericScore);

  // 🔒 DEFINITIEVE TEKSTLOGICA (score → tekst)
  const displayExplanation =
    score === null ? emptyText : (SCORE_TEXT[title] ? SCORE_TEXT[title](score) : emptyText);

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
      </div>

      {/* GAUGE */}
      <div className="flex flex-col items-center justify-center mt-1 mb-2">
        <GaugeChart value={numericScore} displayValue={displayScore} />
      </div>

      {/* CONTRIBUTORS */}
      {topContributors.length > 0 && (
        <div className="mt-3">
          <p className="text-[11px] font-medium text-[var(--text-light)] uppercase tracking-wide mb-1">
            Top bijdragen
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
