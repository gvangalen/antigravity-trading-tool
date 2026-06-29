'use client';

import ReportCard from '@/components/report/sections/ReportCard';
import { useTranslation } from '@/app/providers/I18nProvider';

export default function QuarterlyCyclePositionCard({ report }) {
  const { t } = useTranslation();
  const copy = t?.reports?.blocks?.quarterlyCyclePosition || {};
  if (!report) return null;

  return (
    <ReportCard title={copy.title}>
      <div className="space-y-4 text-sm">

        <CycleRow
          label={copy.marketCycle}
          value={inferCycle(report.market_overview, copy)}
        />

        <CycleRow
          label={copy.macroPhase}
          value={inferMacro(report.macro_trends, copy)}
        />

        <CycleRow
          label={copy.strategicStance}
          value={inferStance(report.executive_summary, copy)}
        />

      </div>
    </ReportCard>
  );
}

function CycleRow({ label, value }) {
  return (
    <div className="flex justify-between items-start gap-4">
      <span className="text-muted-foreground">{label}</span>
      <span className="font-medium text-right">{value}</span>
    </div>
  );
}

function inferCycle(text = '', copy = {}) {
  const t = text.toLowerCase();
  if (t.includes('accumul')) return copy.accumulation;
  if (t.includes('bull')) return copy.expansion;
  if (t.includes('top') || t.includes('oververh')) return copy.distribution;
  if (t.includes('bear') || t.includes('dalend')) return copy.correction;
  return copy.transition;
}

function inferMacro(text = '', copy = {}) {
  const t = text.toLowerCase();
  if (t.includes('ondersteun')) return copy.supportive;
  if (t.includes('verkrapp')) return copy.tightening;
  if (t.includes('neutraal')) return copy.neutral;
  return copy.mixed;
}

function inferStance(text = '', copy = {}) {
  const t = text.toLowerCase();
  if (t.includes('defens')) return copy.defensive;
  if (t.includes('selectief')) return copy.selectiveOffensive;
  if (t.includes('agress')) return copy.offensive;
  return copy.balanced;
}
