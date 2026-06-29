'use client';

import ReportCard from '@/components/report/sections/ReportCard';
import { useTranslation } from '@/app/providers/I18nProvider';

export default function QuarterlyStrategyQualityCard({ report }) {
  const { t } = useTranslation();
  const copy = t?.reports?.blocks?.quarterlyStrategyQuality || {};
  if (!report) return null;

  return (
    <ReportCard title={copy.title}>
      <div className="space-y-4 text-sm">

        <QualityRow
          label={copy.setups}
          value={grade(report.setup_performance, copy)}
        />

        <QualityRow
          label={copy.botExecution}
          value={grade(report.bot_performance, copy)}
        />

        <QualityRow
          label={copy.consistency}
          value={inferConsistency(report.strategic_lessons, copy)}
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

function grade(text = '', copy = {}) {
  const t = text.toLowerCase();
  if (t.includes('sterk') || t.includes('consistent')) return copy.strong;
  if (t.includes('gemengd') || t.includes('wisselend')) return copy.variable;
  if (t.includes('zwak') || t.includes('onder druk')) return copy.weak;
  return copy.neutral;
}

function inferConsistency(text = '', copy = {}) {
  const t = text.toLowerCase();
  if (t.includes('discipline') || t.includes('structuur')) return copy.high;
  if (t.includes('afwijk') || t.includes('emotie')) return copy.declining;
  return copy.average;
}
