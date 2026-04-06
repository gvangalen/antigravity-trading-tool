'use client';

import WeeklyRegimeOverviewCard from '@/components/report/blocks/weekly/WeeklyRegimeOverviewCard';
import WeeklyScoreTrendCard from '@/components/report/blocks/weekly/WeeklyScoreTrendCard';
import WeeklyBotBehaviorCard from '@/components/report/blocks/weekly/WeeklyBotBehaviorCard';

import ReportSection from '@/components/report/sections/ReportSection';

/**
 * WeeklyReportLayout — v2.1
 * --------------------------------------------------
 * Filosofie:
 * - Snelle visuele samenvatting bovenaan
 * - Evaluatie van gedrag & betrouwbaarheid
 * - Rustige strategische reflectie (geen daily focus)
 *
 * Structuur:
 * 1. Weekoverzicht in één oogopslag (cards)
 * 2. Botgedrag & execution (cards)
 * 3. Strategische context (leesbaar, tekst)
 *
 * Backend canonical keys (weekly_reports):
 * - executive_summary
 * - market_overview
 * - macro_trends
 * - technical_structure
 * - setup_performance
 * - bot_performance
 * - strategic_lessons
 * - outlook
 */
export default function WeeklyReportLayout({ report }) {
  if (!report) return null;

  return (
    <div className="max-w-6xl mx-auto px-4 space-y-20">

      {/* =====================================================
          1️⃣ WEEKOVERZICHT — IN ÉÉN OOGOPSLAG
      ====================================================== */}
      <section>
        <h2 className="text-lg font-semibold mb-4">
          Weekoverzicht in één oogopslag
        </h2>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <WeeklyRegimeOverviewCard report={report} />
          <WeeklyScoreTrendCard report={report} />
        </div>
      </section>

      {/* =====================================================
          2️⃣ BOTGEDRAG & EXECUTION
      ====================================================== */}
      <section>
        <h2 className="text-lg font-semibold mb-4">
          Botgedrag & uitvoering
        </h2>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <WeeklyBotBehaviorCard report={report} />

          {/* Placeholder: execution / discipline / risk heatmap */}
          <div className="hidden md:block" />
        </div>
      </section>

      {/* =====================================================
          3️⃣ STRATEGISCHE CONTEXT — REFLECTIE
      ====================================================== */}
      <section className="max-w-3xl mx-auto space-y-14">

        <ReportSection title="Weekoverzicht">
          <p className="leading-relaxed text-[15px] text-neutral-800">
            {report.executive_summary || 'Geen weekoverzicht beschikbaar.'}
          </p>
        </ReportSection>

        <ReportSection title="Marktontwikkeling">
          <p className="leading-relaxed text-[15px] text-neutral-800">
            {report.market_overview || 'Geen marktanalyse beschikbaar.'}
          </p>
        </ReportSection>

        <ReportSection title="Macro-context">
          <p className="leading-relaxed text-[15px] text-neutral-800">
            {report.macro_trends || 'Geen macro-analyse beschikbaar.'}
          </p>
        </ReportSection>

        <ReportSection title="Technische structuur">
          <p className="leading-relaxed text-[15px] text-neutral-800">
            {report.technical_structure || 'Geen technische analyse beschikbaar.'}
          </p>
        </ReportSection>

        <ReportSection title="Setups & strategische lessen">
          <p className="leading-relaxed text-[15px] text-neutral-800">
            {report.strategic_lessons || 'Geen strategische lessen beschikbaar.'}
          </p>
        </ReportSection>

        <ReportSection title="Vooruitblik">
          <p className="leading-relaxed text-[15px] text-neutral-800">
            {report.outlook || 'Geen vooruitblik beschikbaar.'}
          </p>
        </ReportSection>

      </section>

    </div>
  );
}
