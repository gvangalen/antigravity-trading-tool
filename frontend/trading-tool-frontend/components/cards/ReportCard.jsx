'use client';

import { MessageSquare, ChevronRight } from "lucide-react";
import CardWrapper from "@/components/ui/CardWrapper";
import CardLoader from "@/components/ui/CardLoader";
import Link from "next/link";
import { useReportData } from "@/hooks/useReportData";
import AIInsightBlock from "@/components/ui/AIInsightBlock";

export default function ReportCard() {
  const { report, loading, error } = useReportData("daily");

  // ✅ Report moet object zijn
  const safeReport =
    report && typeof report === "object" && !Array.isArray(report)
      ? report
      : null;

  // ✅ 404 = eerste keer / nog geen rapport
  const isFirstTime = error === 404;

  // ✅ AI-quote fallback
  const quote =
    typeof safeReport?.ai_summary_short === "string"
      ? safeReport.ai_summary_short
      : typeof safeReport?.headline === "string"
      ? safeReport.headline
      : "Nieuw rapport is klaar!";

  return (
    <CardWrapper
      title="Daily Rapport"
      icon={<MessageSquare className="w-4 h-4 text-[var(--primary)]" />}
    >
      <div className="flex flex-col gap-4 min-h-[220px]">

        {/* ⏳ LOADING */}
        {loading && <CardLoader text="Rapport laden…" />}

        {/* 🟦 EERSTE KEER (404) */}
        {!loading && isFirstTime && (
          <div className="text-sm text-[var(--text-light)] leading-relaxed">
            ✨ Je eerste dagelijkse rapport wordt
            <span className="font-semibold"> morgen vroeg automatisch</span>{" "}
            gegenereerd door de AI.
            <div className="mt-3">
              <Link
                href="/report"
                className="text-[var(--primary-dark)] hover:underline font-medium"
              >
                Bekijk voorbeeldrapport →
              </Link>
            </div>
          </div>
        )}

        {/* 🔴 ECHTE ERROR */}
        {!loading && error === 'error' && (
          <p className="text-sm text-red-500 italic">
            Rapport kon niet geladen worden.
          </p>
        )}

        {/* 🟢 RAPPORT AANWEZIG */}
        {!loading && safeReport && (
          <>
            <AIInsightBlock text={quote} variant="dashboard" />

            <Link
              href="/report"
              className="
                mt-auto text-xs font-medium
                text-[var(--primary-dark)]
                hover:underline flex items-center gap-1
              "
            >
              Bekijk laatste rapport
              <ChevronRight className="w-3 h-3" />
            </Link>
          </>
        )}
      </div>
    </CardWrapper>
  );
}
