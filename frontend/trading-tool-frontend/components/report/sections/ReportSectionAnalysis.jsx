import NarrativeBlock from "../blocks/NarrativeBlock";
import DataListBlock from "../blocks/DataListBlock";
import SectionAlignedAside from "../layout/SectionAlignedAside";
import { useTranslation } from "@/app/providers/I18nProvider";

/**
 * 🛠️ ReportSectionAnalysis (Exact Screenshot Edition)
 * - Chapter 3: Macro Context (REVERSED: Card Left, Text Right)
 * - Chapter 4: Technische Analyse
 */
export default function ReportSectionAnalysis({ report, isPrint = false }) {
  const { t } = useTranslation();
  const copy = t?.reports?.sections?.analysis || {};
  if (!report) return null;

  const gridClass = isPrint 
    ? "flex flex-col gap-12" 
    : "grid grid-cols-1 lg:grid-cols-3 gap-12 items-start";

  const colSpanClass = isPrint ? "w-full" : "lg:col-span-2";

  return (
    <div className="space-y-32">

      {/* CHAPTER 3: MACRO CONTEXT (Reversed Layout on Screen, Standard in Print) */}
      <div className={gridClass}>
        <div className={isPrint ? "order-2" : "order-2 lg:order-1"}>
          <SectionAlignedAside isPrint={isPrint} isReversed={!isPrint}>
             <DataListBlock
               report={report}
               field="macro_indicator_highlights"
               title={copy.macroIndicatorHighlights}
             />
          </SectionAlignedAside>
        </div>

        <div className={`${colSpanClass} ${isPrint ? "order-1" : "order-1 lg:order-2"}`}>
          <NarrativeBlock
            title={copy.macroContext}
            field="macro_context"
            report={report}
          />
        </div>
      </div>

      {/* CHAPTER 4: TECHNISCHE ANALYSE */}
      <div className={gridClass}>
        <div className={colSpanClass}>
          <NarrativeBlock
            title={copy.technicalAnalysis}
            field="technical_analysis"
            report={report}
          />
        </div>

        <SectionAlignedAside isPrint={isPrint}>
           <DataListBlock
             report={report}
             field="technical_indicator_highlights"
             title={copy.technicalIndicatorHighlights}
           />
        </SectionAlignedAside>
      </div>

    </div>
  );
}
