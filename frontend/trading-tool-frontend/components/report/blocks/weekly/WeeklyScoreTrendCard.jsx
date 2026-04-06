'use client';

import ReportCard from '@/components/report/sections/ReportCard';

/**
 * WeeklyScoreTrendCard — v2.0
 * --------------------------------------------------
 * Doel:
 * - In één oogopslag zien waar momentum zit
 * - Minder tekst, meer visuele richting
 * - Week-context (geen intraday ruis)
 *
 * Verwachte report keys:
 * - macro_score
 * - technical_score
 * - setup_score
 * - (optioneel later: market_score, sentiment_score)
 */
export default function WeeklyScoreTrendCard({ report }) {
  if (!report) return null;

  return (
    <ReportCard title="Scoretrend (Week)">
      <div className="space-y-4">

        <ScoreRow
          label="Macro"
          score={report.macro_score}
        />

        <ScoreRow
          label="Technisch"
          score={report.technical_score}
        />

        <ScoreRow
          label="Setups"
          score={report.setup_score}
        />

      </div>
    </ReportCard>
  );
}

/* =====================================================
   🔹 Helpers
===================================================== */

function ScoreRow({ label, score }) {
  const safeScore = typeof score === 'number' ? score : null;

  const trend =
    safeScore === null ? 'neutral'
    : safeScore >= 65 ? 'up'
    : safeScore <= 45 ? 'down'
    : 'flat';

  const trendIcon =
    trend === 'up' ? '↗'
    : trend === 'down' ? '↘'
    : '→';

  const trendColor =
    trend === 'up'
      ? 'text-emerald-500'
      : trend === 'down'
      ? 'text-red-500'
      : 'text-muted-foreground';

  return (
    <div className="space-y-1">

      {/* Label + trend */}
      <div className="flex items-center justify-between text-sm">
        <span className="font-medium">{label}</span>

        <span className={`flex items-center gap-1 ${trendColor}`}>
          <span className="text-base">{trendIcon}</span>
          <span className="text-xs">
            {trendLabel(trend)}
          </span>
        </span>
      </div>

      {/* Score bar */}
      <div className="h-2 w-full rounded bg-muted overflow-hidden">
        {safeScore !== null && (
          <div
            className="h-full rounded bg-primary transition-all"
            style={{ width: `${Math.min(Math.max(safeScore, 0), 100)}%` }}
          />
        )}
      </div>

      {/* Score value */}
      <div className="text-xs text-muted-foreground">
        {safeScore !== null ? `Score: ${safeScore}` : 'Geen score beschikbaar'}
      </div>

    </div>
  );
}

function trendLabel(trend) {
  switch (trend) {
    case 'up':
      return 'Versterkend';
    case 'down':
      return 'Verzwakkend';
    default:
      return 'Zijwaarts';
  }
}
