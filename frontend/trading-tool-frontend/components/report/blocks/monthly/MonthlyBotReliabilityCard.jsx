'use client';

import ReportCard from '@/components/report/sections/ReportCard';
import { useTranslation } from '@/app/providers/I18nProvider';

export default function MonthlyBotReliabilityCard({ report }) {
  const { t } = useTranslation();
  const copy = t?.reports?.blocks?.monthlyBotReliability || {};
  if (!report) return null;

  return (
    <ReportCard title={copy.title}>
      <div className="space-y-4 text-sm">

        <BehaviorRow
          label={copy.selectivity}
          value={infer('selective', report.bot_performance, copy)}
        />

        <BehaviorRow
          label={copy.discipline}
          value={infer('discipline', report.bot_performance, copy)}
        />

        <BehaviorRow
          label={copy.activity}
          value={infer('activity', report.bot_performance, copy)}
        />

        <p className="pt-2 text-muted-foreground leading-relaxed">
          {report.bot_performance || copy.noEvaluation}
        </p>

      </div>
    </ReportCard>
  );
}

function BehaviorRow({ label, value }) {
  return (
    <div className="flex justify-between">
      <span className="text-muted-foreground">{label}</span>
      <span className="font-medium">{value}</span>
    </div>
  );
}

function infer(type, text = '', copy = {}) {
  const t = text.toLowerCase();

  if (type === 'selective') {
    if (t.includes('weinig') || t.includes('selectief')) return copy.high;
    if (t.includes('veel')) return copy.low;
  }

  if (type === 'discipline') {
    if (t.includes('consistent') || t.includes('gedisciplineerd')) return copy.consistent;
    if (t.includes('afwijk')) return copy.variable;
  }

  if (type === 'activity') {
    if (t.includes('actief')) return copy.active;
    if (t.includes('terughoudend') || t.includes('weinig')) return copy.low;
  }

  return copy.neutral;
}
