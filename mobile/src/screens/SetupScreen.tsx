import { useCallback, useEffect, useMemo, useState } from 'react';
import { Feather } from '@expo/vector-icons';
import { useNavigation, useRoute } from '@react-navigation/native';
import type { NavigationProp, RouteProp } from '@react-navigation/native';
import { Pressable, ScrollView, StyleSheet, Text, View, TouchableOpacity } from 'react-native';

import { BotDecisionCard } from '../components/cards/BotDecisionCard';
import { AppButton } from '../components/buttons/AppButton';
import { CardShell } from '../components/cards/CardShell';
import { InsightCard } from '../components/cards/InsightCard';
import { RiskWarningCard } from '../components/cards/RiskWarningCard';
import { StrategyStatusCard } from '../components/cards/StrategyStatusCard';
import { LoadingSkeletonCard } from '../components/layout/LoadingSkeletonCard';
import { ScreenContainer } from '../components/layout/ScreenContainer';
import { StatusChip } from '../components/layout/StatusChip';
import { BottomSheet } from '../components/sheets/BottomSheet';
import { StrategyCard } from '../components/StrategyCard';
import { TodayWithFinnCard } from '../components/workspace/TodayWithFinnCard';
import { WorkspaceHeroSection } from '../components/workspace/WorkspaceHeroSection';
import { StatusTone, statusTones, theme } from '../constants/theme';

import { useApiResource } from '../hooks/useApiResource';
import { localizedBackendText, translate, translateFinnTag } from '../i18n';
import { preferenceColors, useAppPreferences } from '../preferences/AppPreferencesProvider';
import type { MainTabParamList } from '../navigation/MainTabNavigator';
import { mapBotDecision, mapStrategy, nowLabel } from '../services/dataMappers';
import {
  BotResponse,
  MobileOverviewResponse,
  SetupResponse,
  StrategyResponse,
  intelligenceApi,
  mobileApi,
} from '../services/tradamindApi';
import { triggerHaptic } from '../utils/haptics';
import { useIntelligenceContext } from '../contexts/ActiveIntelligenceContext';
import { useFinnOverlay } from '../contexts/FinnOverlayContext';
import { trackAssistantEvent } from '../services/assistantAnalytics';

type UnknownRecord = Record<string, unknown>;
type SheetKey = 'setup' | 'strategy' | 'risk' | 'confirm' | null;

type SetupSummary = {
  id?: number;
  name: string;
  symbol: string;
  timeframe: string;
  type: string;
  trend: string;
  action: string;
  score: number;
  explanation: string;
  tone: StatusTone;
  status?: string;
};

type BotActionMeta = {
  botId?: number;
  decisionId?: number;
  reportDate?: string;
  status: string;
  reasons: string[];
  tradePlan: UnknownRecord;
  canMarkExecuted: boolean;
};

type PlanStrategySummary = {
  id?: number;
  name: string;
  exists: boolean;
};

export function SetupScreen() {
  const route = useRoute<RouteProp<MainTabParamList, 'Setup'>>();
  const navigation = useNavigation<any>();
  const { context, updateContext } = useIntelligenceContext();
  const activeAsset = route.params?.symbol ?? context.asset;
  const { openFinn } = useFinnOverlay();
  const [sheet, setSheet] = useState<SheetKey>(null);
  const [handledNotification, setHandledNotification] = useState<string | null>(null);
  const [actionStatus, setActionStatus] = useState<string>('');
  const [actionLoading, setActionLoading] = useState(false);

  useEffect(() => {
    trackAssistantEvent({
      event_name: 'screen_view',
      page: 'my_plan',
      flow_type: 'my_plan',
    });
  }, []);

  const fetchOverview = useCallback(() => mobileApi.overview(activeAsset), [activeAsset]);
  const overviewResource = useApiResource<MobileOverviewResponse | undefined>({
    fallbackData: undefined,
    fetcher: fetchOverview,
  });

  const notificationType = route.params?.notificationType;
  useEffect(() => {
    if (route.params?.symbol && route.params.symbol !== context.asset) {
      updateContext({ asset: route.params.symbol, screen: 'My Plan' });
    }
  }, [route.params?.symbol]);

  const activeOverviewAsset = overviewResource.data?.watchlist.find((asset) => asset.symbol === activeAsset);

  const fetchActiveSetup = useCallback(() => intelligenceApi.activeSetups(activeAsset), [activeAsset]);
  const activeSetupResource = useApiResource<SetupResponse | undefined>({
    fallbackData: undefined,
    fetcher: fetchActiveSetup,
  });

  const fetchTopSetups = useCallback(() => intelligenceApi.topSetups(), []);
  const topSetupsResource = useApiResource<SetupResponse | undefined>({
    fallbackData: undefined,
    fetcher: fetchTopSetups,
  });
  const topSetupRecords = useMemo(() => asArray(topSetupsResource.data).slice(0, 12), [topSetupsResource.data]);
  const topSetupIds = useMemo(
    () => topSetupRecords
      .map((item) => readOptionalNumber(item, ['id', 'setup_id']))
      .filter((value): value is number => typeof value === 'number'),
    [topSetupRecords],
  );

  const activeSetup = useMemo(() => extractActiveSetup(activeSetupResource.data), [activeSetupResource.data]);
  const setupId = useMemo(() => readOptionalNumber(activeSetup, ['id', 'setup_id']), [activeSetup]);

  const fetchStrategy = useCallback(() => {
    if (setupId) {
      return intelligenceApi.getStrategyBySetup(setupId);
    }
    return intelligenceApi.activeStrategyToday();
  }, [setupId]);

  const strategyResource = useApiResource<StrategyResponse | undefined>({
    fallbackData: undefined,
    fetcher: fetchStrategy,
    enabled: true,
  });

  const fetchBotToday = useCallback(() => intelligenceApi.botToday(activeAsset), [activeAsset]);
  const botResource = useApiResource<BotResponse | undefined>({
    fallbackData: undefined,
    fetcher: fetchBotToday,
  });

  const setup = useMemo(
    () => mapSetupSummary(activeSetupResource.data, activeOverviewAsset),
    [activeOverviewAsset, activeSetupResource.data],
  );
  const strategySource = useMemo(() => extractStrategy(strategyResource.data), [strategyResource.data]);
  const activeStrategyName = useMemo(
    () =>
      readString(strategySource, ['name', 'strategy_name', 'setup_name'], '') ||
      (strategySource ? 'Active strategy' : 'Add strategy'),
    [strategySource],
  );
  const strategy = useMemo(
    () => mapStrategy(strategySource, activeSetupResource.data),
    [activeSetupResource.data, strategySource],
  );
  const fetchPlanStrategies = useCallback(async () => {
    if (topSetupIds.length === 0) return {} as Record<string, PlanStrategySummary | null>;

    const entries = await Promise.all(
      topSetupIds.map(async (currentSetupId) => {
        try {
          const source = await intelligenceApi.getStrategyBySetup(currentSetupId);
          return [String(currentSetupId), mapPlanStrategySummary(source)] as const;
        } catch {
          return [String(currentSetupId), null] as const;
        }
      }),
    );

    return Object.fromEntries(entries);
  }, [topSetupIds]);
  const planStrategiesResource = useApiResource<Record<string, PlanStrategySummary | null>>({
    fallbackData: {},
    fetcher: fetchPlanStrategies,
    enabled: topSetupIds.length > 0,
  });
  const botDecisionSource = useMemo(() => extractBotDecision(botResource.data), [botResource.data]);
  const botDecision = useMemo(() => mapBotDecision(botDecisionSource), [botDecisionSource]);
  const botMeta = useMemo(() => mapBotActionMeta(botResource.data, botDecisionSource), [botDecisionSource, botResource.data]);
  const topSetups = useMemo(() => mapTopSetups(topSetupsResource.data), [topSetupsResource.data]);
  const decisionState = useMemo(
    () => mapDecisionState(activeOverviewAsset, setup, botDecision.action),
    [activeOverviewAsset, botDecision.action, setup],
  );
  const loading =
    overviewResource.loading ||
    activeSetupResource.loading ||
    strategyResource.loading ||
    botResource.loading ||
    topSetupsResource.loading ||
    planStrategiesResource.loading;
  const isStale =
    overviewResource.isStale ||
    activeSetupResource.isStale ||
    strategyResource.isStale ||
    botResource.isStale ||
    topSetupsResource.isStale ||
    planStrategiesResource.isStale;

  useEffect(() => {
    if (!notificationType) return;

    const key = `${notificationType}-${activeAsset}`;
    if (handledNotification === key) return;
    setHandledNotification(key);

    if (notificationType === 'bot_action_ready') {
      setSheet('confirm');
    }
    if (notificationType === 'strategy_invalidated') {
      setSheet('strategy');
    }
  }, [activeAsset, handledNotification, notificationType]);

  async function skipBotAction() {
    if (!botMeta.botId) return;
    setActionLoading(true);
    setActionStatus('');
    try {
      await intelligenceApi.skipBotToday({
        bot_id: botMeta.botId,
        report_date: botMeta.reportDate,
      });
      setActionStatus('Botactie is overgeslagen. De backend-status is bijgewerkt en Finn helpt je nu bepalen wat je moet blijven volgen.');
      await botResource.refresh();
      openFinn({
        prefill: `Ik heb de botactie voor ${activeAsset} overgeslagen. Leg kort uit wat ik nu moet blijven monitoren.`,
        source: 'action-skip',
      });
    } catch (error) {
      setActionStatus(error instanceof Error ? error.message : 'Skip mislukt. Probeer opnieuw na refresh.');
    } finally {
      setActionLoading(false);
    }
  }

  async function markExecuted() {
    if (!botMeta.botId || !botMeta.decisionId || !botMeta.canMarkExecuted) return;
    setActionLoading(true);
    setActionStatus('');
    try {
      await intelligenceApi.markBotExecuted({
        bot_id: botMeta.botId,
        decision_id: botMeta.decisionId,
      });
      setActionStatus('Botactie is gemarkeerd als uitgevoerd. Finn vat nu kort samen wat dit betekent voor je volgende review.');
      await botResource.refresh();
      openFinn({
        prefill: `Ik heb de botactie voor ${activeAsset} gemarkeerd als uitgevoerd. Vat de impact samen voor mijn volgende rapport.`,
        source: 'action-executed',
      });
    } catch (error) {
      setActionStatus(error instanceof Error ? error.message : 'Markeren mislukt. Controleer backend-status.');
    } finally {
      setActionLoading(false);
    }
  }

  return (
    <ScreenContainer
      contentInsetBottom={272}
      edgeToEdge={true}
      refreshing={
        overviewResource.refreshing ||
        activeSetupResource.refreshing ||
        topSetupsResource.refreshing ||
        strategyResource.refreshing ||
        botResource.refreshing ||
        planStrategiesResource.refreshing
      }
      onRefresh={async () => {
        await Promise.all([
          overviewResource.refresh(),
          activeSetupResource.refresh(),
          topSetupsResource.refresh(),
          strategyResource.refresh(),
          botResource.refresh(),
          planStrategiesResource.refresh(),
        ]);
      }}
    >
      {notificationType ? (
        <NotificationContextCard
          activeAsset={activeAsset}
          notificationType={notificationType}
          onAskFinn={() =>
            openFinn({
              prefill: pushPrefill(notificationType, activeAsset),
              source: `push-${notificationType}`,
            })
          }
          onReview={() => setSheet(notificationType === 'strategy_invalidated' ? 'strategy' : 'confirm')}
        />
      ) : null}

      {loading && !activeOverviewAsset && !activeSetupResource.data && !botResource.data ? (
        <LoadingSkeletonCard />
      ) : (
        <>
          <FinnSetupBriefingCard
            briefing={overviewResource.data?.finn_briefing}
            decisionState={decisionState}
            topSetups={topSetups}
            isStale={isStale}
            onAskFinn={() =>
              openFinn({
                prefill: `Explain my current plan for ${activeAsset}. Tell me why ${setup.name} is leading, what confirms it and what should wait.`,
                source: 'my-plan-workspace',
                symbol: activeAsset,
              })
            }
            setup={setup}
            strategy={strategy}
          />
          <MyPlanWorkflowIntro setup={setup} />
          <ActivePlanWorkspaceCard
            botDecision={botDecision}
            decisionState={decisionState}
            onOpenSetup={() => setSheet('setup')}
            onOpenStrategy={() => setSheet('strategy')}
            onReviewBot={() => setSheet('confirm')}
            setup={setup}
            strategy={strategy}
          />
          <AllPlansListCard
            activeSetup={setup}
            activeStrategyName={activeStrategyName}
            planStrategies={planStrategiesResource.data}
            strategy={strategy}
            setups={topSetups}
          />
        </>
      )}

      {overviewResource.error || activeSetupResource.error || strategyResource.error || botResource.error ? (
        <InsightCard
          label="Action sync"
          title="Een deel van de decision-data is stale."
          body={
            overviewResource.error?.message ||
            activeSetupResource.error?.message ||
            strategyResource.error?.message ||
            botResource.error?.message ||
            (planStrategiesResource.error instanceof Error ? planStrategiesResource.error.message : '') ||
            'Controleer backend/API status.'
          }
          tone="warning"
          cta="Ververs"
        />
      ) : null}

      <BottomSheet visible={sheet === 'setup'} title="Actieve setup" onClose={() => setSheet(null)}>
        <SetupSheet setup={setup} />
      </BottomSheet>
      <BottomSheet visible={sheet === 'strategy'} title="Strategiedetail" onClose={() => setSheet(null)}>
        <StrategySheet strategy={strategySource} fallback={strategy} />
      </BottomSheet>
      <BottomSheet visible={sheet === 'risk'} title="Laat Finn risico uitleggen" onClose={() => setSheet(null)}>
        <RiskSheet decisionState={decisionState} setup={setup} botReasons={botMeta.reasons} />
      </BottomSheet>
      <BottomSheet visible={sheet === 'confirm'} title="Bevestig botactie" onClose={() => setSheet(null)}>
        <ConfirmBotSheet
          actionLoading={actionLoading}
          actionStatus={actionStatus}
          botDecision={botDecision}
          botMeta={botMeta}
          onMarkExecuted={markExecuted}
          onSkip={skipBotAction}
        />
      </BottomSheet>
    </ScreenContainer>
  );
}

function FinnSetupBriefingCard({
  briefing,
  decisionState,
  isStale,
  onAskFinn,
  setup,
  strategy,
  topSetups,
}: {
  briefing?: MobileOverviewResponse['finn_briefing'];
  decisionState: ReturnType<typeof mapDecisionState>;
  isStale: boolean;
  onAskFinn: () => void;
  setup: SetupSummary;
  strategy: ReturnType<typeof mapStrategy>;
  topSetups: SetupSummary[];
}) {
  const { language } = useAppPreferences();
  const reviewCount = topSetups.filter((item) => item.score < 70).length + (setup.score < 70 ? 1 : 0);
  const queueItems = [
    {
      key: 'tasks',
      label: translate(language, 'queue.label.tasks'),
      value: topSetups.length + 1,
      body: translate(language, 'queue.body.plansInCurrentWorkspace'),
    },
    {
      key: 'reviews',
      label: translate(language, 'queue.label.reviews'),
      value: reviewCount,
      body: translate(language, 'queue.body.plansNeedReview'),
    },
    {
      key: 'risks',
      label: translate(language, 'queue.label.risks'),
      value: topSetups.filter((item) => item.score < 50).length + (setup.score < 50 ? 1 : 0),
      body: translate(language, 'queue.body.weakPlansSlowing'),
    },
    {
      key: 'performance',
      label: translate(language, 'queue.label.performance'),
      value: strategy && strategy.symbol && strategy.entryZone !== 'n/a' ? 1 : 0,
      body: translate(language, 'queue.body.plansAlreadyReady'),
    },
  ];
  const finnHeadline = localizedBackendText(
    language,
    briefing?.summary?.trim(),
    translate(language, 'finn.noBriefingReady'),
  );
  const tags = [
    {
      label: translateFinnTag(
        language,
        decisionState.score >= 70 ? 'Constructive' : decisionState.score >= 50 ? 'Selective' : 'Defensive',
      ),
      tone: scoreBadgeTone(decisionState.score),
    },
    { label: translateFinnTag(language, setup.action || 'Review'), tone: setup.tone },
    { label: translate(language, 'common.confidence', { count: setup.score }), tone: 'accent' as StatusTone },
    {
      label: translateFinnTag(language, isStale ? 'Stale sync' : strategy?.status || 'Plan review'),
      tone: isStale ? ('warning' as StatusTone) : ('neutral' as StatusTone),
    },
  ];

  return (
    <WorkspaceHeroSection>
      <TodayWithFinnCard
        headline={finnHeadline}
        support={translate(language, reviewCount === 1 ? 'finn.reviewNeedsAttention' : 'finn.reviewsNeedAttention', {
          count: reviewCount,
        })}
        tags={tags}
        primaryActionLabel={translate(language, 'finn.refreshDailyScores')}
        onPrimaryAction={onAskFinn}
        queueItems={queueItems}
        queueStatusLabel={translate(language, 'common.itemsOpen', { count: Number(queueItems[0]?.value ?? 0) })}
      />
    </WorkspaceHeroSection>
  );
}

function MyPlanWorkflowIntro({ setup }: { setup: SetupSummary }) {
  const { appearance, language } = useAppPreferences();
  const colors = preferenceColors(appearance);
  const steps = [
    {
      icon: 'layers',
      title: '1 Setup',
      text: translate(language, 'myPlan.workflowStepSetup'),
    },
    {
      icon: 'activity',
      title: '2 Strategy',
      text: translate(language, 'myPlan.workflowStepStrategy'),
    },
    {
      icon: 'shield',
      title: '3 Plan',
      text: translate(language, 'myPlan.workflowStepPlan'),
    },
  ] as const;

  return (
    <View
      style={[
        styles.workspacePanel,
        { backgroundColor: colors.surface, borderColor: colors.borderSubtle },
      ]}
    >
      <Text style={[styles.workspaceEyebrow, { color: colors.textDim }]}>
        {translate(language, 'myPlan.workflowEyebrow')}
      </Text>
      <Text style={[styles.workspaceSectionTitle, { color: colors.text }]}>
        {translate(language, 'myPlan.workflowTitle')}
      </Text>
      <Text style={[styles.workflowHeroSubtitle, { color: colors.textMuted }]}>
        {translate(language, 'myPlan.workflowSubtitle')}
      </Text>

      <ScrollView
        horizontal
        showsHorizontalScrollIndicator={false}
        style={styles.workflowRail}
        contentContainerStyle={styles.workflowRailContent}
      >
        {steps.map((step, index) => (
          <View
            key={step.title}
            style={[
              styles.workflowStepCard,
              {
                backgroundColor: colors.surface,
                borderColor: colors.borderSubtle,
                marginRight: index === steps.length - 1 ? 0 : 10,
              },
            ]}
          >
            <View style={[styles.workflowStepIcon, { backgroundColor: colors.surfaceMuted }]}>
              <Feather name={step.icon} size={16} color={colors.accent} />
            </View>
            <View style={styles.workflowStepCopy}>
              <Text style={[styles.workflowStepTitle, { color: colors.text }]}>{step.title}</Text>
              <Text style={[styles.workflowStepText, { color: colors.textMuted }]} numberOfLines={2}>
                {step.text}
              </Text>
            </View>
          </View>
        ))}
      </ScrollView>

      <View style={styles.planCheckStrip}>
        <View style={styles.planCheckIcon}>
          <Feather name="zap" size={15} color="#fff" />
        </View>
        <View style={styles.flexText}>
          <Text style={styles.planCheckEyebrow}>{translate(language, 'myPlan.planCheckEyebrow')}</Text>
          <Text style={styles.planCheckText}>
            {translate(language, 'myPlan.planCheckReady', { name: setup.name })}
          </Text>
        </View>
      </View>
    </View>
  );
}

function ActivePlanWorkspaceCard({
  botDecision,
  decisionState,
  onOpenSetup,
  onOpenStrategy,
  onReviewBot,
  setup,
  strategy,
}: {
  botDecision: ReturnType<typeof mapBotDecision>;
  decisionState: ReturnType<typeof mapDecisionState>;
  onOpenSetup: () => void;
  onOpenStrategy: () => void;
  onReviewBot: () => void;
  setup: SetupSummary;
  strategy: ReturnType<typeof mapStrategy>;
}) {
  const { appearance } = useAppPreferences();
  const colors = preferenceColors(appearance);
  const planReady = strategy && strategy.symbol && strategy.entryZone !== 'n/a';

  return (
    <View style={[styles.workspacePanel, { backgroundColor: colors.surfaceMuted, borderColor: colors.borderSubtle }]}>
      <View style={styles.sectionTop}>
        <View style={styles.flexText}>
          <Text style={[styles.workspaceEyebrow, { color: colors.textDim }]}>Active plan</Text>
          <Text style={[styles.workspaceSectionTitle, { color: colors.text }]}>{setup.name}</Text>
          <Text style={[styles.workspaceMicrocopy, { color: colors.textMuted }]}>
            {setup.symbol} · {setup.timeframe} · {setup.type}
          </Text>
        </View>
        <FilledStatusBadge label={planReady ? 'Active' : 'In review'} tone={planReady ? 'success' : 'warning'} />
      </View>

      <View style={[styles.workspaceDivider, { backgroundColor: colors.borderSubtle }]} />

      <View style={[styles.planPartGroup, { backgroundColor: colors.surfaceMuted, borderColor: colors.borderSubtle }]}>
        <PlanPartRow
          actionLabel="Open setup"
          description={`${setup.trend} conditions · ${setup.action}`}
          icon="layers"
          onPress={onOpenSetup}
          summary={`${setup.score}% match`}
          title="Setup"
          value={setup.name}
        />
        <View style={[styles.planPartDivider, { backgroundColor: colors.borderSubtle }]} />
        <PlanPartRow
          actionLabel="Open strategy"
          description={planReady ? `${strategy.bias} · ${strategy.entryZone}` : 'Nog geen uitvoerbare strategy gekoppeld'}
          icon="activity"
          onPress={onOpenStrategy}
          summary={planReady ? `${strategy.confidence}% confidence` : 'Missing'}
          title="Strategy"
          value={planReady ? strategy.bias : 'No active strategy'}
        />
        <View style={[styles.planPartDivider, { backgroundColor: colors.borderSubtle }]} />
        <PlanPartRow
          actionLabel="Review bot"
          description={botDecision.reason}
          icon="shield"
          onPress={onReviewBot}
          summary={botDecision.action}
          title="Plan"
          value={decisionState.title}
        />
      </View>
    </View>
  );
}

function AllPlansListCard({
  activeSetup,
  activeStrategyName,
  planStrategies,
  setups,
  strategy,
}: {
  activeSetup: SetupSummary;
  activeStrategyName: string;
  planStrategies: Record<string, PlanStrategySummary | null>;
  setups: SetupSummary[];
  strategy: ReturnType<typeof mapStrategy>;
}) {
  const { appearance } = useAppPreferences();
  const colors = preferenceColors(appearance);
  const plans = useMemo(() => {
    const merged = [activeSetup, ...setups];
    const seen = new Set<string>();
    return merged.filter((item) => {
      const key = `${item.name}-${item.symbol}-${item.timeframe}`;
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    });
  }, [activeSetup, setups]);

  return (
    <View style={[styles.workspacePanel, { backgroundColor: colors.surface, borderColor: colors.borderSubtle }]}>
      <View style={styles.sectionTop}>
        <View style={styles.flexText}>
          <View style={styles.planListHeadingRow}>
            <Text style={[styles.workspaceSectionTitle, { color: colors.text }]}>My plans</Text>
            <StatusChip label={`${plans.length} plans`} tone="neutral" />
          </View>
          <Text style={[styles.workspaceSectionSubtitle, { color: colors.textMuted }]}>
            Setup and strategy remain visible as two parts of the same plan.
          </Text>
        </View>
      </View>

      <View style={[styles.workspaceDivider, { backgroundColor: colors.borderSubtle }]} />

      <View style={styles.planList}>
        {plans.map((plan, index) => {
          const isActive = plan.name === activeSetup.name;
          const planStrategy = plan.id ? planStrategies[String(plan.id)] : null;
          const hasStrategy = isActive
            ? Boolean(strategy && strategy.symbol && strategy.entryZone !== 'n/a')
            : Boolean(planStrategy?.exists);
          const planStatus = isActive && hasStrategy ? 'Active' : 'Draft';
          const planTone: StatusTone = planStatus === 'Active' ? 'success' : 'warning';
          const botState = isActive && hasStrategy ? 'Bot active' : 'No linked bot';
          const strategyTitle = isActive
            ? activeStrategyName
            : planStrategy?.name || 'Add strategy';

          return (
            <View
              key={`${plan.name}-${plan.symbol}-${plan.timeframe}-${index}`}
              style={[
                styles.planListRow,
                index < plans.length - 1 && { borderBottomWidth: 1, borderBottomColor: colors.borderSubtle },
              ]}
            >
              <View style={styles.planListHeader}>
                <View style={styles.flexText}>
                  <View style={styles.planListTitleRow}>
                    <Text style={[styles.planListTitle, { color: colors.text }]}>{plan.name}</Text>
                    <FilledStatusBadge label={planStatus} tone={planTone} />
                  </View>
                  <Text style={[styles.planListMeta, { color: colors.textDim }]}>
                    {plan.symbol} · {plan.timeframe}
                  </Text>
                  <Text style={[styles.planListBotState, { color: colors.textSoft }]}>
                    {botState}
                  </Text>
                </View>
              </View>

              <View style={styles.planListTiles}>
                <View style={[styles.planListTile, { backgroundColor: colors.surfaceMuted, borderColor: colors.borderSubtle }]}>
                  <View style={styles.planListTileHeader}>
                    <View style={[styles.planListTileIcon, { backgroundColor: colors.surface }]}>
                      <Feather name="layers" size={15} color={colors.accent} />
                    </View>
                    <Text style={[styles.planListTileLabel, { color: colors.textDim }]}>Setup</Text>
                  </View>
                  <View style={styles.planListTileBody}>
                    <Text style={[styles.planListTileTitle, { color: colors.text }]} numberOfLines={1}>
                      {plan.name}
                    </Text>
                    <Feather name="check" size={17} color={theme.colors.success} />
                  </View>
                </View>

                <View
                  style={[
                    styles.planListTile,
                    hasStrategy
                      ? { backgroundColor: colors.surfaceMuted, borderColor: colors.borderSubtle }
                      : styles.planListTileDraft,
                  ]}
                >
                  <View style={styles.planListTileHeader}>
                    <View style={[styles.planListTileIcon, { backgroundColor: hasStrategy ? colors.surface : '#FFF5D7' }]}>
                      <Feather name="target" size={15} color={hasStrategy ? colors.accent : theme.colors.warning} />
                    </View>
                    <Text style={[styles.planListTileLabel, { color: colors.textDim }]}>Strategy</Text>
                  </View>
                  <View style={styles.planListTileBody}>
                    <Text style={[styles.planListTileTitle, { color: colors.text }]} numberOfLines={1}>
                      {strategyTitle}
                    </Text>
                    <Feather
                      name={hasStrategy ? 'check' : 'plus'}
                      size={17}
                      color={hasStrategy ? theme.colors.success : theme.colors.warning}
                    />
                  </View>
                </View>
              </View>
            </View>
          );
        })}
      </View>
    </View>
  );
}

function PlanPartRow({
  actionLabel,
  description,
  icon,
  onPress,
  summary,
  title,
  value,
}: {
  actionLabel: string;
  description: string;
  icon: keyof typeof Feather.glyphMap;
  onPress: () => void;
  summary: string;
  title: string;
  value: string;
}) {
  const { appearance } = useAppPreferences();
  const colors = preferenceColors(appearance);

  return (
    <Pressable onPress={onPress} style={({ pressed }) => [styles.planPartRow, pressed && styles.pressed]}>
      <View style={[styles.planPartIcon, { backgroundColor: colors.surface }]}>
        <Feather name={icon} size={15} color={colors.accent} />
      </View>
      <View style={styles.planPartContent}>
        <View style={styles.planPartTop}>
          <Text style={[styles.planPartTitle, { color: colors.textDim }]}>{title}</Text>
          <Text style={[styles.planPartSummary, { color: colors.accent }]}>{summary}</Text>
        </View>
        <View style={styles.planPartBody}>
          <View style={styles.flexText}>
            <Text style={[styles.planPartValue, { color: colors.text }]} numberOfLines={1}>{value}</Text>
            <Text style={[styles.planPartDescription, { color: colors.textMuted }]} numberOfLines={2}>{description}</Text>
          </View>
          <Text style={[styles.planPartAction, { color: colors.textSoft }]}>{actionLabel}</Text>
        </View>
      </View>
    </Pressable>
  );
}

function BestMatchingSetupCard({ setup, onPress }: { setup: SetupSummary; onPress: () => void }) {
  const { appearance } = useAppPreferences();
  const colors = preferenceColors(appearance);

  return (
    <Pressable
      onPress={async () => {
        await triggerHaptic('selection');
        onPress();
      }}
      style={({ pressed }) => [pressed && styles.pressed, { paddingVertical: theme.spacing.md, paddingHorizontal: theme.spacing.lg }]}
    >
      <View style={styles.sectionTop}>
        <View style={styles.flexText}>
          <Text style={styles.kicker}>BEST MATCHING SETUP</Text>
          <Text style={[styles.matcherTitle, { color: colors.text }]}>{setup.name}</Text>
          <Text style={[styles.metaLine, { color: colors.textDim }]}>
            {setup.symbol} · {setup.timeframe} · {setup.type}
          </Text>
        </View>
        <View style={styles.matchBadge}>
          <Text style={styles.matchBadgeScore}>{setup.score}</Text>
          <Text style={styles.matchBadgeLabel}>MATCH</Text>
        </View>
      </View>
      
      <View style={styles.matchProgressTrack}>
        <View style={[styles.matchProgressFill, { width: `${setup.score}%` }]} />
      </View>
      
      <View style={styles.setupFactsRow}>
        <SetupFact label="TREND" value={setup.trend || 'neutral'} />
        <SetupFact label="ACTION" value={setup.action || 'Monitor'} />
        <SetupFact label="STATUS" value={setup.score >= 65 ? 'Active...' : 'Wait...'} />
      </View>
    </Pressable>
  );
}

function WhyFinnSelectedCard({
  asset,
  setup,
}: {
  asset?: MobileOverviewResponse['watchlist'][number];
  setup: SetupSummary;
}) {
  const { appearance } = useAppPreferences();
  const colors = preferenceColors(appearance);
  const drivers = [
    {
      label: 'Macro drivers',
      score: clampScore(asset?.macro_score ?? 0),
      text: driverCopy('macro', asset?.macro_score),
    },
    {
      label: 'Technical drivers',
      score: clampScore(asset?.technical_score ?? 0),
      text: driverCopy('technical', asset?.technical_score),
    },
    {
      label: 'Market drivers',
      score: clampScore(asset?.market_score ?? 0),
      text: driverCopy('market', asset?.market_score),
    },
  ];

  return (
    <View style={[styles.plainCard, { borderColor: colors.border }]}>
      <Text style={styles.kicker}>WHY FINN SELECTED THIS</Text>
      <Text style={[styles.plainCardTitle, { color: colors.text }]}>De match komt uit drie signalen</Text>
      <Text style={[styles.plainCardSubtitle, { color: colors.textMuted }]}>Berekend via dynamische overlap.</Text>
      <View style={styles.driverList}>
        {drivers.map((driver) => (
          <View key={driver.label} style={styles.driverRow}>
            <View style={[styles.driverDot, { backgroundColor: theme.colors.danger }]} />
            <View style={styles.flexText}>
              <Text style={[styles.driverLabel, { color: colors.text }]}>{driver.label}</Text>
              <Text style={[styles.driverText, { color: colors.textMuted }]}>{driver.text}</Text>
            </View>
            <Text style={[styles.driverScore, { color: theme.colors.danger }]}>{driver.score}</Text>
          </View>
        ))}
      </View>
    </View>
  );
}

function NextBestMatchesCard({ setups }: { setups: SetupSummary[] }) {
  const { appearance } = useAppPreferences();
  const colors = preferenceColors(appearance);

  if (setups.length === 0) return null;

  return (
    <View style={[styles.plainCard, { borderColor: colors.border }]}>
      <Text style={styles.kicker}>NEXT BEST MATCHES</Text>
      <Text style={[styles.plainCardTitle, { color: colors.text }]}>Alternatieven</Text>
      <View style={styles.compactMatchList}>
        {setups.map((setup, index) => (
          <View key={`${setup.name}-${index}`} style={[styles.compactMatchRow, index !== setups.length - 1 && { borderBottomWidth: 1, borderBottomColor: colors.border }]}>
            <View style={styles.flexText}>
              <Text style={[styles.setupName, { color: colors.text }]} numberOfLines={1}>{setup.name}</Text>
              <Text style={[styles.metaLine, { color: colors.textDim }]}>
                {setup.timeframe} · {setup.type}
              </Text>
            </View>
            <Text style={[styles.setupScoreOrange]}>{setup.score}</Text>
          </View>
        ))}
      </View>
    </View>
  );
}

function DeepSystemDetails({
  botDecision,
  decisionState,
  onAskBotWhy,
  onBotConfirm,
  onRiskExplain,
  onStrategyPress,
  setup,
  strategy,
}: {
  botDecision: ReturnType<typeof mapBotDecision>;
  decisionState: ReturnType<typeof mapDecisionState>;
  onAskBotWhy: () => void;
  onBotConfirm: () => void;
  onRiskExplain: () => void;
  onStrategyPress: () => void;
  setup: SetupSummary;
  strategy: ReturnType<typeof mapStrategy>;
}) {
  const { appearance } = useAppPreferences();
  const colors = preferenceColors(appearance);

  return (
    <View style={styles.deepSection}>
      <Text style={styles.kicker}>DEEP SYSTEM DETAILS</Text>
      <Text style={[styles.deepSectionTitle, { color: colors.text }]}>Alleen nodig bij review</Text>
      <StrategyStatusCard {...strategy} onPress={onStrategyPress} />
      <View style={{ height: 0.5, backgroundColor: colors.border, marginVertical: theme.spacing.md }} />
      <BotDecisionCard {...botDecision} onAskWhy={onAskBotWhy} onConfirm={onBotConfirm} />
      <View style={{ height: 0.5, backgroundColor: colors.border, marginVertical: theme.spacing.md }} />
      <RiskWarningCard
        severity={riskSeverity(decisionState.score, botDecision.action)}
        title={riskTitle(decisionState.score, botDecision.action)}
        body={riskBody(setup, strategy.status, botDecision.reason)}
        nextStep="Controleer setup, strategie en botstatus voordat je iets markeert of overslaat."
        onExplain={onRiskExplain}
      />
    </View>
  );
}

function SetupFact({ label, value }: { label: string; value: string }) {
  const { appearance } = useAppPreferences();
  const colors = preferenceColors(appearance);

  return (
    <View style={{ flex: 1, gap: 2 }}>
      <Text style={{ fontSize: 10, color: colors.textDim, fontWeight: '700', letterSpacing: 0.5 }}>{label.toUpperCase()}</Text>
      <Text style={{ fontSize: 13, color: colors.text, fontWeight: '700' }} numberOfLines={1}>{value}</Text>
    </View>
  );
}

function DecisionStateCard({ state, stale }: { state: ReturnType<typeof mapDecisionState>; stale: boolean }) {
  const { appearance } = useAppPreferences();
  const colors = preferenceColors(appearance);

  return (
    <CardShell emphasis="primary">
      <View style={styles.sectionTop}>
        <View>
          <Text style={styles.kicker}>System state</Text>
          <Text style={[styles.heroTitle, { color: colors.text }]}>{state.title}</Text>
        </View>
        <StatusChip label={stale ? 'Stale' : state.status} tone={stale ? 'warning' : state.tone} />
      </View>
      <View style={styles.scoreRow}>
        {state.scores.map((score) => (
          <View key={score.label} style={[styles.scoreTile, { backgroundColor: colors.backgroundSoft, borderColor: colors.border }]}>
            <Text style={[styles.scoreLabel, { color: colors.textDim }]}>{score.label}</Text>
            <Text style={[styles.scoreValue, { color: colorForScore(score.value) }]}>{score.value}</Text>
          </View>
        ))}
      </View>
      <Text style={[styles.bodyText, { color: colors.textMuted }]}>{state.reason}</Text>
      <Text style={styles.nextStep}>{state.nextStep}</Text>
    </CardShell>
  );
}

function ActiveSetupCard({ setup, onPress }: { setup: SetupSummary; onPress: () => void }) {
  const { appearance } = useAppPreferences();
  const colors = preferenceColors(appearance);
  const palette = statusTones[setup.tone];

  return (
    <Pressable
      onPress={async () => {
        await triggerHaptic('selection');
        onPress();
      }}
      style={({ pressed }) => pressed && styles.pressed}
    >
      <CardShell>
        <View style={styles.sectionTop}>
          <View>
            <Text style={styles.kicker}>Optimal setup</Text>
            <Text style={[styles.cardTitle, { color: colors.text }]}>{setup.name}</Text>
            <Text style={[styles.metaLine, { color: colors.textDim }]}>
              {setup.symbol} · {setup.timeframe} · {setup.type}
            </Text>
          </View>
          <View style={[styles.scoreBadge, { backgroundColor: palette.background, borderColor: palette.border }]}>
            <Text style={[styles.scoreBadgeValue, { color: palette.color }]}>{setup.score}</Text>
            <Text style={styles.scoreBadgeLabel}>match</Text>
          </View>
        </View>
        <View style={styles.progressTrack}>
          <View style={[styles.progressFill, { backgroundColor: palette.color, width: `${setup.score}%` }]} />
        </View>
        <View style={styles.compactGrid}>
          <MiniMetric label="Trend" value={setup.trend || 'n/a'} />
          <MiniMetric label="Action" value={setup.action || 'Review'} />
        </View>
        <Text style={[styles.bodyText, { color: colors.textMuted }]}>{setup.explanation}</Text>
      </CardShell>
    </Pressable>
  );
}

function TopSetupsCard({ setups }: { setups: SetupSummary[] }) {
  const { appearance } = useAppPreferences();
  const colors = preferenceColors(appearance);

  if (setups.length === 0) {
    return (
      <InsightCard
        label="Setup ranking"
        title="Geen top setups gevonden."
        body="De backend heeft nog geen setup-ranking teruggegeven voor deze gebruiker."
        tone="neutral"
        cta="Ververs"
      />
    );
  }

  return (
    <CardShell emphasis="muted">
      <View style={styles.sectionTop}>
        <View>
          <Text style={styles.kicker}>Setup ranking</Text>
          <Text style={[styles.cardTitle, { color: colors.text }]}>Best matching setups</Text>
        </View>
        <StatusChip label={`${setups.length} loaded`} tone="accent" />
      </View>
      <View style={styles.setupList}>
        {setups.map((setup, index) => (
          <View key={`${setup.name}-${index}`} style={[styles.setupRow, { borderColor: colors.border }]}>
            <View>
              <Text style={[styles.setupName, { color: colors.text }]}>{setup.name}</Text>
              <Text style={[styles.metaLine, { color: colors.textDim }]}>
                {setup.symbol} · {setup.timeframe} · {setup.type}
              </Text>
            </View>
            <Text style={[styles.setupScore, { color: colorForScore(setup.score) }]}>{setup.score}</Text>
          </View>
        ))}
      </View>
    </CardShell>
  );
}

function SetupSheet({ setup }: { setup: SetupSummary }) {
  const { appearance } = useAppPreferences();
  const colors = preferenceColors(appearance);

  return (
    <View style={styles.sheetStack}>
      <Text style={[styles.sheetTitle, { color: colors.text }]}>{setup.name}</Text>
      <Text style={[styles.bodyText, { color: colors.textMuted }]}>{setup.explanation}</Text>
      <View style={styles.compactGrid}>
        <MiniMetric label="Symbol" value={setup.symbol} />
        <MiniMetric label="Timeframe" value={setup.timeframe} />
        <MiniMetric label="Type" value={setup.type} />
        <MiniMetric label="Match score" value={`${setup.score}`} />
      </View>
    </View>
  );
}

function StrategySheet({
  fallback,
  strategy,
}: {
  fallback: ReturnType<typeof mapStrategy>;
  strategy?: UnknownRecord;
}) {
  const { appearance } = useAppPreferences();
  const colors = preferenceColors(appearance);
  const baseAmount = readNumber(strategy, ['base_amount'], NaN);
  const riskReward = readString(strategy, ['risk_reward'], 'n/a');
  const mode = readString(strategy, ['execution_mode'], 'n/a');

  return (
    <View style={styles.sheetStack}>
      <Text style={[styles.sheetTitle, { color: colors.text }]}>{readString(strategy, ['name'], fallback.bias)}</Text>
      <Text style={[styles.bodyText, { color: colors.textMuted }]}>{fallback.explanation}</Text>
      <View style={{ gap: 8, marginTop: theme.spacing.md }}>
        <View style={{ flexDirection: 'row', justifyContent: 'space-between' }}>
          <Text style={{ fontSize: 13, color: colors.textDim }}>Entry</Text>
          <Text style={{ fontSize: 13, color: colors.text, fontWeight: '600' }}>{fallback.entryZone}</Text>
        </View>
        <View style={{ flexDirection: 'row', justifyContent: 'space-between' }}>
          <Text style={{ fontSize: 13, color: colors.textDim }}>Targets</Text>
          <Text style={{ fontSize: 13, color: colors.text, fontWeight: '600' }}>{fallback.targets.join(' / ')}</Text>
        </View>
        <View style={{ flexDirection: 'row', justifyContent: 'space-between' }}>
          <Text style={{ fontSize: 13, color: colors.textDim }}>Stop</Text>
          <Text style={{ fontSize: 13, color: colors.text, fontWeight: '600' }}>{fallback.invalidation}</Text>
        </View>
        <View style={{ flexDirection: 'row', justifyContent: 'space-between' }}>
          <Text style={{ fontSize: 13, color: colors.textDim }}>R:R</Text>
          <Text style={{ fontSize: 13, color: colors.text, fontWeight: '600' }}>{riskReward}</Text>
        </View>
        <View style={{ flexDirection: 'row', justifyContent: 'space-between' }}>
          <Text style={{ fontSize: 13, color: colors.textDim }}>Mode</Text>
          <Text style={{ fontSize: 13, color: colors.text, fontWeight: '600' }}>{mode}</Text>
        </View>
        <View style={{ flexDirection: 'row', justifyContent: 'space-between' }}>
          <Text style={{ fontSize: 13, color: colors.textDim }}>Base</Text>
          <Text style={{ fontSize: 13, color: colors.text, fontWeight: '600' }}>{Number.isFinite(baseAmount) ? formatMoney(baseAmount, 'EUR') : 'n/a'}</Text>
        </View>
      </View>
    </View>
  );
}

function RiskSheet({
  botReasons,
  decisionState,
  setup,
}: {
  botReasons: string[];
  decisionState: ReturnType<typeof mapDecisionState>;
  setup: SetupSummary;
}) {
  const { appearance } = useAppPreferences();
  const colors = preferenceColors(appearance);

  return (
    <View style={styles.sheetStack}>
      <Text style={[styles.sheetTitle, { color: colors.text }]}>{riskTitle(decisionState.score, '')}</Text>
      <Text style={[styles.bodyText, { color: colors.textMuted }]}>
        De gecombineerde score is {decisionState.score}. Setup match is {setup.score}. Mobile toont context en
        status; uitvoering blijft expliciet en review-first.
      </Text>
      <View style={styles.ruleList}>
        {(botReasons.length > 0 ? botReasons : [decisionState.reason, setup.explanation]).slice(0, 4).map((item, index) => (
          <Text key={`${item}-${index}`} style={[styles.ruleItem, { color: colors.textMuted }]}>
            {index + 1}. {item}
          </Text>
        ))}
      </View>
    </View>
  );
}

function ConfirmBotSheet({
  actionLoading,
  actionStatus,
  botDecision,
  botMeta,
  onMarkExecuted,
  onSkip,
}: {
  actionLoading: boolean;
  actionStatus: string;
  botDecision: ReturnType<typeof mapBotDecision>;
  botMeta: BotActionMeta;
  onMarkExecuted: () => void;
  onSkip: () => void;
}) {
  const { appearance } = useAppPreferences();
  const colors = preferenceColors(appearance);
  const canSkip = Boolean(botMeta.botId);

  return (
    <View style={styles.sheetStack}>
      <Text style={[styles.sheetTitle, { color: colors.text }]}>Bevestig botactie voor {botDecision.botName}</Text>
      <Text style={[styles.bodyText, { color: colors.textMuted }]}>
        {botDecision.reason}
      </Text>
      <View style={{ gap: 8, marginTop: theme.spacing.md }}>
        <View style={{ flexDirection: 'row', justifyContent: 'space-between' }}>
          <Text style={{ fontSize: 13, color: colors.textDim }}>Context</Text>
          <Text style={{ fontSize: 13, color: colors.text, fontWeight: '600' }}>{botDecision.botName}</Text>
        </View>
        <View style={{ flexDirection: 'row', justifyContent: 'space-between' }}>
          <Text style={{ fontSize: 13, color: colors.textDim }}>Actie</Text>
          <Text style={{ fontSize: 13, color: colors.text, fontWeight: '600' }}>{botDecision.action}</Text>
        </View>
        <View style={{ flexDirection: 'row', justifyContent: 'space-between' }}>
          <Text style={{ fontSize: 13, color: colors.textDim }}>Impact</Text>
          <Text style={{ fontSize: 13, color: colors.text, fontWeight: '600' }}>{botDecision.amount}</Text>
        </View>
        <View style={{ flexDirection: 'row', justifyContent: 'space-between' }}>
          <Text style={{ fontSize: 13, color: colors.textDim }}>Vertrouwen</Text>
          <Text style={{ fontSize: 13, color: colors.text, fontWeight: '600' }}>{botDecision.confidence}</Text>
        </View>
        <View style={{ flexDirection: 'row', justifyContent: 'space-between' }}>
          <Text style={{ fontSize: 13, color: colors.textDim }}>Status</Text>
          <Text style={{ fontSize: 13, color: colors.text, fontWeight: '600' }}>{botMeta.status || 'review'}</Text>
        </View>
      </View>
      <Text style={styles.warningCopy}>Veiligheid: {botDecision.guardrail}</Text>
      <Text style={[styles.bodyText, { color: colors.textMuted }]}>
        Daarna verversen we de backend-status en laat Finn kort weten wat je nu moet monitoren.
      </Text>
      <View style={styles.sheetActions}>
        <ActionButton disabled={!canSkip || actionLoading} label="Sla botactie over" tone="warning" onPress={onSkip} />
        <ActionButton
          disabled={!botMeta.canMarkExecuted || actionLoading}
          label="Markeer botactie als uitgevoerd"
          tone="accent"
          onPress={onMarkExecuted}
        />
      </View>
      {actionStatus ? <Text style={styles.actionStatus}>{actionStatus}</Text> : null}
    </View>
  );
}

function MiniMetric({ label, value }: { label: string; value: string }) {
  const { appearance } = useAppPreferences();
  const colors = preferenceColors(appearance);

  return (
    <View style={styles.miniMetric}>
      <Text style={[styles.metricLabel, { color: colors.textDim }]}>{label}</Text>
      <Text style={[styles.metricValue, { color: colors.text }]} numberOfLines={2}>{value}</Text>
    </View>
  );
}

function ActionButton({
  disabled,
  label,
  onPress,
  tone,
}: {
  disabled: boolean;
  label: string;
  onPress: () => void;
  tone: StatusTone;
}) {
  const { appearance } = useAppPreferences();
  const colors = preferenceColors(appearance);
  const palette = statusTones[tone];

  return (
    <AppButton
      disabled={disabled}
      label={label}
      variant={tone === 'warning' ? 'secondary' : 'primary'}
      textColor={tone === 'warning' ? (disabled ? colors.textDim : palette.color) : undefined}
      onPress={async () => {
        await triggerHaptic('impact');
        onPress();
      }}
      style={tone === 'warning'
        ? {
            backgroundColor: disabled ? colors.surfaceMuted : palette.background,
            borderColor: disabled ? colors.border : palette.border,
          }
        : undefined}
    />
  );
}

function NotificationContextCard({
  activeAsset,
  notificationType,
  onAskFinn,
  onReview,
}: {
  activeAsset: string;
  notificationType: string;
  onAskFinn: () => void;
  onReview: () => void;
}) {
  const { appearance } = useAppPreferences();
  const colors = preferenceColors(appearance);
  const copy = notificationCopy(notificationType, activeAsset);

  return (
    <CardShell emphasis="primary">
      <View style={styles.sectionTop}>
        <View>
          <Text style={styles.kicker}>Push context</Text>
          <Text style={[styles.cardTitle, { color: colors.text }]}>{copy.title}</Text>
        </View>
        <StatusChip label={copy.chip} tone={copy.tone} />
      </View>
      <Text style={[styles.bodyText, { color: colors.textMuted }]}>{copy.body}</Text>
      <View style={styles.notificationActions}>
        <Pressable
          onPress={async () => {
            await triggerHaptic('selection');
            onReview();
          }}
          style={({ pressed }) => [styles.notificationPrimary, pressed && styles.pressed]}
        >
          <Text style={styles.notificationPrimaryText}>{copy.primaryCta}</Text>
        </Pressable>
      </View>
    </CardShell>
  );
}

function PlanDecisionMatrix({
  decisionState,
}: {
  decisionState: ReturnType<typeof mapDecisionState>;
}) {
  const { appearance } = useAppPreferences();
  const colors = preferenceColors(appearance);

  return (
    <View style={[styles.workspacePanel, { backgroundColor: colors.surface, borderColor: colors.borderSubtle }]}>
      <View style={styles.sectionTop}>
        <View style={styles.flexText}>
          <Text style={[styles.workspaceEyebrow, { color: colors.textDim }]}>Decision matrix</Text>
          <Text style={[styles.workspaceSectionTitle, { color: colors.text }]}>{decisionState.title}</Text>
        </View>
        <FilledStatusBadge label={`${decisionState.score}/100`} tone={decisionState.tone} />
      </View>
      <View style={styles.matrixGrid}>
        {decisionState.scores.map((item) => (
          <View key={item.label} style={[styles.matrixCell, { borderColor: colors.borderSubtle, backgroundColor: colors.surfaceMuted }]}>
            <Text style={[styles.matrixLabel, { color: colors.textDim }]}>{item.label}</Text>
            <Text style={[styles.matrixValue, { color: colors.text }]}>{item.value}</Text>
          </View>
        ))}
      </View>
      <Text style={[styles.workspaceBody, { color: colors.textMuted }]}>{decisionState.reason}</Text>
      <Text style={[styles.matrixNextStep, { color: colors.textSoft }]}>{decisionState.nextStep}</Text>
    </View>
  );
}

function FilledStatusBadge({ label, tone }: { label: string; tone: StatusTone }) {
  const { appearance } = useAppPreferences();
  const colors = preferenceColors(appearance);
  const palette = statusPalette(tone, colors);

  return (
    <View style={[styles.filledBadge, { backgroundColor: palette.background, borderColor: palette.border }]}>
      <View style={[styles.filledBadgeDot, { backgroundColor: palette.color }]} />
      <Text style={[styles.filledBadgeText, { color: palette.color }]}>{label}</Text>
    </View>
  );
}

function notificationCopy(type: string, symbol: string): {
  body: string;
  chip: string;
  primaryCta: string;
  title: string;
  tone: StatusTone;
} {
  if (type === 'strategy_invalidated') {
    return {
      body: `De ${symbol} strategie heeft aandacht nodig. Controleer eerst invalidatie, setup-context en risico voordat je iets aanpast.`,
      chip: 'Review',
      primaryCta: 'Bekijk strategie',
      title: `${symbol} strategy needs review`,
      tone: 'warning',
    };
  }

  return {
    body: `Er is een ${symbol} botbeslissing klaar. Mobile opent review-context; uitvoering blijft bewust en nooit direct vanuit push.`,
    chip: 'Bot action',
    primaryCta: 'Review botactie',
    title: `${symbol} bot decision ready`,
    tone: 'accent',
  };
}

function pushPrefill(type: string, symbol: string) {
  if (type === 'strategy_invalidated') {
    return `Leg uit waarom mijn ${symbol} strategie aandacht nodig heeft. Benoem invalidatie, risico en veilige volgende stap.`;
  }
  return `Leg deze ${symbol} botmelding uit. Waarom is review nodig en wat moet ik controleren voordat ik bevestig of oversla?`;
}

function mapSetupSummary(source?: SetupResponse, overviewAsset?: MobileOverviewResponse['watchlist'][number]): SetupSummary {
  const active = extractActiveSetup(source);
  const score = clampScore(readNumber(active, ['score', 'match_score'], overviewAsset?.setup_score ?? 0));
  const symbol = readString(active, ['symbol'], overviewAsset?.symbol ?? 'BTC');
  const name = readString(active, ['name', 'setup_name'], active ? `${symbol} setup` : 'Geen actieve setup');

  return {
    action: readString(active, ['action'], score >= 65 ? 'Monitor' : 'Wait'),
    explanation:
      readString(active, ['setup_explanation', 'ai_explanation', 'explanation'], '') ||
      (active
        ? 'De backend heeft deze setup geselecteerd op basis van overlap met de huidige macro-, technical- en market-scores.'
        : 'Er is nog geen actieve setup beschikbaar voor deze asset. Gebruik dit scherm als read-only context.'),
    id: readOptionalNumber(active, ['id', 'setup_id']),
    name,
    score,
    symbol,
    timeframe: readString(active, ['timeframe'], '1D'),
    tone: toneForScore(score),
    trend: readString(active, ['trend'], 'neutral'),
    type: readString(active, ['setup_type', 'type'], 'setup'),
    status: readString(active, ['status', 'state'], 'active'),
  };
}

function mapTopSetups(source?: SetupResponse): SetupSummary[] {
  return asArray(source).slice(0, 12).map((item) => {
    const score = clampScore(readNumber(item, ['score', 'match_score', 'setup_score'], 50));
    return {
      action: readString(item, ['action'], 'Review'),
      explanation: readString(item, ['explanation', 'setup_explanation'], 'Setup uit backend-ranking.'),
      id: readOptionalNumber(item, ['id', 'setup_id']),
      name: readString(item, ['name', 'setup_name'], 'Setup'),
      score,
      symbol: readString(item, ['symbol'], 'BTC'),
      timeframe: readString(item, ['timeframe'], '1D'),
      tone: toneForScore(score),
      trend: readString(item, ['trend'], 'neutral'),
      type: readString(item, ['setup_type', 'type'], 'setup'),
      status: readString(item, ['status', 'state'], 'active'),
    };
  });
}

function mapDecisionState(
  asset: MobileOverviewResponse['watchlist'][number] | undefined,
  setup: SetupSummary,
  botAction: string,
) {
  const macro = clampScore(asset?.macro_score ?? 0);
  const technical = clampScore(asset?.technical_score ?? 0);
  const market = clampScore(asset?.market_score ?? 0);
  const setupScore = clampScore(setup.score || asset?.setup_score || 0);
  const score = clampScore((macro + technical + market + setupScore) / 4);
  const tone = toneForScore(score);
  const action = botAction.toLowerCase();
  const status =
    score >= 70 ? 'Constructive' : score >= 50 ? 'Selective' : action.includes('hold') ? 'Hold' : 'Defensive';

  return {
    nextStep:
      action.includes('buy') || action.includes('sell')
        ? 'Open de bot review sheet en bevestig pas na risk check.'
        : 'Wacht op betere bevestiging of vraag FINN om de blokkade uit te leggen.',
    reason: `${asset?.symbol ?? setup.symbol} combineert macro ${macro}, technical ${technical}, market ${market} en setup ${setupScore}. Botactie: ${botAction}.`,
    score,
    scores: [
      { label: 'Macro', value: macro },
      { label: 'Technical', value: technical },
      { label: 'Market', value: market },
      { label: 'Setup', value: setupScore },
    ],
    status,
    title: score >= 70 ? 'Setup valid, stay selective' : score >= 50 ? 'Review before action' : 'Defensive posture',
    tone,
  };
}

function mapBotActionMeta(source?: BotResponse, decision?: UnknownRecord): BotActionMeta {
  const response = firstObject(source);
  const action = readString(decision, ['action'], '').toLowerCase();
  const reasons = readArray(decision, ['reasons', 'reason_json']).map(String);
  const tradePlan = readRecord(decision, ['trade_plan']) ?? {};

  return {
    botId: readOptionalNumber(decision, ['bot_id']),
    canMarkExecuted:
      Boolean(readOptionalNumber(decision, ['bot_id']) && readOptionalNumber(decision, ['id'])) &&
      !action.includes('hold') &&
      !action.includes('skip') &&
      !action.includes('wait'),
    decisionId: readOptionalNumber(decision, ['id', 'decision_id']),
    reasons,
    reportDate: readString(response, ['date'], ''),
    status: readString(decision, ['status'], 'review'),
    tradePlan,
  };
}

function extractActiveSetup(source?: SetupResponse) {
  const record = firstObject(source);
  const active = record?.active;
  if (isRecord(active)) {
    return {
      ...active,
      id: readOptionalNumber(active, ['id', 'setup_id']) ?? active.id,
    };
  }
  if (isRecord(record)) {
    return {
      ...record,
      id: readOptionalNumber(record, ['id', 'setup_id']) ?? record.id,
    };
  }
  return record;
}

function extractStrategy(source?: StrategyResponse) {
  const record = firstObject(source);
  if (record && record.active === false && !isRecord(record.strategy)) return undefined;
  const strategy = record?.strategy;
  return isRecord(strategy) ? strategy : record;
}

function extractBotDecision(source?: BotResponse) {
  const record = firstObject(source);
  const decisions = record?.decisions;
  if (Array.isArray(decisions)) return decisions.find(isRecord);
  return record;
}

function mapPlanStrategySummary(source?: StrategyResponse): PlanStrategySummary | null {
  const strategy = extractStrategy(source);
  if (!strategy) return null;

  return {
    exists: true,
    id: readOptionalNumber(strategy, ['id', 'strategy_id']),
    name:
      readString(strategy, ['name', 'strategy_name', 'setup_name'], '') ||
      readString(strategy, ['decision_curve_name'], 'Strategy'),
  };
}

function riskSeverity(score: number, action: string) {
  if (score < 45) return 'high' as const;
  if (action.toLowerCase().includes('buy') || action.toLowerCase().includes('sell')) return 'caution' as const;
  return 'info' as const;
}

function riskTitle(score: number, action: string) {
  if (score < 45) return 'Risk first: weak confirmation';
  if (action.toLowerCase().includes('buy') || action.toLowerCase().includes('sell')) return 'Execution requires explicit review';
  return 'Hold is also a decision';
}

function riskBody(setup: SetupSummary, strategyStatus: string, botReason: string) {
  return `${setup.name} heeft match ${setup.score}. Strategy status: ${strategyStatus}. Bot rationale: ${botReason}`;
}

function riskLabelForScore(score: number) {
  if (score >= 70) return 'Laag / stabiel';
  if (score >= 50) return 'Selectief';
  return 'Defensief';
}

function driverCopy(type: 'macro' | 'technical' | 'market', score?: number | null) {
  const value = clampScore(score ?? 0);
  if (type === 'macro') {
    if (value >= 70) return 'Macro ondersteunt risk-on, maar FINN blijft selectief.';
    if (value >= 45) return 'Macro is gemengd en vraagt om bevestiging.';
    return 'Macro blokkeert agressieve setup-keuzes.';
  }
  if (type === 'technical') {
    if (value >= 70) return 'Technicals bevestigen de setupkwaliteit.';
    if (value >= 45) return 'Technicals zijn bruikbaar, maar nog niet schoon.';
    return 'Technicals zijn zwak; timing krijgt extra frictie.';
  }
  if (value >= 70) return 'Market context geeft voldoende steun voor monitoring.';
  if (value >= 45) return 'Market context is neutraal en vraagt geduld.';
  return 'Market context verhoogt de kans op false starts.';
}

function latestLabel(labels: string[]) {
  return labels.find(Boolean) ?? nowLabel();
}

function firstObject(value: unknown): UnknownRecord | undefined {
  if (Array.isArray(value)) return value.find(isRecord);
  return isRecord(value) ? value : undefined;
}

function asArray(value: unknown): UnknownRecord[] {
  if (Array.isArray(value)) return value.filter(isRecord);
  if (isRecord(value)) return [value];
  return [];
}

function isRecord(value: unknown): value is UnknownRecord {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function readRecord(source: UnknownRecord | undefined, keys: string[]) {
  for (const key of keys) {
    const value = source?.[key];
    if (isRecord(value)) return value;
  }
  return undefined;
}

function readArray(source: UnknownRecord | undefined, keys: string[]) {
  for (const key of keys) {
    const value = source?.[key];
    if (Array.isArray(value)) return value;
  }
  return [];
}

function readString(source: UnknownRecord | undefined, keys: string[], fallback = '') {
  for (const key of keys) {
    const value = source?.[key];
    if (typeof value === 'string' && value.trim()) return value;
    if (typeof value === 'number' && Number.isFinite(value)) return String(value);
  }
  return fallback;
}

function readNumber(source: UnknownRecord | undefined, keys: string[], fallback = 0) {
  for (const key of keys) {
    const value = source?.[key];
    if (typeof value === 'number' && Number.isFinite(value)) return value;
    if (typeof value === 'string' && Number.isFinite(Number(value))) return Number(value);
  }
  return fallback;
}

function readOptionalNumber(source: UnknownRecord | undefined, keys: string[]) {
  const value = readNumber(source, keys, NaN);
  return Number.isFinite(value) ? value : undefined;
}

function clampScore(value: number) {
  if (!Number.isFinite(value)) return 0;
  return Math.max(0, Math.min(100, Math.round(value)));
}

function toneForScore(score: number): StatusTone {
  if (score >= 70) return 'success';
  if (score >= 55) return 'accent';
  if (score >= 40) return 'warning';
  return 'danger';
}

function scoreBadgeTone(score: number): StatusTone {
  if (score >= 70) return 'success';
  if (score >= 50) return 'accent';
  if (score >= 35) return 'warning';
  return 'danger';
}

function statusPalette(tone: StatusTone, colors: ReturnType<typeof preferenceColors>) {
  const softMap: Record<StatusTone, { background: string; border: string; color: string }> = {
    accent: { background: '#E8F0FF', border: '#C7D7FE', color: colors.accent },
    success: { background: '#EAF9F3', border: '#C8EFD9', color: colors.success },
    warning: { background: '#FEF5E7', border: '#F9D9A7', color: colors.warning },
    danger: { background: '#FDECEF', border: '#F8C7D1', color: colors.danger },
    neutral: { background: colors.surfaceMuted, border: colors.borderSubtle, color: colors.textDim },
  };
  return softMap[tone];
}

function colorForScore(score: number) {
  return statusTones[toneForScore(score)].color;
}

function formatMoney(value: number, currency: 'EUR' | 'USD' = 'EUR') {
  return new Intl.NumberFormat('nl-NL', {
    currency,
    maximumFractionDigits: value > 1000 ? 0 : 2,
    style: 'currency',
  }).format(value);
}

function Tag({ label, tone }: { label: string; tone: StatusTone }) {
  return (
    <View style={[styles.tag, { borderColor: statusTones[tone].color }]}>
      <Text style={[styles.tagText, { color: statusTones[tone].color }]}>{label}</Text>
    </View>
  );
}

function BotMetric({ label, tone, value }: { label: string; tone: StatusTone; value: string }) {
  return (
    <View style={styles.botMetric}>
      <Text style={[styles.metricLabel, { color: theme.colors.textDim }]}>{label}</Text>
      <Text style={[styles.botMetricValue, { color: statusTones[tone].color }]}>{value}</Text>
    </View>
  );
}

function StrategyListCard({ strat }: { strat: any }) {
  const { appearance } = useAppPreferences();
  const colors = preferenceColors(appearance);
  const { openFinn } = useFinnOverlay();
  const target = firstStrategyTarget(strat.targets);
  const riskReward = normalizeRiskReward(strat.risk_reward);
  const entry = formatStrategyPrice(strat.entry);
  const stop = formatStrategyPrice(strat.stop_loss);
  const targetLabel = formatStrategyPrice(target);
  const statusTone: StatusTone = strat.status === 'active' ? 'success' : 'neutral';

  return (
    <TouchableOpacity
      style={[styles.botRow, { borderBottomColor: theme.colors.border }]}
      onPress={() => {
        openFinn({
          prefill: `Help me de strategie '${strat.name}' aan te passen.`,
          source: 'strategy-edit',
          symbol: strat.symbol,
        });
      }}
    >
      <View style={{ backgroundColor: '#F1F5F9', padding: 6, borderRadius: 4, marginBottom: theme.spacing.sm }}>
        <Text style={{ color: '#475569', fontSize: 10, fontWeight: '900', letterSpacing: 1.2 }}>
          {strat.setup_name?.toUpperCase() || strat.name?.toUpperCase() || 'SETUP'} {'>'} {strat.name?.toUpperCase() || 'STRATEGIE'}
        </Text>
      </View>

      <View style={styles.strategyCardMetaRow}>
        <Text style={[styles.strategyBreadcrumb, { color: colors.textDim }]} numberOfLines={1}>
          {strat.symbol || 'BTC'}  /  {strat.setup_type || 'TRADE'}
        </Text>
        <StatusChip label={strat.status || 'stand-by'} tone={statusTone} />
      </View>

      <Text style={[styles.strategyCardTitle, { color: colors.text }]} numberOfLines={2}>
        {strat.name || 'Naamloze strategie'}
      </Text>

      <View style={styles.strategyTypeRow}>
        <Tag label={strat.setup_type?.toUpperCase() || 'TRADE'} tone="accent" />
        <Tag label={strat.timeframe || '1W'} tone="neutral" />
        <Text style={[styles.strategyBotState, { color: colors.textDim }]}>Geen bot</Text>
      </View>

      <View style={styles.botMetricGrid}>
        <StrategyPlanMetric label="Instap" value={entry} tone="accent" />
        <StrategyPlanMetric label="Doelen" value={targetLabel} tone="success" />
        <StrategyPlanMetric label="Stop-loss" value={stop} tone="danger" />
        <StrategyPlanMetric label="R/R" value={riskReward} tone="success" />
      </View>

      <View style={{ marginTop: theme.spacing.md }}>
        <Text style={[styles.metricLabel, { marginBottom: 4 }]}>Uitvoering</Text>
        <ExecutionStep label="TP1" value={targetLabel} tone="success" />
        <ExecutionStep label="Instap" value={entry} tone="accent" />
        <ExecutionStep label="Stop" value={stop} tone="danger" />
      </View>

      {strat.explanation ? (
        <View style={styles.strategyExplanation}>
          <Text style={styles.strategyExplanationLabel}>Toelichting</Text>
          <Text style={[styles.strategyExplanationText, { color: colors.textSoft }]}>{strat.explanation}</Text>
        </View>
      ) : null}
    </TouchableOpacity>
  );
}

function StrategyPlanMetric({
  label,
  tone,
  value,
}: {
  label: string;
  tone: StatusTone;
  value: string;
}) {
  return (
    <View style={styles.botMetric}>
      <Text style={styles.metricLabel}>{label}</Text>
      <Text style={[styles.botMetricValue, { color: statusTones[tone].color }]}>{value}</Text>
    </View>
  );
}

function ExecutionStep({
  label,
  tone,
  value,
}: {
  label: string;
  tone: StatusTone;
  value: string;
}) {
  return (
    <View style={{ flexDirection: 'row', justifyContent: 'space-between', paddingVertical: 4 }}>
      <Text style={{ color: theme.colors.textDim }}>{label}</Text>
      <Text style={{ color: statusTones[tone].color, fontWeight: 'bold' }}>{value}</Text>
    </View>
  );
}

function firstStrategyTarget(value: unknown) {
  if (Array.isArray(value)) return value[0];
  if (typeof value !== 'string') return value;
  return value
    .split(/[,\n/|]+/)
    .map((item) => item.trim())
    .filter(Boolean)[0] ?? value;
}

function normalizeRiskReward(value: unknown) {
  const raw = String(value ?? '').trim();
  if (!raw || raw.toLowerCase() === 'n/a') return 'n/a';
  return raw.startsWith('1:') ? raw : `1:${raw}`;
}

function formatStrategyPrice(value: unknown) {
  if (value === null || value === undefined || value === '') return 'n/a';
  const numeric = Number(String(value).replace(/[^0-9.-]/g, ''));
  if (!Number.isFinite(numeric)) return String(value);
  return new Intl.NumberFormat('en-US', {
    currency: 'USD',
    maximumFractionDigits: numeric >= 1000 ? 0 : 2,
    style: 'currency',
  }).format(numeric);
}

const styles = StyleSheet.create({
  filledBadge: {
    alignItems: 'center',
    borderRadius: theme.radius.pill,
    borderWidth: 1,
    flexDirection: 'row',
    gap: 6,
    paddingHorizontal: 12,
    paddingVertical: 7,
  },
  filledBadgeDot: {
    borderRadius: 999,
    height: 7,
    width: 7,
  },
  filledBadgeRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: theme.spacing.xs,
    marginTop: theme.spacing.sm,
  },
  filledBadgeText: {
    fontSize: 11,
    fontWeight: '900',
    letterSpacing: 0.8,
    textTransform: 'uppercase',
  },
  heroMetaGrid: {
    flexDirection: 'row',
    gap: theme.spacing.sm,
    marginTop: theme.spacing.md,
  },
  heroMetaLabel: {
    fontSize: 10,
    fontWeight: '900',
    letterSpacing: 1.2,
    textTransform: 'uppercase',
  },
  heroMetaTile: {
    borderRadius: 18,
    borderWidth: 1,
    flex: 1,
    gap: 4,
    paddingHorizontal: theme.spacing.md,
    paddingVertical: 14,
  },
  heroMetaValue: {
    fontSize: 16,
    fontWeight: '900',
    lineHeight: 20,
  },
  todayFinnBadgeContent: {
    paddingRight: 8,
  },
  todayFinnBadgeRail: {
    marginTop: 12,
  },
  todayFinnDot: {
    borderRadius: 999,
    height: 8,
    width: 8,
  },
  todayFinnHeader: {
    alignItems: 'center',
    flexDirection: 'row',
    gap: 8,
  },
  planPartAction: {
    fontSize: 11,
    fontWeight: '900',
    letterSpacing: 0.5,
    marginTop: 2,
    textTransform: 'uppercase',
  },
  planPartBody: {
    flexDirection: 'row',
    gap: 12,
    justifyContent: 'space-between',
    marginTop: 3,
  },
  planPartContent: {
    flex: 1,
    gap: 4,
  },
  planPartDescription: {
    fontSize: 12,
    fontWeight: '600',
    lineHeight: 17,
  },
  planPartDivider: {
    height: 1,
    marginLeft: 52,
  },
  planPartGroup: {
    borderRadius: 20,
    borderWidth: 1,
    marginTop: theme.spacing.md,
    overflow: 'hidden',
  },
  planPartIcon: {
    alignItems: 'center',
    borderRadius: 14,
    height: 38,
    justifyContent: 'center',
    width: 38,
  },
  planPartRow: {
    alignItems: 'flex-start',
    flexDirection: 'row',
    gap: 12,
    paddingHorizontal: theme.spacing.md,
    paddingVertical: 14,
  },
  planPartSummary: {
    fontSize: 10,
    fontWeight: '900',
    letterSpacing: 0.8,
    textTransform: 'uppercase',
  },
  planPartTitle: {
    fontSize: 10,
    fontWeight: '900',
    letterSpacing: 1.4,
    textTransform: 'uppercase',
  },
  planPartTop: {
    alignItems: 'center',
    flexDirection: 'row',
    justifyContent: 'space-between',
  },
  planPartValue: {
    fontSize: 16,
    fontWeight: '900',
    lineHeight: 20,
    marginTop: 1,
  },
  primaryActionButton: {
    alignItems: 'center',
    backgroundColor: theme.colors.accent,
    borderRadius: theme.radius.pill,
    justifyContent: 'center',
    marginTop: theme.spacing.md,
    minHeight: 52,
    paddingHorizontal: theme.spacing.lg,
  },
  primaryActionButtonText: {
    color: '#ffffff',
    fontSize: 13,
    fontWeight: '900',
    letterSpacing: 1.1,
    textTransform: 'uppercase',
  },
  planList: {
    gap: 0,
  },
  planListBotState: {
    fontSize: 11,
    fontWeight: '900',
    letterSpacing: 1.1,
    marginTop: 4,
    textTransform: 'uppercase',
  },
  planListHeadingRow: {
    alignItems: 'center',
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
  },
  planListHeader: {
    gap: 6,
  },
  planListMeta: {
    fontSize: 12,
    fontWeight: '700',
    marginTop: 4,
    textTransform: 'uppercase',
  },
  planListRow: {
    gap: 12,
    paddingVertical: 14,
  },
  planListTile: {
    borderRadius: 18,
    borderWidth: 1,
    flex: 1,
    gap: 8,
    minHeight: 84,
    paddingHorizontal: 12,
    paddingVertical: 12,
  },
  planListTileBody: {
    alignItems: 'center',
    flexDirection: 'row',
    gap: 8,
    justifyContent: 'space-between',
  },
  planListTileDraft: {
    backgroundColor: '#FFFBEF',
    borderColor: '#F7D77A',
    borderStyle: 'dashed',
  },
  planListTileHeader: {
    alignItems: 'center',
    flexDirection: 'row',
    gap: 8,
  },
  planListTileIcon: {
    alignItems: 'center',
    borderRadius: 14,
    height: 34,
    justifyContent: 'center',
    width: 34,
  },
  planListTileLabel: {
    fontSize: 11,
    fontWeight: '700',
  },
  planListTileTitle: {
    fontSize: 14,
    fontWeight: '800',
    lineHeight: 18,
    marginTop: 0,
    minWidth: 0,
    flex: 1,
  },
  planListTiles: {
    flexDirection: 'row',
    gap: 10,
  },
  planListTitle: {
    fontSize: 15,
    fontWeight: '900',
    lineHeight: 20,
  },
  planListTitleRow: {
    alignItems: 'center',
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
  },
  queueBody: {
    fontSize: 12,
    fontWeight: '600',
    lineHeight: 17,
  },
  queueCard: {
    borderRadius: 18,
    borderWidth: 1,
    gap: 6,
    minHeight: 100,
    paddingHorizontal: 12,
    paddingVertical: 12,
    width: '47.2%',
  },
  queueGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
    justifyContent: 'space-between',
    marginTop: 12,
  },
  queueLabel: {
    fontSize: 13,
    fontWeight: '800',
  },
  queueValue: {
    fontSize: 22,
    fontWeight: '900',
  },
  planCheckEyebrow: {
    color: '#DBEAFE',
    fontSize: 10,
    fontWeight: '900',
    letterSpacing: 1.2,
    textTransform: 'uppercase',
  },
  planCheckIcon: {
    alignItems: 'center',
    backgroundColor: theme.colors.accent,
    borderRadius: 18,
    height: 42,
    justifyContent: 'center',
    width: 42,
  },
  planCheckStrip: {
    alignItems: 'center',
    backgroundColor: theme.colors.accent,
    borderRadius: 20,
    flexDirection: 'row',
    gap: 12,
    marginTop: 14,
    paddingHorizontal: 14,
    paddingVertical: 14,
  },
  planCheckText: {
    color: '#ffffff',
    fontSize: 14,
    fontWeight: '800',
    lineHeight: 19,
  },
  workflowHeroSubtitle: {
    fontSize: 13,
    fontWeight: '600',
    lineHeight: 18,
    marginTop: 2,
  },
  workflowStepCopy: {
    flex: 1,
    gap: 4,
    justifyContent: 'center',
  },
  workflowRail: {
    marginTop: 12,
  },
  workflowRailContent: {
    paddingRight: 42,
  },
  workflowStepIcon: {
    alignItems: 'center',
    borderRadius: 16,
    height: 40,
    justifyContent: 'center',
    width: 40,
  },
  workflowStepCard: {
    borderRadius: 18,
    borderWidth: 1,
    flexDirection: 'row',
    gap: 10,
    minHeight: 84,
    paddingHorizontal: 12,
    paddingVertical: 12,
    width: 228,
  },
  workflowStepText: {
    fontSize: 12,
    fontWeight: '600',
    lineHeight: 17,
  },
  workflowStepTitle: {
    fontSize: 14,
    fontWeight: '900',
    lineHeight: 18,
  },
  workspaceBody: {
    fontSize: 15,
    fontWeight: '600',
    lineHeight: 24,
  },
  workspaceEyebrow: {
    fontSize: 11,
    fontWeight: '900',
    letterSpacing: 2.2,
    textTransform: 'uppercase',
  },
  workspaceHeadline: {
    fontSize: 28,
    fontWeight: '900',
    letterSpacing: -0.8,
    lineHeight: 34,
  },
  workspaceHeadlineCompact: {
    fontSize: 19,
    lineHeight: 28,
    marginTop: 4,
  },
  workspaceLead: {
    fontSize: 15,
    fontWeight: '700',
    marginTop: 6,
  },
  workspaceMicrocopy: {
    fontSize: 12,
    fontWeight: '700',
    lineHeight: 17,
    marginTop: 3,
    textTransform: 'uppercase',
  },
  workspaceMutedPanel: {
    marginTop: 0,
  },
  workspacePanel: {
    backgroundColor: 'transparent',
    borderColor: 'transparent',
    borderRadius: 28,
    borderWidth: 1,
    gap: theme.spacing.sm,
    marginHorizontal: theme.spacing.lg,
    marginTop: 0,
    paddingHorizontal: 20,
    paddingVertical: 20,
  },
  workspaceSectionCopy: {
    flex: 1,
    gap: 6,
  },
  workspaceSectionHeader: {
    alignItems: 'flex-start',
    flexDirection: 'row',
    gap: 12,
    justifyContent: 'space-between',
  },
  workspaceSectionSubtitle: {
    fontSize: 16,
    fontWeight: '600',
    lineHeight: 24,
  },
  workspaceSectionTitle: {
    fontSize: 18,
    fontWeight: '900',
    lineHeight: 24,
  },
  workspaceSubsectionHeader: {
    alignItems: 'center',
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginTop: 2,
  },
  workspaceDivider: {
    height: 1,
    marginTop: 4,
  },
  botTop: {
    alignItems: 'center',
    flexDirection: 'row',
    gap: theme.spacing.md,
  },
  botRow: {
    borderBottomWidth: 0.5,
    paddingVertical: theme.spacing.md,
    paddingHorizontal: theme.spacing.lg,
    gap: theme.spacing.md,
  },
  botIcon: {
    alignItems: 'center',
    backgroundColor: 'transparent',
    borderColor: theme.colors.border,
    borderRadius: theme.radius.md,
    borderWidth: 1,
    height: 54,
    justifyContent: 'center',
    width: 54,
  },
  botIconText: {
    color: theme.colors.accent,
    fontSize: theme.typography.body,
    fontWeight: '900',
  },
  botTitleBlock: {
    flex: 1,
  },
  botNameRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: theme.spacing.sm,
  },
  botName: {
    fontSize: 16,
    fontWeight: 'bold',
  },
  statusDot: {
    width: 10,
    height: 10,
    borderRadius: 5,
  },
  botMeta: {
    color: theme.colors.textDim,
    fontSize: theme.typography.label,
    fontWeight: '900',
    letterSpacing: 1.2,
    marginTop: 6,
    textTransform: 'uppercase',
  },
  botChips: {
    flexDirection: 'row',
    gap: theme.spacing.sm,
  },
  botMetricGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    justifyContent: 'space-between',
  },
  botMetric: {
    flex: 1,
    minWidth: '45%',
    paddingVertical: theme.spacing.sm,
  },
  botMetricValue: {
    fontSize: 14,
    fontWeight: 'bold',
  },
  botFooter: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginTop: theme.spacing.sm,
  },
  botFooterText: {
    fontSize: 12,
  },
  metricLabel: {
    color: theme.colors.textDim,
    fontSize: theme.typography.label,
    fontWeight: '900',
    letterSpacing: 1.2,
    textTransform: 'uppercase',
  },
  tag: {
    backgroundColor: 'transparent',
    borderRadius: theme.radius.pill,
    borderWidth: 1,
    paddingHorizontal: theme.spacing.md,
    paddingVertical: theme.spacing.sm,
  },
  tagText: {
    fontSize: theme.typography.label,
    fontWeight: '900',
    letterSpacing: 1.5,
    textTransform: 'uppercase',
  },
  strategyListCard: {
    backgroundColor: theme.colors.surface,
    borderColor: theme.colors.border,
    borderRadius: theme.radius.card,
    borderWidth: 1,
    gap: theme.spacing.md,
    marginBottom: theme.spacing.md,
    padding: theme.spacing.md,
  },
  strategyCardMetaRow: {
    alignItems: 'center',
    flexDirection: 'row',
    gap: theme.spacing.sm,
    justifyContent: 'space-between',
  },
  strategyBreadcrumb: {
    color: theme.colors.textDim,
    flex: 1,
    fontSize: theme.typography.label,
    fontWeight: '900',
    letterSpacing: 1.4,
    textTransform: 'uppercase',
  },
  strategyCardTitle: {
    color: theme.colors.text,
    fontSize: 22,
    fontWeight: '900',
    lineHeight: 26,
  },
  strategyTypeRow: {
    alignItems: 'center',
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: theme.spacing.sm,
  },
  strategyBotState: {
    color: theme.colors.textDim,
    fontSize: theme.typography.label,
    fontWeight: '900',
    letterSpacing: 1.2,
    textTransform: 'uppercase',
  },
  strategyPlanGrid: {
    gap: theme.spacing.sm,
  },
  strategyPlanMetric: {
    backgroundColor: theme.colors.surfaceElevated,
    borderRadius: theme.radius.card,
    borderWidth: 1,
    paddingHorizontal: theme.spacing.md,
    paddingVertical: theme.spacing.md,
  },
  strategyPlanLabel: {
    fontSize: theme.typography.label,
    fontWeight: '900',
    letterSpacing: 1.3,
    textTransform: 'uppercase',
  },
  strategyPlanValue: {
    color: theme.colors.text,
    fontSize: 24,
    fontWeight: '900',
    marginTop: theme.spacing.xs,
  },
  strategyRiskPanel: {
    backgroundColor: theme.colors.surfaceMuted,
    borderRadius: theme.radius.card,
    gap: theme.spacing.md,
    padding: theme.spacing.md,
  },
  strategyRiskHeader: {
    alignItems: 'flex-start',
    flexDirection: 'row',
    gap: theme.spacing.md,
    justifyContent: 'space-between',
  },
  strategyRiskLabel: {
    color: theme.colors.textSoft,
    fontSize: theme.typography.label,
    fontWeight: '900',
    letterSpacing: 1.4,
    textTransform: 'uppercase',
  },
  strategyRiskValue: {
    color: theme.colors.white,
    fontSize: 30,
    fontWeight: '900',
    marginTop: 2,
  },
  strategyRiskChips: {
    alignItems: 'flex-end',
    gap: theme.spacing.xs,
  },
  strategyRiskChip: {
    borderRadius: theme.radius.pill,
    fontSize: 10,
    fontWeight: '900',
    overflow: 'hidden',
    paddingHorizontal: theme.spacing.sm,
    paddingVertical: 5,
    textTransform: 'uppercase',
  },
  strategyRiskChipDanger: {
    backgroundColor: '#7F1D1D88',
    color: '#FCA5A5',
  },
  strategyRiskChipSuccess: {
    backgroundColor: '#065F4688',
    color: '#6EE7B7',
  },
  strategyRiskTrack: {
    backgroundColor: theme.colors.borderStrong,
    borderRadius: theme.radius.pill,
    flexDirection: 'row',
    height: 10,
    overflow: 'hidden',
  },
  strategyRiskLoss: {
    backgroundColor: '#EF4444',
    flex: 1,
  },
  strategyRiskGain: {
    backgroundColor: '#22C55E',
    flex: 2.55,
  },
  executionLadder: {
    borderColor: theme.colors.borderSubtle,
    borderRadius: theme.radius.card,
    borderWidth: 1,
    gap: theme.spacing.sm,
    padding: theme.spacing.md,
  },
  executionTitle: {
    color: theme.colors.text,
    fontSize: theme.typography.label,
    fontWeight: '900',
    letterSpacing: 1.4,
    marginBottom: theme.spacing.xs,
    textTransform: 'uppercase',
  },
  executionStep: {
    alignItems: 'center',
    borderRadius: theme.radius.md,
    borderWidth: 1,
    flexDirection: 'row',
    justifyContent: 'space-between',
    paddingHorizontal: theme.spacing.md,
    paddingVertical: theme.spacing.sm,
  },
  executionStepLabel: {
    fontSize: theme.typography.label,
    fontWeight: '900',
    letterSpacing: 0.8,
    textTransform: 'uppercase',
  },
  executionStepValue: {
    fontSize: 15,
    fontWeight: '900',
  },
  strategyExplanation: {
    backgroundColor: '#FAF5FF',
    borderColor: '#E9D5FF',
    borderRadius: theme.radius.card,
    borderWidth: 1,
    padding: theme.spacing.md,
  },
  strategyExplanationLabel: {
    color: '#8B5CF6',
    fontSize: theme.typography.label,
    fontWeight: '900',
    letterSpacing: 1.4,
    marginBottom: theme.spacing.xs,
    textTransform: 'uppercase',
  },
  strategyExplanationText: {
    color: theme.colors.textSoft,
    fontSize: theme.typography.small,
    fontWeight: '600',
    lineHeight: 19,
  },
  tabBar: {
    flexDirection: 'row',
    gap: 4,
    marginBottom: theme.spacing.md,
    marginHorizontal: theme.spacing.lg,
    padding: 2,
  },
  tabButton: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 6,
    borderRadius: theme.radius.pill,
  },
  tabButtonText: {
    fontSize: 11,
    fontWeight: '700',
    textTransform: 'uppercase',
    letterSpacing: 0.5,
  },
  actionStatus: {
    color: theme.colors.textMuted,
    fontSize: theme.typography.small,
    fontWeight: '700',
    lineHeight: 19,
  },
  bodyText: {
    color: theme.colors.textMuted,
    fontSize: theme.typography.body,
    fontWeight: '600',
    lineHeight: 22,
    marginTop: theme.spacing.md,
  },
  cardTitle: {
    color: theme.colors.text,
    fontSize: theme.typography.title,
    fontWeight: '900',
    lineHeight: 27,
    marginTop: 5,
  },
  briefingCopy: {
    color: theme.colors.textMuted,
    fontSize: 18,
    fontWeight: '800',
    lineHeight: 27,
    marginTop: theme.spacing.lg,
  },
  briefingMetaRow: {
    flexDirection: 'row',
    gap: theme.spacing.sm,
    marginTop: theme.spacing.lg,
  },
  briefingMetric: {
    borderRadius: theme.radius.md,
    borderWidth: 1,
    flex: 1,
    minHeight: 82,
    padding: theme.spacing.md,
  },
  briefingMetricValue: {
    fontSize: 18,
    fontWeight: '900',
    lineHeight: 24,
    marginTop: 6,
  },
  compactGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: theme.spacing.sm,
    marginTop: theme.spacing.md,
  },
  compactMatchList: {
    gap: theme.spacing.sm,
    marginTop: theme.spacing.lg,
  },
  compactMatchRow: {
    alignItems: 'center',
    borderBottomWidth: 1,
    flexDirection: 'row',
    gap: theme.spacing.md,
    justifyContent: 'space-between',
    paddingVertical: theme.spacing.md,
  },
  deepSection: {
    gap: theme.spacing.md,
    marginTop: theme.spacing.sm,
    paddingHorizontal: theme.spacing.lg,
  },
  deepSectionTitle: {
    color: theme.colors.text,
    fontSize: theme.typography.title,
    fontWeight: '900',
    lineHeight: 28,
  },
  driverDot: {
    borderRadius: theme.radius.pill,
    height: 8,
    marginTop: 7,
    width: 8,
  },
  driverLabel: {
    color: theme.colors.text,
    fontSize: theme.typography.body,
    fontWeight: '900',
  },
  driverList: {
    gap: theme.spacing.md,
    marginTop: theme.spacing.lg,
  },
  driverRow: {
    alignItems: 'flex-start',
    flexDirection: 'row',
    gap: theme.spacing.sm,
  },
  driverScore: {
    fontSize: theme.typography.body,
    fontWeight: '900',
    minWidth: 34,
    textAlign: 'right',
  },
  driverText: {
    color: theme.colors.textMuted,
    fontSize: theme.typography.small,
    fontWeight: '700',
    lineHeight: 19,
    marginTop: 3,
  },
  flexText: {
    flex: 1,
  },
  heroTitle: {
    color: theme.colors.text,
    fontSize: 18,
    fontWeight: '700',
    lineHeight: 22,
    marginTop: 5,
  },
  kicker: {
    color: theme.colors.accent,
    fontSize: theme.typography.label,
    fontWeight: '700',
    letterSpacing: 1.7,
    textTransform: 'uppercase',
  },
  metaLine: {
    color: theme.colors.textDim,
    fontSize: theme.typography.small,
    fontWeight: '800',
    lineHeight: 18,
    marginTop: 5,
  },
  matcherHeader: {
    alignItems: 'flex-start',
    flexDirection: 'row',
    gap: theme.spacing.md,
    justifyContent: 'space-between',
  },
  matcherTitle: {
    color: theme.colors.text,
    fontSize: 18,
    fontWeight: '900',
    lineHeight: 22,
    marginTop: 5,
  },
  metricValue: {
    color: theme.colors.text,
    fontSize: 16,
    fontWeight: '600',
    lineHeight: 20,
    marginTop: 2,
  },
  miniMetric: {
    flexBasis: '47%',
    flexGrow: 1,
    paddingVertical: theme.spacing.sm,
    gap: 2,
  },
  nextStep: {
    color: theme.colors.textSoft,
    fontSize: theme.typography.small,
    fontWeight: '900',
    lineHeight: 19,
    marginTop: theme.spacing.sm,
  },
  notificationActions: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: theme.spacing.sm,
    marginTop: theme.spacing.lg,
  },
  notificationPrimary: {
    alignItems: 'center',
    backgroundColor: theme.colors.accent,
    borderRadius: theme.radius.button,
    flexGrow: 1,
    justifyContent: 'center',
    minHeight: 48,
    paddingHorizontal: theme.spacing.md,
  },
  notificationPrimaryText: {
    color: theme.colors.white,
    fontSize: 12,
    fontWeight: '900',
    letterSpacing: 1,
    textTransform: 'uppercase',
  },
  notificationSecondary: {
    alignItems: 'center',
    borderColor: theme.colors.borderStrong,
    borderRadius: theme.radius.button,
    borderWidth: 1,
    flexGrow: 1,
    justifyContent: 'center',
    minHeight: 48,
    paddingHorizontal: theme.spacing.md,
  },
  notificationSecondaryText: {
    color: theme.colors.textSoft,
    fontSize: 12,
    fontWeight: '900',
    letterSpacing: 1,
    textTransform: 'uppercase',
  },
  pressed: {
    opacity: 0.86,
    transform: [{ scale: 0.995 }],
  },
  primaryAction: {
    alignItems: 'center',
    backgroundColor: theme.colors.text,
    borderRadius: theme.radius.button,
    justifyContent: 'center',
    marginTop: theme.spacing.lg,
    minHeight: 50,
    paddingHorizontal: theme.spacing.md,
  },
  primaryActionText: {
    color: theme.colors.white,
    fontSize: 12,
    fontWeight: '900',
    letterSpacing: 1,
    textTransform: 'uppercase',
  },
  progressFill: {
    borderRadius: theme.radius.pill,
    height: 7,
  },
  progressTrack: {
    backgroundColor: theme.colors.backgroundSoft,
    borderRadius: theme.radius.pill,
    height: 7,
    marginTop: theme.spacing.lg,
    overflow: 'hidden',
  },
  ruleItem: {
    color: theme.colors.textMuted,
    fontSize: theme.typography.body,
    fontWeight: '700',
    lineHeight: 22,
  },
  ruleList: {
    gap: theme.spacing.sm,
    marginTop: theme.spacing.md,
  },
  scoreBadge: {
    alignItems: 'center',
    borderRadius: theme.radius.md,
    borderWidth: 1,
    minWidth: 78,
    padding: theme.spacing.sm,
  },
  scoreBadgeLabel: {
    color: theme.colors.textDim,
    fontSize: 10,
    fontWeight: '900',
    marginTop: 2,
    textTransform: 'uppercase',
  },
  scoreBadgeValue: {
    fontSize: 18,
    fontWeight: '900',
  },
  scoreLabel: {
    color: theme.colors.textDim,
    fontSize: theme.typography.label,
    fontWeight: '900',
    letterSpacing: 1.3,
    textTransform: 'uppercase',
  },
  scoreRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: theme.spacing.sm,
    marginTop: theme.spacing.lg,
  },
  scoreTile: {
    backgroundColor: theme.colors.backgroundSoft,
    borderColor: theme.colors.border,
    borderRadius: theme.radius.md,
    borderWidth: 1,
    flexBasis: '47%',
    flexGrow: 1,
    padding: theme.spacing.md,
  },
  scoreValue: {
    fontSize: 18,
    fontWeight: '900',
    marginTop: 5,
  },
  sectionTop: {
    alignItems: 'flex-start',
    flexDirection: 'row',
    gap: theme.spacing.md,
    justifyContent: 'space-between',
  },
  setupList: {
    gap: theme.spacing.sm,
    marginTop: theme.spacing.lg,
  },
  setupFact: {
    borderRadius: theme.radius.md,
    borderWidth: 1,
    flex: 1,
    minWidth: 92,
    padding: theme.spacing.md,
  },
  setupFacts: {
    flexDirection: 'row',
    gap: theme.spacing.sm,
    marginTop: theme.spacing.lg,
  },
  setupName: {
    color: theme.colors.text,
    fontSize: theme.typography.body,
    fontWeight: '900',
  },
  setupRow: {
    alignItems: 'center',
    borderColor: theme.colors.border,
    borderRadius: theme.radius.md,
    borderWidth: 1,
    flexDirection: 'row',
    gap: theme.spacing.md,
    justifyContent: 'space-between',
    padding: theme.spacing.md,
  },
  matrixCell: {
    borderRadius: theme.radius.md,
    borderWidth: 0.5,
    flexBasis: '48%',
    gap: 4,
    paddingHorizontal: theme.spacing.md,
    paddingVertical: theme.spacing.sm,
  },
  matrixGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: theme.spacing.sm,
    marginTop: theme.spacing.md,
  },
  matrixLabel: {
    color: theme.colors.textDim,
    fontSize: theme.typography.label,
    fontWeight: '900',
    letterSpacing: 1,
    textTransform: 'uppercase',
  },
  matrixNextStep: {
    fontSize: 13,
    fontWeight: '700',
    lineHeight: 19,
    marginTop: theme.spacing.sm,
  },
  matrixValue: {
    fontSize: 18,
    fontWeight: '900',
  },
  setupScore: {
    fontSize: 18,
    fontWeight: '900',
  },
  sheetActions: {
    gap: theme.spacing.sm,
    marginTop: theme.spacing.md,
  },
  sheetStack: {
    gap: theme.spacing.md,
  },
  sheetTitle: {
    color: theme.colors.text,
    fontSize: theme.typography.title,
    fontWeight: '900',
    lineHeight: 28,
  },
  warningCopy: {
    color: theme.colors.warning,
    fontSize: theme.typography.small,
    fontWeight: '800',
    lineHeight: 20,
  },
  heroCard: {
    borderBottomWidth: 0.5,
    paddingVertical: theme.spacing.md,
    paddingHorizontal: theme.spacing.lg,
    marginTop: theme.spacing.md,
  },
  heroKicker: {
    color: theme.colors.accent,
    fontSize: 11,
    fontWeight: '900',
    letterSpacing: 2,
  },
  heroPill: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: theme.colors.dangerSoft,
    paddingHorizontal: 8,
    paddingVertical: 4,
    borderRadius: theme.radius.pill,
    gap: 4,
  },
  heroPillDot: {
    width: 6,
    height: 6,
    borderRadius: 3,
    backgroundColor: theme.colors.danger,
  },
  heroPillText: {
    color: theme.colors.danger,
    fontSize: 9,
    fontWeight: '900',
    letterSpacing: 1,
  },
  heroStatBlock: {
    flex: 1,
    borderRadius: theme.radius.lg,
    padding: theme.spacing.md,
  },
  heroStatLabel: {
    fontSize: 10,
    fontWeight: '900',
    letterSpacing: 1.5,
  },
  heroStatValue: {
    fontSize: 18,
    fontWeight: '900',
    marginTop: 4,
  },
  heroCta: {
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 8,
    paddingHorizontal: 16,
    borderRadius: theme.radius.pill,
    borderWidth: 0.5,
    borderColor: theme.colors.border,
    backgroundColor: 'transparent',
    marginTop: theme.spacing.md,
  },
  heroCtaText: {
    color: theme.colors.accent,
    fontSize: 12,
    fontWeight: '700',
    letterSpacing: 0.5,
    textTransform: 'uppercase',
  },
  matchCard: {
    borderRadius: theme.radius.xl,
    borderWidth: 0.5,
    padding: theme.spacing.md,
    marginTop: theme.spacing.md,
  },
  matchBadge: {
    backgroundColor: '#064E3B',
    borderRadius: theme.radius.md,
    paddingVertical: 6,
    paddingHorizontal: 10,
    alignItems: 'center',
  },
  matchBadgeScore: {
    color: '#34D399',
    fontSize: 18,
    fontWeight: '900',
  },
  matchBadgeLabel: {
    color: '#34D399',
    fontSize: 9,
    fontWeight: '900',
    letterSpacing: 1,
    marginTop: 2,
  },
  matchProgressTrack: {
    height: 6,
    backgroundColor: theme.colors.backgroundSoft,
    borderRadius: 3,
    marginTop: theme.spacing.lg,
    overflow: 'hidden',
  },
  matchProgressFill: {
    height: '100%',
    backgroundColor: '#10B981',
    borderRadius: 3,
  },
  setupFactsRow: {
    flexDirection: 'row',
    gap: theme.spacing.sm,
    marginTop: theme.spacing.lg,
  },
  factLabel: {
    fontSize: 9,
    fontWeight: '900',
    letterSpacing: 1.5,
  },
  factValue: {
    fontSize: 14,
    fontWeight: '900',
    marginTop: 4,
  },
  plainCard: {
    borderBottomWidth: 0.5,
    paddingVertical: theme.spacing.md,
    paddingHorizontal: theme.spacing.lg,
    marginTop: theme.spacing.md,
  },
  plainCardTitle: {
    fontSize: 18,
    fontWeight: '900',
    marginTop: 6,
    lineHeight: 22,
  },
  plainCardSubtitle: {
    fontSize: 15,
    fontWeight: '600',
    marginTop: 6,
  },
  setupScoreOrange: {
    color: theme.colors.warning,
    fontSize: 18,
    fontWeight: '900',
  },
});
