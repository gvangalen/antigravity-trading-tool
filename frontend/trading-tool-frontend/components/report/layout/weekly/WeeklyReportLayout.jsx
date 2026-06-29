'use client';

import WeeklyRegimeOverviewCard from '@/components/report/blocks/weekly/WeeklyRegimeOverviewCard';
import WeeklyScoreTrendCard from '@/components/report/blocks/weekly/WeeklyScoreTrendCard';
import WeeklyBotBehaviorCard from '@/components/report/blocks/weekly/WeeklyBotBehaviorCard';

import ReportSection from '@/components/report/sections/ReportSection';
import { useTranslation } from '@/app/providers/I18nProvider';

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
  const { t } = useTranslation();
  if (!report) return null;

  const copy = t?.reports?.layouts?.weekly || {};

  return (
    <div className="max-w-6xl mx-auto px-4 space-y-20">

      {/* =====================================================
          1️⃣ WEEKOVERZICHT — IN ÉÉN OOGOPSLAG
      ====================================================== */}
      <section>
        <h2 className="text-lg font-semibold mb-4">
          {copy.summaryTitle || 'Weekly overview at a glance'}
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
          {copy.behaviorTitle || 'Bot behavior & execution'}
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

        <ReportSection title={copy.sections?.overview || 'Weekly overview'}>
          <p className="leading-relaxed text-[15px] text-neutral-800">
            {report.executive_summary || copy.fallbacks?.overview || 'No weekly overview is available yet.'}
          </p>
        </ReportSection>

        <ReportSection title={copy.sections?.marketDevelopment || 'Market development'}>
          <p className="leading-relaxed text-[15px] text-neutral-800">
            {report.market_overview || copy.fallbacks?.marketDevelopment || 'No market analysis is available yet.'}
          </p>
        </ReportSection>

        <ReportSection title={copy.sections?.macroContext || 'Macro context'}>
          <p className="leading-relaxed text-[15px] text-neutral-800">
            {report.macro_trends || copy.fallbacks?.macroContext || 'No macro analysis is available yet.'}
          </p>
        </ReportSection>

        <ReportSection title={copy.sections?.technicalStructure || 'Technical structure'}>
          <p className="leading-relaxed text-[15px] text-neutral-800">
            {report.technical_structure || copy.fallbacks?.technicalStructure || 'No technical analysis is available yet.'}
          </p>
        </ReportSection>

        <ReportSection title={copy.sections?.strategicLessons || 'Setups & strategic lessons'}>
          <p className="leading-relaxed text-[15px] text-neutral-800">
            {report.strategic_lessons || copy.fallbacks?.strategicLessons || 'No strategic lessons are available yet.'}
          </p>
        </ReportSection>

        <ReportSection title={copy.sections?.outlook || 'Outlook'}>
          <p className="leading-relaxed text-[15px] text-neutral-800">
            {report.outlook || copy.fallbacks?.outlook || 'No outlook is available yet.'}
          </p>
        </ReportSection>

      </section>

    </div>
  );
}
