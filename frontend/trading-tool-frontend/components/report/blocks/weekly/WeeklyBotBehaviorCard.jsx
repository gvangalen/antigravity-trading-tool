'use client';

import ReportCard from '@/components/report/sections/ReportCard';

/**
 * WeeklyBotBehaviorCard — v2.0
 * --------------------------------------------------
 * Doel:
 * - In 1 oogopslag zien HOE de bot zich gedroeg
 * - Geen trade-lijst, maar gedragskwaliteit
 * - Ondersteunende context uit bot_performance
 *
 * Gebruikte report keys:
 * - bot_performance (tekst)
 * - setup_score (indirecte selectiviteit)
 * - technical_score (discipline / volgen structuur)
 */
export default function WeeklyBotBehaviorCard({ report }) {
  if (!report) return null;

  const activity = deriveActivity(report);
  const selectivity = deriveSelectivity(report);
  const discipline = deriveDiscipline(report);

  return (
    <ReportCard title="Botgedrag (Week)">
      <div className="space-y-4">

        {/* GEDRAGSOVERZICHT */}
        <div className="grid grid-cols-3 gap-3 text-sm">
          <BehaviorPill
            label="Activiteit"
            value={activity.label}
            tone={activity.tone}
          />
          <BehaviorPill
            label="Selectiviteit"
            value={selectivity.label}
            tone={selectivity.tone}
          />
          <BehaviorPill
            label="Discipline"
            value={discipline.label}
            tone={discipline.tone}
          />
        </div>

        {/* CONTEXT */}
        {report.bot_performance && (
          <p className="text-sm leading-relaxed text-muted-foreground">
            {report.bot_performance}
          </p>
        )}

      </div>
    </ReportCard>
  );
}

/* =====================================================
   🔹 Behavior logic (frontend-only, safe defaults)
===================================================== */

function deriveActivity(report) {
  // Later: echte trade-counts
  if (!report.bot_performance) {
    return { label: 'Onbekend', tone: 'neutral' };
  }

  const text = report.bot_performance.toLowerCase();

  if (text.includes('weinig') || text.includes('terughoudend')) {
    return { label: 'Laag', tone: 'neutral' };
  }
  if (text.includes('actief') || text.includes('meerdere')) {
    return { label: 'Hoog', tone: 'positive' };
  }

  return { label: 'Gemiddeld', tone: 'neutral' };
}

function deriveSelectivity(report) {
  const score = report.setup_score;

  if (typeof score !== 'number') {
    return { label: 'Onbekend', tone: 'neutral' };
  }

  if (score >= 65) {
    return { label: 'Hoog', tone: 'positive' };
  }
  if (score <= 45) {
    return { label: 'Laag', tone: 'negative' };
  }

  return { label: 'Gemiddeld', tone: 'neutral' };
}

function deriveDiscipline(report) {
  const score = report.technical_score;

  if (typeof score !== 'number') {
    return { label: 'Onbekend', tone: 'neutral' };
  }

  if (score >= 65) {
    return { label: 'Consistent', tone: 'positive' };
  }
  if (score <= 45) {
    return { label: 'Wisselend', tone: 'negative' };
  }

  return { label: 'Redelijk', tone: 'neutral' };
}

/* =====================================================
   🔹 UI helpers
===================================================== */

function BehaviorPill({ label, value, tone }) {
  const toneClass =
    tone === 'positive'
      ? 'border-emerald-500/40 bg-emerald-500/5 text-emerald-600'
      : tone === 'negative'
      ? 'border-red-500/40 bg-red-500/5 text-red-600'
      : 'border-border bg-muted text-foreground';

  return (
    <div className={`rounded-lg border px-3 py-2 ${toneClass}`}>
      <div className="text-xs text-muted-foreground">{label}</div>
      <div className="font-medium">{value}</div>
    </div>
  );
}
