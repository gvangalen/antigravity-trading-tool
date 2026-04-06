'use client';

import ReportCard from '@/components/report/sections/ReportCard';

export default function QuarterlyCyclePositionCard({ report }) {
  if (!report) return null;

  return (
    <ReportCard title="Cyclus & positionering">
      <div className="space-y-4 text-sm">

        <CycleRow
          label="Marktcyclus"
          value={inferCycle(report.market_overview)}
        />

        <CycleRow
          label="Macro-fase"
          value={inferMacro(report.macro_trends)}
        />

        <CycleRow
          label="Strategische houding"
          value={inferStance(report.executive_summary)}
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

function inferCycle(text = '') {
  const t = text.toLowerCase();
  if (t.includes('accumul')) return 'Accumulation / bodemvorming';
  if (t.includes('bull')) return 'Expansie / bullfase';
  if (t.includes('top') || t.includes('oververh')) return 'Distributie / verzwakking';
  if (t.includes('bear') || t.includes('dalend')) return 'Correctie / bearfase';
  return 'Overgangsfase';
}

function inferMacro(text = '') {
  const t = text.toLowerCase();
  if (t.includes('ondersteun')) return 'Ondersteunend';
  if (t.includes('verkrapp')) return 'Verkrappend';
  if (t.includes('neutraal')) return 'Neutraal';
  return 'Gemengd';
}

function inferStance(text = '') {
  const t = text.toLowerCase();
  if (t.includes('defens')) return 'Defensief';
  if (t.includes('selectief')) return 'Selectief offensief';
  if (t.includes('agress')) return 'Offensief';
  return 'Gebalanceerd';
}
