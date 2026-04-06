'use client';

import ReportCard from '@/components/report/sections/ReportCard';
import { ArrowDown, ArrowRight, ArrowUp } from 'lucide-react';

/**
 * WeeklyRegimeOverviewCard
 * --------------------------------------------------
 * Doel:
 * - In 5 seconden snappen: hoe stond de week ervoor?
 * - Afgeleid uit bestaande weekly report tekst
 * - Geen backend-wijzigingen nodig
 */
export default function WeeklyRegimeOverviewCard({ report }) {
  if (!report) return null;

  const regime = deriveWeeklyRegime(report);

  return (
    <ReportCard title="Weekregime Overzicht">
      <div className="grid grid-cols-2 gap-4">

        <RegimePill
          label="Markt"
          value={regime.market.label}
          tone={regime.market.tone}
          icon={regime.market.icon}
        />

        <RegimePill
          label="Macro"
          value={regime.macro.label}
          tone={regime.macro.tone}
          icon={regime.macro.icon}
        />

        <RegimePill
          label="Technisch"
          value={regime.technical.label}
          tone={regime.technical.tone}
          icon={regime.technical.icon}
        />

        <RegimePill
          label="Setups"
          value={regime.setups.label}
          tone={regime.setups.tone}
          icon={regime.setups.icon}
        />

      </div>
    </ReportCard>
  );
}

/* ======================================================
 * Helpers — regime afleiding
 * ====================================================== */

function deriveWeeklyRegime(report) {
  return {
    market: deriveFromText(report.market_overview),
    macro: deriveFromText(report.macro_trends),
    technical: deriveFromText(report.technical_structure),
    setups: deriveFromText(report.setup_performance),
  };
}

function deriveFromText(text = '') {
  const t = text.toLowerCase();

  if (t.includes('bear') || t.includes('zwak') || t.includes('druk')) {
    return {
      label: 'Bearish / defensief',
      tone: 'negative',
      icon: ArrowDown,
    };
  }

  if (t.includes('bull') || t.includes('sterk') || t.includes('impuls')) {
    return {
      label: 'Bullish / momentum',
      tone: 'positive',
      icon: ArrowUp,
    };
  }

  return {
    label: 'Neutraal / range',
    tone: 'neutral',
    icon: ArrowRight,
  };
}

/* ======================================================
 * UI component
 * ====================================================== */

function RegimePill({ label, value, tone = 'neutral', icon: Icon }) {
  const toneStyles = {
    positive: 'border-green-500/40 bg-green-500/5 text-green-600',
    negative: 'border-red-500/40 bg-red-500/5 text-red-600',
    neutral: 'border-muted bg-muted/40 text-foreground',
  };

  return (
    <div className={`rounded-lg border px-3 py-3 ${toneStyles[tone]}`}>
      <div className="flex items-center justify-between">
        <div>
          <div className="text-xs text-muted-foreground">{label}</div>
          <div className="font-medium">{value}</div>
        </div>
        {Icon && <Icon className="h-4 w-4 opacity-70" />}
      </div>
    </div>
  );
}
