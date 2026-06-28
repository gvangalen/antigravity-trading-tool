'use client';

import ReportCard from '@/components/report/sections/ReportCard';
import { useTranslation } from '@/app/providers/I18nProvider';

export default function MonthlyScoreStabilityCard({ report }) {
  const { t } = useTranslation();
  const copy = t?.reports?.blocks?.monthlyScoreStability || {};
  if (!report) return null;

  return (
    <ReportCard title={copy.title}>
      <div className="space-y-3 text-sm">

        <StabilityRow
          label={copy.macro}
          score={report.macro_score}
          copy={copy}
        />

        <StabilityRow
          label={copy.technical}
          score={report.technical_score}
          copy={copy}
        />

        <StabilityRow
          label={copy.setups}
          score={report.setup_score}
          copy={copy}
        />

      </div>
    </ReportCard>
  );
}

function StabilityRow({ label, score, copy }) {
  return (
    <div className="flex justify-between items-center">
      <span className="font-medium">{label}</span>
      <span className="text-muted-foreground">
        {interpret(score, copy)}
      </span>
    </div>
  );
}

function interpret(score, copy = {}) {
  if (score == null) return copy.noScore;

  if (score >= 75) return copy.consistentlyStrong;
  if (score >= 50) return copy.stableSelective;
  if (score >= 30) return copy.decliningConfidence;

  return copy.unstable;
}
