import { useState } from 'react';

import { BotDecisionCard } from '../components/cards/BotDecisionCard';
import { InsightCard } from '../components/cards/InsightCard';
import { RiskWarningCard } from '../components/cards/RiskWarningCard';
import { StrategyStatusCard } from '../components/cards/StrategyStatusCard';
import { AssetContextHeader } from '../components/layout/AssetContextHeader';
import { ScreenContainer } from '../components/layout/ScreenContainer';
import { SectionHeader } from '../components/layout/SectionHeader';
import { BottomSheet } from '../components/sheets/BottomSheet';
import { RiskExplanationSheetContent } from '../components/sheets/SheetContent';
import { mockBotDecision, mockBriefing, mockStrategy, mockWarning } from '../data/mockFoundation';

export function SetupScreen() {
  const [sheet, setSheet] = useState<'risk' | null>(null);

  return (
    <ScreenContainer>
      <AssetContextHeader asset={mockBriefing.asset} context="Setup decision layer" updatedAt={mockBriefing.updatedAt} />
      <SectionHeader
        label="Setup"
        title="Scenarios for today"
        description="Foundation preview. FINN is the only backend-connected tab in this phase."
      />

      <InsightCard
        label="Foundation mode"
        title="Setup remains mock-only for now."
        body="This lets the first authenticated assistant flow settle before setup/strategy read endpoints are expanded."
        cta="Ask FINN to explain"
        tone="neutral"
      />

      <StrategyStatusCard {...mockStrategy} />

      <BotDecisionCard {...mockBotDecision} onConfirm={() => setSheet('risk')} />

      <RiskWarningCard
        severity={mockWarning.severity}
        title="Scenario is not an execution command."
        body="Setup context explains the plan and risk. Execution remains gated and review-first."
        nextStep="Review the scenario, then return to FINN for coaching."
        onExplain={() => setSheet('risk')}
      />

      <BottomSheet visible={sheet === 'risk'} title="Risk explanation" onClose={() => setSheet(null)}>
        <RiskExplanationSheetContent />
      </BottomSheet>
    </ScreenContainer>
  );
}
