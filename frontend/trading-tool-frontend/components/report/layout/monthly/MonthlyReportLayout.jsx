'use client';

import MonthlyRegimeShiftCard from '@/components/report/blocks/monthly/MonthlyRegimeShiftCard';
import MonthlyScoreStabilityCard from '@/components/report/blocks/monthly/MonthlyScoreStabilityCard';
import MonthlyBotReliabilityCard from '@/components/report/blocks/monthly/MonthlyBotReliabilityCard';

import ReportSection from '@/components/report/sections/ReportSection';

export default function MonthlyReportLayout({ report }) {
  if (!report) return null;

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

        <ReportSection title="Maandoverzicht">
          <p className="leading-relaxed">
            {report.executive_summary || 'Geen maandoverzicht beschikbaar.'}
          </p>
        </ReportSection>

        <ReportSection title="Markt- en macrocontext">
          <p className="leading-relaxed">
            {report.market_overview || report.macro_trends || 'Geen context beschikbaar.'}
          </p>
        </ReportSection>

        <ReportSection title="Technische structuur">
          <p className="leading-relaxed">
            {report.technical_structure || 'Geen technische evaluatie beschikbaar.'}
          </p>
        </ReportSection>

        <ReportSection title="Strategische lessen">
          <p className="leading-relaxed">
            {report.strategic_lessons || 'Geen strategische lessen beschikbaar.'}
          </p>
        </ReportSection>

        <ReportSection title="Vooruitblik">
          <p className="leading-relaxed">
            {report.outlook || 'Geen vooruitblik beschikbaar.'}
          </p>
        </ReportSection>

      </section>

    </div>
  );
}
