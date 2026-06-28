'use client';

import ReportCard from '@/components/report/sections/ReportCard';
import { useTranslation } from '@/app/providers/I18nProvider';

export default function QuarterlyRiskDrawdownCard({ report }) {
  const { t } = useTranslation();
  const copy = t?.reports?.blocks?.quarterlyRiskDrawdown || {};
  if (!report) return null;

  return (
    <ReportCard title={copy.title}>
      <div className="space-y-4 text-sm">

        <RiskRow
          label={copy.riskProfile}
          value={inferRisk(report.strategic_lessons, copy)}
        />

        <RiskRow
          label={copy.drawdownTolerance}
          value={inferDrawdown(report.strategic_lessons, copy)}
        />

        <RiskRow
          label={copy.capitalProtection}
          value={inferProtection(report.executive_summary, copy)}
        />

      </div>
    </ReportCard>
  );
}

function RiskRow({ label, value }) {
  return (
    <div className="flex justify-between">
      <span className="text-muted-foreground">{label}</span>
      <span className="font-medium">{value}</span>
    </div>
  );
}

function inferRisk(text = '', copy = {}) {
  const t = text.toLowerCase();
  if (t.includes('laag risico') || t.includes('defensief')) return copy.low;
  if (t.includes('verhoogd risico')) return copy.elevated;
  return copy.balanced;
}

function inferDrawdown(text = '', copy = {}) {
  const t = text.toLowerCase();
  if (t.includes('beperkt')) return copy.limited;
  if (t.includes('acceptabel')) return copy.acceptable;
  if (t.includes('hoog')) return copy.high;
  return copy.unknown;
}

function inferProtection(text = '', copy = {}) {
  const t = text.toLowerCase();
  if (t.includes('bescherm')) return copy.active;
  if (t.includes('blootstelling')) return copy.limited;
  return copy.neutral;
}
