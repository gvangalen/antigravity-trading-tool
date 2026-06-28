"use client";

import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import ReportLayout from "@/components/report/layout/ReportLayout";
import { API_BASE_URL } from "@/lib/config";
import { useTranslation } from "@/app/providers/I18nProvider";

const DEFAULT_PRINT_COPY = {
  missingToken: "Missing print token.",
  fetchFailed: "Failed to fetch report",
  loadFailed: "Could not load report data.",
  loading: "Loading report...",
  errorPrefix: "Error",
  unknownError: "Unknown error.",
};

function DailyPrintReportPageContent() {
  const { t } = useTranslation();
  const copy = t?.reports?.print || DEFAULT_PRINT_COPY;
  const searchParams = useSearchParams();
  const token = searchParams.get("token");
  const [report, setReport] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!token) {
       setError(copy.missingToken);
       setLoading(false);
       return;
    }

    async function loadReport() {
      try {
        const res = await fetch(`${API_BASE_URL}/api/public/report?token=${token}`, {
          cache: "no-store",
        });

        if (!res.ok) {
          throw new Error(`${copy.fetchFailed}: ${res.status}`);
        }

        const data = await res.json();
        setReport(data);
      } catch (err) {
        console.error("PRINT FETCH ERROR:", err);
        setError(copy.loadFailed);
      } finally {
        setLoading(false);
      }
    }

    loadReport();
  }, [token]);

  if (loading) {
    return <div className="p-8 font-mono animate-pulse">{copy.loading}</div>;
  }

  if (error || !report) {
    return (
      <div className="print-wrapper p-8 text-red-500 font-mono">
        {copy.errorPrefix}: {error || copy.unknownError}
      </div>
    );
  }

  return (
    <div className="bg-white min-h-screen p-8 md:p-12 print:p-0">
      <ReportLayout report={report} isPrint={true} />
      
      {/* Playwright signal - ONLY rendered on success */}
      <div id="print-ready" className="hidden" aria-hidden="true" />
    </div>
  );
}

export default function DailyPrintReportPage() {
  const { t } = useTranslation();
  const copy = t?.reports?.print || DEFAULT_PRINT_COPY;
  return (
    <Suspense fallback={<div className="p-8 font-mono animate-pulse">{copy.loading}</div>}>
      <DailyPrintReportPageContent />
    </Suspense>
  );
}
