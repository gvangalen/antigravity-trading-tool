'use client';

import ReportCard from '@/components/report/sections/ReportCard';

export default function QuarterlyStrategyQualityCard({ report }) {
  if (!report) return null;

  return (
    <ReportCard title="Strategiekwaliteit">
      <div className="space-y-4 text-sm">

        <QualityRow
          label="Setups"
          value={grade(report.setup_performance)}
        />

        <QualityRow
          label="Bot-executie"
          value={grade(report.bot_performance)}
        />

        <QualityRow
          label="Consistentie"
          value={inferConsistency(report.strategic_lessons)}
        />

      </div>
    </ReportCard>
  );
}

function QualityRow({ label, value }) {
  return (
    <div className="flex justify-between">
      <span className="text-muted-foreground">{label}</span>
      <span className="font-medium">{value}</span>
    </div>
  );
}

function grade(text = '') {
  const t = text.toLowerCase();
  if (t.includes('sterk') || t.includes('consistent')) return 'Sterk';
  if (t.includes('gemengd') || t.includes('wisselend')) return 'Wisselend';
  if (t.includes('zwak') || t.includes('onder druk')) return 'Zwak';
  return 'Neutraal';
}

function inferConsistency(text = '') {
  const t = text.toLowerCase();
  if (t.includes('discipline') || t.includes('structuur')) return 'Hoog';
  if (t.includes('afwijk') || t.includes('emotie')) return 'Afnemend';
  return 'Gemiddeld';
}
