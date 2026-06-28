'use client';

import MonthlyRegimeShiftCard from '@/components/report/blocks/monthly/MonthlyRegimeShiftCard';
import MonthlyScoreStabilityCard from '@/components/report/blocks/monthly/MonthlyScoreStabilityCard';
import MonthlyBotReliabilityCard from '@/components/report/blocks/monthly/MonthlyBotReliabilityCard';

import ReportSection from '@/components/report/sections/ReportSection';
import { useTranslation } from '@/app/providers/I18nProvider';

export default function MonthlyReportLayout({ report }) {
  const { t } = useTranslation();
  if (!report) return null;

  const copy = t?.reports?.layouts?.monthly || {};

  return (
    <div className="max-w-6xl mx-auto space-y-16">

      {/* =====================================================
          1️⃣ VISUELE SAMENVATTING
      ====================================================== */}
      <section className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <MonthlyRegimeShiftCard report={report} />
        <MonthlyScoreStabilityCard report={report} />
        <MonthlyBotReliabilityCard report={report} />
      </section>

      {/* =====================================================
          2️⃣ STRATEGISCHE CONTEXT
      ====================================================== */}
      <section className="max-w-3xl mx-auto space-y-12">

        <ReportSection title={copy.sections?.overview || 'Monthly overview'}>
          <p className="leading-relaxed">
            {report.executive_summary || copy.fallbacks?.overview || 'No monthly overview is available yet.'}
          </p>
        </ReportSection>

        <ReportSection title={copy.sections?.marketMacroContext || 'Market and macro context'}>
          <p className="leading-relaxed">
            {report.market_overview || report.macro_trends || copy.fallbacks?.marketMacroContext || 'No context is available yet.'}
          </p>
        </ReportSection>

        <ReportSection title={copy.sections?.technicalStructure || 'Technical structure'}>
          <p className="leading-relaxed">
            {report.technical_structure || copy.fallbacks?.technicalStructure || 'No technical evaluation is available yet.'}
          </p>
        </ReportSection>

        <ReportSection title={copy.sections?.strategicLessons || 'Strategic lessons'}>
          <p className="leading-relaxed">
            {report.strategic_lessons || copy.fallbacks?.strategicLessons || 'No strategic lessons are available yet.'}
          </p>
        </ReportSection>

        <ReportSection title={copy.sections?.outlook || 'Outlook'}>
          <p className="leading-relaxed">
            {report.outlook || copy.fallbacks?.outlook || 'No outlook is available yet.'}
          </p>
        </ReportSection>

      </section>

    </div>
  );
}
