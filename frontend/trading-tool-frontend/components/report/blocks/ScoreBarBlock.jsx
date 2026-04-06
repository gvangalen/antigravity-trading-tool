"use client";

import ReportCard from "../ReportCard";
import { Activity } from "lucide-react";

/* =====================================================
   HELPERS
===================================================== */

function normalizeScore(value) {
  if (value === null || value === undefined) return null;

  if (typeof value === "number") {
    return Math.round(value);
  }

  if (typeof value === "string") {
    const v = value.trim();
    return v.length ? v : null;
  }

  return null;
}

/* =====================================================
   UI SUBCOMPONENTS
===================================================== */

function ScoreRow({ label, value }) {
  const v = normalizeScore(value);
  if (v === null) return null;

  return (
    <div className="flex items-center justify-between">
      <span className="text-sm text-[var(--text-light)]">
        {label}
      </span>
      <span className="text-base font-semibold text-[var(--text-dark)]">
        {v}
      </span>
    </div>
  );
}

function ScoreDivider() {
  return <div className="h-px bg-gray-100 my-1" />;
}

/* =====================================================
   BLOCK — Scores (2.0)
   - rust
   - hiërarchie
   - dashboard-waardig
===================================================== */

export default function ScoreBarBlock({ report }) {
  if (!report || typeof report !== "object") return null;

  const {
    macro_score,
    technical_score,
    market_score,
    setup_score,
  } = report;

  // 🔒 niets renderen als alles ontbreekt
  const hasAny =
    macro_score !== undefined ||
    technical_score !== undefined ||
    market_score !== undefined ||
    setup_score !== undefined;

  if (!hasAny) return null;

  return (
    <ReportCard
      icon={<Activity size={18} />}
      title="Scores"
    >
      <div className="space-y-3">
        <ScoreRow label="Macro" value={macro_score} />
        <ScoreDivider />

        <ScoreRow label="Technical" value={technical_score} />
        <ScoreDivider />

        <ScoreRow label="Market" value={market_score} />
        <ScoreDivider />

        <ScoreRow label="Setup" value={setup_score} />
      </div>
    </ReportCard>
  );
}
