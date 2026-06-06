"use client";

import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import ReportLayout from "@/components/report/layout/ReportLayout";
import { API_BASE_URL } from "@/lib/config";

function DailyPrintReportPageContent() {
  const searchParams = useSearchParams();
  const token = searchParams.get("token");
  const [report, setReport] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!token) {
       setError(`Missing print token.`);
       setLoading(false);
       return;
    }

    async function loadReport() {
      try {
        const res = await fetch(`${API_BASE_URL}/api/public/report?token=${token}`, {
          cache: "no-store",
        });

        if (!res.ok) {
          throw new Error(`Failed to fetch report: ${res.status}`);
        }

        const data = await res.json();
        setReport(data);
      } catch (err) {
        console.error("PRINT FETCH ERROR:", err);
        setError("Failed to load report data.");
      } finally {
        setLoading(false);
      }
    }

    loadReport();
  }, [token]);

  if (loading) {
    return <div className="p-8 font-mono animate-pulse">Laden van rapport...</div>;
  }

  if (error || !report) {
    return (
      <div className="print-wrapper p-8 text-red-500 font-mono">
        Error: {error || "Onbekende fout."}
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
  return (
    <Suspense fallback={<div className="p-8 font-mono animate-pulse">Laden van rapport...</div>}>
      <DailyPrintReportPageContent />
    </Suspense>
  );
}
