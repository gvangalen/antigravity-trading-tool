"use client";

import ReportSectionMarket from '@/components/report/sections/ReportSectionMarket';
import ReportSectionAnalysis from '@/components/report/sections/ReportSectionAnalysis';
import ReportSectionStrategy from '@/components/report/sections/ReportSectionStrategy';
import ReportV2Layout from '@/components/report/layout/ReportV2Layout';
import { scoreSourceSnapshot } from '@/lib/report/reportSourceSnapshot.mjs';

/**
 * 📄 ReportLayout (Unified Professional Edition)
 * - Variable rhythm across 5 core sections
 * - Narrative-led structure
 * - Clean whitespace-driven design (no bars or lines)
 */
/**
 * 📄 ReportLayout (Structured Professional Edition)
 * - Consistent 2:1 Rhythm across all sections
 * - Narrative-led structure (left), Supporting data (right)
 * - Clean whitespace-driven design
 */
/**
 * 📄 ReportLayout (Exact Screenshot Edition)
 * - Restores the 8-chapter sequence from screenshots
 * - Continuous document flow
 * - Clean whitespace-driven design
 */
export default function ReportLayout({ report, isPrint = false }) {
  if (!report) return null;
  if (scoreSourceSnapshot(report)?.report_v2?.version === 2) {
    return <ReportV2Layout report={report} isPrint={isPrint} />;
  }

  return (
    <div
      className={`
        mx-auto 
        ${isPrint ? "max-w-[1000px]" : "max-w-[1100px]"}
        space-y-16 pb-20
      `}
    >
      {/* CHAPTERS 1-2: MARKT & OVERZICHT */}
      <section className="animate-in fade-in duration-1000">
        <ReportSectionMarket report={report} isPrint={isPrint} />
      </section>

      {/* CHAPTERS 3-4: MACRO & TECHNIEK */}
      <section className="animate-in fade-in slide-in-from-bottom-8 duration-1000 delay-100">
        <ReportSectionAnalysis report={report} isPrint={isPrint} />
      </section>

      {/* CHAPTERS 5-8: SETUPS & EXECUTION */}
      <section className="animate-in fade-in slide-in-from-bottom-8 duration-1000 delay-200">
        <ReportSectionStrategy report={report} isPrint={isPrint} />
      </section>
    </div>
  );
}
