import NarrativeBlock from "../blocks/NarrativeBlock";
import SetupMatchReportCard from "../blocks/SetupMatchReportCard";
import ActiveStrategyReportCard from "../blocks/ActiveStrategyReportCard";
import BotDecisionReportCard from "../blocks/BotDecisionReportCard";
import SectionAlignedAside from "../layout/SectionAlignedAside";
import { useTranslation } from "@/app/providers/I18nProvider";

/**
 * 🎯 ReportSectionStrategy (Exact Screenshot Edition)
 * - Chapter 5: Setup Validatie
 * - Chapter 6: Strategie Implicatie
 * - Chapter 7: Botbeslissing
 * - Chapter 8: Vooruitblik & Scenario's
 */
export default function ReportSectionStrategy({ report, isPrint = false }) {
  const { t } = useTranslation();
  const copy = t?.reports?.sections?.strategy || {};
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
            title={copy.setupValidation}
            field="setup_validation"
            report={report}
          />
        </div>

        <SectionAlignedAside isPrint={isPrint}>
           <SetupMatchReportCard report={report} title={copy.setupMatchToday} />
        </SectionAlignedAside>
      </div>

      {/* CHAPTER 6: STRATEGIE IMPLICATIE */}
      <div className={gridClass}>
        <div className={colSpanClass}>
          <NarrativeBlock
            title={copy.strategyImplication}
            field="strategy_implication"
            report={report}
          />
        </div>

        <SectionAlignedAside isPrint={isPrint}>
           <ActiveStrategyReportCard report={report} title={copy.activeStrategyToday} />
        </SectionAlignedAside>
      </div>

      {/* CHAPTER 7: BOTBESLISSING */}
      <div className={gridClass}>
        <div className={colSpanClass}>
          <NarrativeBlock
            title={copy.botDecision}
            field="bot_strategy"
            report={report}
          />
        </div>

        <SectionAlignedAside isPrint={isPrint}>
           <BotDecisionReportCard snapshot={report?.bot_snapshot} title={copy.botDecisionToday} />
        </SectionAlignedAside>
      </div>

      {/* CHAPTER 8: VOORUITBLIK & SCENARIO'S (Full Width) */}
      <div className={isPrint ? "w-full" : "max-w-3xl"}>
        <NarrativeBlock
          title={copy.outlook}
          field="outlook"
          report={report}
        />
      </div>

    </div>
  );
}
