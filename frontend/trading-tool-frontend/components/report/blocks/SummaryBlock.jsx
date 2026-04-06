"use client";

import ReportSection from "../ReportSection";

/* =====================================================
   HELPERS
   - robuust voor string / jsonb / AI-output
===================================================== */

function normalizeExecutiveSummary(value) {
  if (value === null || value === undefined) return null;

  if (typeof value === "string") {
    const v = value.trim();
    return v.length ? v : null;
  }

  if (typeof value === "object") {
    if (typeof value.text === "string") return value.text.trim();
    if (typeof value.summary === "string") return value.summary.trim();
    if (typeof value.description === "string")
      return value.description.trim();

    try {
      return JSON.stringify(value, null, 2);
    } catch {
      return String(value);
    }
  }

  return null;
}

/* =====================================================
   BLOCK — Executive Summary
   ✔ opening van het rapport
   ✔ meta (datum + gebruiker) HIER
   ✔ tekst eronder
===================================================== */

export default function SummaryBlock({
  report,
  hideHeader = false,
}) {
  if (!report || typeof report !== "object") return null;

  const content = normalizeExecutiveSummary(report.executive_summary);
  if (!content) return null;

  const inner = (
    <div className="flex flex-col gap-6">
      {/* NARRATIVE TEXT */}
      <div className="text-[18px] leading-[1.8] text-slate-800 tracking-tight">
        {content}
      </div>
    </div>
  );

  if (hideHeader) return inner;

  return (
    <ReportSection title="Samenvatting">
      {inner}
    </ReportSection>
  );
}
