'use client';

import ReportCard from '@/components/report/sections/ReportCard';

export default function MonthlyBotReliabilityCard({ report }) {
  if (!report) return null;

  return (
    <ReportCard title="Botbetrouwbaarheid">
      <div className="space-y-4 text-sm">

        <BehaviorRow
          label="Selectiviteit"
          value={infer('selective', report.bot_performance)}
        />

        <BehaviorRow
          label="Discipline"
          value={infer('discipline', report.bot_performance)}
        />

        <BehaviorRow
          label="Activiteit"
          value={infer('activity', report.bot_performance)}
        />

        <p className="pt-2 text-muted-foreground leading-relaxed">
          {report.bot_performance || 'Geen bot-evaluatie beschikbaar.'}
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

function infer(type, text = '') {
  const t = text.toLowerCase();

  if (type === 'selective') {
    if (t.includes('weinig') || t.includes('selectief')) return 'Hoog';
    if (t.includes('veel')) return 'Laag';
  }

  if (type === 'discipline') {
    if (t.includes('consistent') || t.includes('gedisciplineerd')) return 'Consistent';
    if (t.includes('afwijk')) return 'Wisselend';
  }

  if (type === 'activity') {
    if (t.includes('actief')) return 'Actief';
    if (t.includes('terughoudend') || t.includes('weinig')) return 'Laag';
  }

  return 'Neutraal';
}
