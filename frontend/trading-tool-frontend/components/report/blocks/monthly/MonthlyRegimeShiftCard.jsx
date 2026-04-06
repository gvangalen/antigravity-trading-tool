'use client';

import ReportCard from '@/components/report/sections/ReportCard';

export default function MonthlyRegimeShiftCard({ report }) {
  if (!report) return null;

  return (
    <ReportCard title="Marktregime (Maand)">
      <div className="space-y-4 text-sm">

        <RegimeRow
          label="Marktstructuur"
          value={extract(report.market_overview)}
        />

        <RegimeRow
          label="Macro-omgeving"
          value={extract(report.macro_trends)}
        />

        <RegimeRow
          label="Technisch regime"
          value={extract(report.technical_structure)}
        />

      </div>
    </ReportCard>
  );
}

function RegimeRow({ label, value }) {
  return (
    <div className="flex justify-between items-start gap-4">
      <span className="text-muted-foreground">{label}</span>
      <span className="font-medium text-right">{value}</span>
    </div>
  );
}

/**
 * Semantische extractie:
 * we tonen GEEN ruwe tekst, maar een compacte interpretatie
 */
function extract(text) {
  if (!text) return 'Onvoldoende data';

  if (/bear|zwak|druk/i.test(text)) return 'Bearish / defensief';
  if (/bull|sterk|opbouw/i.test(text)) return 'Bullish / ondersteunend';
  if (/range|neutraal|consolid/i.test(text)) return 'Neutraal / range';

  return 'Gemengd / overgangsfase';
}
