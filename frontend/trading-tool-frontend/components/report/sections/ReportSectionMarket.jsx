import SummaryBlock from "../blocks/SummaryBlock";
import NarrativeBlock from "../blocks/NarrativeBlock";
import MarketSnapshotBlock from "../blocks/MarketSnapshotBlock";
import DataListBlock from "../blocks/DataListBlock";
import SectionAlignedAside from "../layout/SectionAlignedAside";

import { useAuth } from "@/components/auth/AuthProvider";

/**
 * 📈 ReportSectionMarket (Exact Screenshot Edition)
 * - Chapter 1: Dagoverzicht
 * - Chapter 2: Market Analyse
 */
export default function ReportSectionMarket({ report, isPrint = false }) {
  const { user } = useAuth();
  if (!report) return null;

  const gridClass = isPrint 
    ? "flex flex-col gap-12" 
    : "grid grid-cols-1 lg:grid-cols-3 gap-12 items-start";

  const colSpanClass = isPrint ? "w-full" : "lg:col-span-2";

  return (
    <div className="space-y-32">

      {/* CHAPTER 1: DAGOVERZICHT */}
      <div className={gridClass}>
        <div className={colSpanClass}>
          <div className="mb-10">
            <h2 className="text-2xl font-bold text-slate-900 tracking-tight mb-6">
              Dagoverzicht — <span className="text-slate-400 font-medium">{report.report_date || "—"}</span>
            </h2>
            
            <div className="space-y-1">
              <div className="text-xl font-bold text-slate-900">
                Hi {user?.first_name || "Gerrit"},
              </div>
              <p className="text-slate-500 font-medium italic">
                De markt laat vandaag het volgende beeld zien:
              </p>
            </div>
          </div>
          
          <SummaryBlock report={report} hideHeader />
        </div>

        <SectionAlignedAside isPrint={isPrint}>
          <MarketSnapshotBlock report={report} />
        </SectionAlignedAside>
      </div>

      {/* CHAPTER 2: MARKET ANALYSE */}
      <div className={gridClass}>
        <div className={colSpanClass}>
          <NarrativeBlock
            title="Market Analyse"
            field="market_analysis"
            report={report}
          />
        </div>

        <SectionAlignedAside isPrint={isPrint}>
          <DataListBlock
            report={report}
            field="market_indicator_highlights"
            title="Market Indicator Highlights"
          />
        </SectionAlignedAside>
      </div>

    </div>
  );
}
