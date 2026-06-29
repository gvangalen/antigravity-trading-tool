'use client';

import ReportCard from '@/components/report/sections/ReportCard';
import { useTranslation } from '@/app/providers/I18nProvider';

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
  const { t } = useTranslation();
  const copy = t?.reports?.blocks?.weeklyBotBehavior || {};
  if (!report) return null;

  const activity = deriveActivity(report, copy);
  const selectivity = deriveSelectivity(report, copy);
  const discipline = deriveDiscipline(report, copy);

  return (
    <ReportCard title={copy.title}>
      <div className="space-y-4">

        {/* GEDRAGSOVERZICHT */}
        <div className="grid grid-cols-3 gap-3 text-sm">
          <BehaviorPill
            label={copy.activity}
            value={activity.label}
            tone={activity.tone}
          />
          <BehaviorPill
            label={copy.selectivity}
            value={selectivity.label}
            tone={selectivity.tone}
          />
          <BehaviorPill
            label={copy.discipline}
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

function deriveActivity(report, copy = {}) {
  // Later: echte trade-counts
  if (!report.bot_performance) {
    return { label: copy.unknown, tone: 'neutral' };
  }

  const text = report.bot_performance.toLowerCase();

  if (text.includes('weinig') || text.includes('terughoudend')) {
    return { label: copy.low, tone: 'neutral' };
  }
  if (text.includes('actief') || text.includes('meerdere')) {
    return { label: copy.high, tone: 'positive' };
  }

  return { label: copy.average, tone: 'neutral' };
}

function deriveSelectivity(report, copy = {}) {
  const score = report.setup_score;

  if (typeof score !== 'number') {
    return { label: copy.unknown, tone: 'neutral' };
  }

  if (score >= 65) {
    return { label: copy.high, tone: 'positive' };
  }
  if (score <= 45) {
    return { label: copy.low, tone: 'negative' };
  }

  return { label: copy.average, tone: 'neutral' };
}

function deriveDiscipline(report, copy = {}) {
  const score = report.technical_score;

  if (typeof score !== 'number') {
    return { label: copy.unknown, tone: 'neutral' };
  }

  if (score >= 65) {
    return { label: copy.consistent, tone: 'positive' };
  }
  if (score <= 45) {
    return { label: copy.variable, tone: 'negative' };
  }

  return { label: copy.fair, tone: 'neutral' };
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
