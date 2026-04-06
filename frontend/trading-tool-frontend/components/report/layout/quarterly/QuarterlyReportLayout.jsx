'use client';

import QuarterlyCyclePositionCard from '@/components/report/blocks/quarterly/QuarterlyCyclePositionCard';
import QuarterlyStrategyQualityCard from '@/components/report/blocks/quarterly/QuarterlyStrategyQualityCard';
import QuarterlyRiskDrawdownCard from '@/components/report/blocks/quarterly/QuarterlyRiskDrawdownCard';

import ReportSection from '@/components/report/sections/ReportSection';

export default function QuarterlyReportLayout({ report }) {
  if (!report) return null;

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

        <ReportSection title="Kwartaaloverzicht">
          <p className="leading-relaxed">
            {report.executive_summary || 'Geen kwartaaloverzicht beschikbaar.'}
          </p>
        </ReportSection>

        <ReportSection title="Strategische lessen">
          <p className="leading-relaxed">
            {report.strategic_lessons || 'Geen strategische lessen beschikbaar.'}
          </p>
        </ReportSection>

        <ReportSection title="Vooruitblik volgend kwartaal">
          <p className="leading-relaxed">
            {report.outlook || 'Geen vooruitblik beschikbaar.'}
          </p>
        </ReportSection>

      </section>

    </div>
  );
}
