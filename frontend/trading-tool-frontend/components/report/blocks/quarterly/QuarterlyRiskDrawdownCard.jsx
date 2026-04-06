'use client';

import ReportCard from '@/components/report/sections/ReportCard';

export default function QuarterlyRiskDrawdownCard({ report }) {
  if (!report) return null;

  return (
    <ReportCard title="Risico & robuustheid">
      <div className="space-y-4 text-sm">

        <RiskRow
          label="Risicoprofiel"
          value={inferRisk(report.strategic_lessons)}
        />

        <RiskRow
          label="Drawdown-tolerantie"
          value={inferDrawdown(report.strategic_lessons)}
        />

        <RiskRow
          label="Kapitaalbescherming"
          value={inferProtection(report.executive_summary)}
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

function inferRisk(text = '') {
  const t = text.toLowerCase();
  if (t.includes('laag risico') || t.includes('defensief')) return 'Laag';
  if (t.includes('verhoogd risico')) return 'Verhoogd';
  return 'Gebalanceerd';
}

function inferDrawdown(text = '') {
  const t = text.toLowerCase();
  if (t.includes('beperkt')) return 'Beperkt';
  if (t.includes('acceptabel')) return 'Acceptabel';
  if (t.includes('hoog')) return 'Hoog';
  return 'Onbekend';
}

function inferProtection(text = '') {
  const t = text.toLowerCase();
  if (t.includes('bescherm')) return 'Actief';
  if (t.includes('blootstelling')) return 'Beperkt';
  return 'Neutraal';
}
