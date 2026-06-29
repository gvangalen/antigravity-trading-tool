'use client';

import ReportCard from '@/components/report/sections/ReportCard';
import { useTranslation } from '@/app/providers/I18nProvider';

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
  const { t } = useTranslation();
  const copy = t?.reports?.blocks?.weeklyScoreTrend || {};
  if (!report) return null;

  return (
    <ReportCard title={copy.title}>
      <div className="space-y-4">

        <ScoreRow
          label={copy.macro}
          score={report.macro_score}
          copy={copy}
        />

        <ScoreRow
          label={copy.technical}
          score={report.technical_score}
          copy={copy}
        />

        <ScoreRow
          label={copy.setups}
          score={report.setup_score}
          copy={copy}
        />

      </div>
    </ReportCard>
  );
}

/* =====================================================
   🔹 Helpers
===================================================== */

function ScoreRow({ label, score, copy }) {
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
            {trendLabel(trend, copy)}
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
        {safeScore !== null ? `${copy.scoreLabel}: ${safeScore}` : copy.noScore}
      </div>

    </div>
  );
}

function trendLabel(trend, copy = {}) {
  switch (trend) {
    case 'up':
      return copy.up;
    case 'down':
      return copy.down;
    default:
      return copy.flat;
  }
}
