import NarrativeBlock from "../blocks/NarrativeBlock";
import SetupMatchReportCard from "../blocks/SetupMatchReportCard";
import ActiveStrategyReportCard from "../blocks/ActiveStrategyReportCard";
import BotDecisionReportCard from "../blocks/BotDecisionReportCard";
import SectionAlignedAside from "../layout/SectionAlignedAside";

/**
 * 🎯 ReportSectionStrategy (Exact Screenshot Edition)
 * - Chapter 5: Setup Validatie
 * - Chapter 6: Strategie Implicatie
 * - Chapter 7: Botbeslissing
 * - Chapter 8: Vooruitblik & Scenario's
 */
export default function ReportSectionStrategy({ report, isPrint = false }) {
  if (!report) return null;

  const gridClass = isPrint 
    ? "flex flex-col gap-12" 
    : "grid grid-cols-1 lg:grid-cols-3 gap-12 items-start";

  const colSpanClass = isPrint ? "w-full" : "lg:col-span-2";

  return (
    <div className="space-y-32">

      {/* CHAPTER 5: SETUP VALIDATIE */}
      <div className={gridClass}>
        <div className={colSpanClass}>
          <NarrativeBlock
            title="Setup Validatie"
            field="setup_validation"
            report={report}
          />
        </div>

        <SectionAlignedAside isPrint={isPrint}>
           <SetupMatchReportCard report={report} title="Setup Match Vandaag" />
        </SectionAlignedAside>
      </div>

      {/* CHAPTER 6: STRATEGIE IMPLICATIE */}
      <div className={gridClass}>
        <div className={colSpanClass}>
          <NarrativeBlock
            title="Strategie Implicatie"
            field="strategy_implication"
            report={report}
          />
        </div>

        <SectionAlignedAside isPrint={isPrint}>
           <ActiveStrategyReportCard report={report} title="Actieve Strategie Vandaag" />
        </SectionAlignedAside>
      </div>

      {/* CHAPTER 7: BOTBESLISSING */}
      <div className={gridClass}>
        <div className={colSpanClass}>
          <NarrativeBlock
            title="Botbeslissing"
            field="bot_strategy"
            report={report}
          />
        </div>

        <SectionAlignedAside isPrint={isPrint}>
           <BotDecisionReportCard snapshot={report?.bot_snapshot} title="Botbeslissing Vandaag" />
        </SectionAlignedAside>
      </div>

      {/* CHAPTER 8: VOORUITBLIK & SCENARIO'S (Full Width) */}
      <div className={isPrint ? "w-full" : "max-w-3xl"}>
        <NarrativeBlock
          title="Vooruitblik & Scenario's"
          field="outlook"
          report={report}
        />
      </div>

    </div>
  );
}
