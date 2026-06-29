'use client';

import { MessageSquare, ChevronRight } from "lucide-react";
import CardWrapper from "@/components/ui/CardWrapper";
import CardLoader from "@/components/ui/CardLoader";
import Link from "next/link";
import { useReportData } from "@/hooks/useReportData";
import AIInsightBlock from "@/components/ui/AIInsightBlock";
import { useTranslation } from "@/app/providers/I18nProvider";

export default function ReportCard() {
  const { t } = useTranslation();
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
      : t?.dashboard?.cards?.reportReady;

  return (
    <CardWrapper
      title={t.dashboard.cards.report}
      icon={<MessageSquare className="w-4 h-4 text-[var(--primary)]" />}
    >
      <div className="flex flex-col gap-4 min-h-[220px]">

        {/* ⏳ LOADING */}
        {loading && <CardLoader text={t.dashboard.cards.loading_report} />}

        {/* 🟦 EERSTE KEER (404) */}
        {!loading && isFirstTime && (
          <div className="text-sm text-[var(--text-light)] leading-relaxed">
            ✨ {t.dashboard.cards.first_report_hint}
            <div className="mt-3">
              <Link
                href="/report"
                className="text-[var(--primary-dark)] hover:underline font-medium"
              >
                {t.dashboard.cards.view_example} →
              </Link>
            </div>
          </div>
        )}

        {/* 🔴 ECHTE ERROR */}
        {!loading && error === 'error' && (
          <p className="text-sm text-red-500 italic">
            {t.dashboard.cards.error_report}
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
              {t.dashboard.cards.view_last}
              <ChevronRight className="w-3 h-3" />
            </Link>
          </>
        )}
      </div>
    </CardWrapper>
  );
}
