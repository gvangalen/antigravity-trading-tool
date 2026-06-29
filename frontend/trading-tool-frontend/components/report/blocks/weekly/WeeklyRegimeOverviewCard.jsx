'use client';

import ReportCard from '@/components/report/sections/ReportCard';
import { ArrowDown, ArrowRight, ArrowUp } from 'lucide-react';
import { useTranslation } from '@/app/providers/I18nProvider';

/**
 * WeeklyRegimeOverviewCard
 * --------------------------------------------------
 * Doel:
 * - In 5 seconden snappen: hoe stond de week ervoor?
 * - Afgeleid uit bestaande weekly report tekst
 * - Geen backend-wijzigingen nodig
 */
export default function WeeklyRegimeOverviewCard({ report }) {
  const { t } = useTranslation();
  const copy = t?.reports?.blocks?.weeklyRegime || {};
  if (!report) return null;

  const regime = deriveWeeklyRegime(report, copy);

  return (
    <ReportCard title={copy.title}>
      <div className="grid grid-cols-2 gap-4">

        <RegimePill
          label={copy.market}
          value={regime.market.label}
          tone={regime.market.tone}
          icon={regime.market.icon}
        />

        <RegimePill
          label={copy.macro}
          value={regime.macro.label}
          tone={regime.macro.tone}
          icon={regime.macro.icon}
        />

        <RegimePill
          label={copy.technical}
          value={regime.technical.label}
          tone={regime.technical.tone}
          icon={regime.technical.icon}
        />

        <RegimePill
          label={copy.setups}
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

function deriveWeeklyRegime(report, copy = {}) {
  return {
    market: deriveFromText(report.market_overview, copy),
    macro: deriveFromText(report.macro_trends, copy),
    technical: deriveFromText(report.technical_structure, copy),
    setups: deriveFromText(report.setup_performance, copy),
  };
}

function deriveFromText(text = '', copy = {}) {
  const t = text.toLowerCase();

  if (t.includes('bear') || t.includes('zwak') || t.includes('druk')) {
    return {
      label: copy.bearish,
      tone: 'negative',
      icon: ArrowDown,
    };
  }

  if (t.includes('bull') || t.includes('sterk') || t.includes('impuls')) {
    return {
      label: copy.bullish,
      tone: 'positive',
      icon: ArrowUp,
    };
  }

  return {
    label: copy.neutral,
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
