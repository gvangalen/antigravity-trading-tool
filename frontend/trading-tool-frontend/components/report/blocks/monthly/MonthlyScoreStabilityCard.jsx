'use client';

import ReportCard from '@/components/report/sections/ReportCard';

export default function MonthlyScoreStabilityCard({ report }) {
  if (!report) return null;

  return (
    <ReportCard title="Score-stabiliteit">
      <div className="space-y-3 text-sm">

        <StabilityRow
          label="Macro"
          score={report.macro_score}
        />

        <StabilityRow
          label="Technisch"
          score={report.technical_score}
        />

        <StabilityRow
          label="Setups"
          score={report.setup_score}
        />

      </div>
    </ReportCard>
  );
}

function StabilityRow({ label, score }) {
  return (
    <div className="flex justify-between items-center">
      <span className="font-medium">{label}</span>
      <span className="text-muted-foreground">
        {interpret(score)}
      </span>
    </div>
  );
}

function interpret(score) {
  if (score == null) return 'Geen score';

  if (score >= 75) return 'Consistent sterk';
  if (score >= 50) return 'Stabiel maar selectief';
  if (score >= 30) return 'Afnemend vertrouwen';

  return 'Instabiel / onbetrouwbaar';
}
