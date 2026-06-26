import NarrativeBlock from "../blocks/NarrativeBlock";
import DataListBlock from "../blocks/DataListBlock";
import SectionAlignedAside from "../layout/SectionAlignedAside";

/**
 * 🛠️ ReportSectionAnalysis (Exact Screenshot Edition)
 * - Chapter 3: Macro Context (REVERSED: Card Left, Text Right)
 * - Chapter 4: Technische Analyse
 */
export default function ReportSectionAnalysis({ report, isPrint = false }) {
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
               title="Macro-indicator highlights"
             />
          </SectionAlignedAside>
        </div>

        <div className={`${colSpanClass} ${isPrint ? "order-1" : "order-1 lg:order-2"}`}>
          <NarrativeBlock
            title="Macrocontext"
            field="macro_context"
            report={report}
          />
        </div>
      </div>

      {/* CHAPTER 4: TECHNISCHE ANALYSE */}
      <div className={gridClass}>
        <div className={colSpanClass}>
          <NarrativeBlock
            title="Technische Analyse"
            field="technical_analysis"
            report={report}
          />
        </div>

        <SectionAlignedAside isPrint={isPrint}>
           <DataListBlock
             report={report}
             field="technical_indicator_highlights"
             title="Technische indicator-highlights"
           />
        </SectionAlignedAside>
      </div>

    </div>
  );
}
