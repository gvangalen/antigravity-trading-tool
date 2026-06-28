'use client';

import ReportCard from '@/components/report/sections/ReportCard';
import { useTranslation } from '@/app/providers/I18nProvider';

export default function MonthlyRegimeShiftCard({ report }) {
  const { t } = useTranslation();
  const copy = t?.reports?.blocks?.monthlyRegimeShift || {};
  if (!report) return null;

  return (
    <ReportCard title={copy.title}>
      <div className="space-y-4 text-sm">

        <RegimeRow
          label={copy.marketStructure}
          value={extract(report.market_overview, copy)}
        />

        <RegimeRow
          label={copy.macroEnvironment}
          value={extract(report.macro_trends, copy)}
        />

        <RegimeRow
          label={copy.technicalRegime}
          value={extract(report.technical_structure, copy)}
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
function extract(text, copy = {}) {
  if (!text) return copy.insufficientData;

  if (/bear|zwak|druk/i.test(text)) return copy.bearish;
  if (/bull|sterk|opbouw/i.test(text)) return copy.bullish;
  if (/range|neutraal|consolid/i.test(text)) return copy.neutral;

  return copy.mixed;
}
