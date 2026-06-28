'use client';

import QuarterlyCyclePositionCard from '@/components/report/blocks/quarterly/QuarterlyCyclePositionCard';
import QuarterlyStrategyQualityCard from '@/components/report/blocks/quarterly/QuarterlyStrategyQualityCard';
import QuarterlyRiskDrawdownCard from '@/components/report/blocks/quarterly/QuarterlyRiskDrawdownCard';

import ReportSection from '@/components/report/sections/ReportSection';
import { useTranslation } from '@/app/providers/I18nProvider';

export default function QuarterlyReportLayout({ report }) {
  const { t } = useTranslation();
  if (!report) return null;

  const copy = t?.reports?.layouts?.quarterly || {};

  return (
    <div className="max-w-6xl mx-auto space-y-20">

      {/* =====================================================
          1️⃣ STRATEGISCH OVERZICHT (CARDS)
      ====================================================== */}
      <section className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <QuarterlyCyclePositionCard report={report} />
        <QuarterlyStrategyQualityCard report={report} />
        <QuarterlyRiskDrawdownCard report={report} />
      </section>

      {/* =====================================================
          2️⃣ DIEPGAANDE REFLECTIE
      ====================================================== */}
      <section className="max-w-3xl mx-auto space-y-14">

        <ReportSection title={copy.sections?.overview || 'Quarterly overview'}>
          <p className="leading-relaxed">
            {report.executive_summary || copy.fallbacks?.overview || 'No quarterly overview is available yet.'}
          </p>
        </ReportSection>

        <ReportSection title={copy.sections?.strategicLessons || 'Strategic lessons'}>
          <p className="leading-relaxed">
            {report.strategic_lessons || copy.fallbacks?.strategicLessons || 'No strategic lessons are available yet.'}
          </p>
        </ReportSection>

        <ReportSection title={copy.sections?.nextQuarterOutlook || 'Outlook for next quarter'}>
          <p className="leading-relaxed">
            {report.outlook || copy.fallbacks?.nextQuarterOutlook || 'No outlook is available yet.'}
          </p>
        </ReportSection>

      </section>

    </div>
  );
}
