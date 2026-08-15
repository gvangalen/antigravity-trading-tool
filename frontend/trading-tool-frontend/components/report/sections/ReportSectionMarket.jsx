import SummaryBlock from "../blocks/SummaryBlock";
import NarrativeBlock from "../blocks/NarrativeBlock";
import MarketSnapshotBlock from "../blocks/MarketSnapshotBlock";
import DataListBlock from "../blocks/DataListBlock";
import SectionAlignedAside from "../layout/SectionAlignedAside";

import { useAuth } from "@/components/auth/AuthProvider";
import { useTranslation } from "@/app/providers/I18nProvider";

/**
 * 📈 ReportSectionMarket (Exact Screenshot Edition)
 * - Chapter 1: Dagoverzicht
 * - Chapter 2: Marktanalyse
 */
export default function ReportSectionMarket({ report, isPrint = false }) {
  const { t } = useTranslation();
  const copy = t?.reports?.sections?.market || {};
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
            <h2 className="text-2xl font-bold text-foreground tracking-tight mb-6">
              {copy.dailyOverview} — <span className="text-secondary font-medium">{report.report_date || "—"}</span>
            </h2>
            
            <div className="space-y-1">
              <div className="text-xl font-bold text-slate-900">
                {copy.greeting} {user?.first_name || "Trader"},
              </div>
              <p className="text-muted font-medium italic">
                {copy.marketIntro}
              </p>
            </div>
          </div>
          
          <SummaryBlock report={report} hideHeader />
        </div>

        <SectionAlignedAside isPrint={isPrint}>
          <MarketSnapshotBlock report={report} />
        </SectionAlignedAside>
      </div>

      {/* CHAPTER 2: MARKTANALYSE */}
      <div className={gridClass}>
        <div className={colSpanClass}>
          <NarrativeBlock
            title={copy.analysisTitle}
            field="market_analysis"
            report={report}
          />
        </div>

        <SectionAlignedAside isPrint={isPrint}>
          <DataListBlock
            report={report}
            field="market_indicator_highlights"
            title={copy.highlightsTitle}
          />
        </SectionAlignedAside>
      </div>

    </div>
  );
}
