// SERVER component

export const dynamic = "force-dynamic";
export const revalidate = 0;

import ReportLayout from "@/components/report/layout/ReportLayout";

export default async function DailyPrintReportPage({ searchParams }) {
  // Debug log for V1 issues
  console.log("🖨️  Print Page SearchParams:", JSON.stringify(searchParams));
  
  const token = searchParams?.token;

  if (!token) {
    return (
      <div className="print-wrapper p-8 text-red-500 font-mono">
        Error: Missing print token (Received keys: {Object.keys(searchParams || {}).join(", ")}).
      </div>
    );
  }

  try {
    const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";
    const res = await fetch(
      `${apiBaseUrl}/api/public/report?token=${token}`,
      {
        cache: "no-store",
      }
    );

    if (!res.ok) {
      throw new Error(`Failed to fetch report: ${res.status}`);
    }

    const report = await res.json();

    return (
      <div className="bg-white min-h-screen p-8 md:p-12 print:p-0">
        <ReportLayout report={report} isPrint={true} />
        
        {/* Playwright signal - ONLY rendered on success */}
        <div id="print-ready" className="hidden" aria-hidden="true" />
      </div>
    );
  } catch (err) {
    console.error("PRINT FETCH ERROR:", err);

    return (
      <div className="print-wrapper p-8 text-red-500 font-mono">
        Error: Failed to load report data for printing.
      </div>
    );
  }
}
