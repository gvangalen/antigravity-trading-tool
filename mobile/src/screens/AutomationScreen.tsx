import { useCallback, useEffect, useMemo, useState } from 'react';
import { Feather } from '@expo/vector-icons';
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';

import { InsightCard } from '../components/cards/InsightCard';
import { LoadingSkeletonCard } from '../components/layout/LoadingSkeletonCard';
import { ScreenContainer } from '../components/layout/ScreenContainer';
import { SwipeActionRow } from '../components/rows/SwipeActionRow';
import { SegmentedControl } from '../components/layout/SegmentedControl';
import { StatusChip } from '../components/layout/StatusChip';
import { BottomSheet } from '../components/sheets/BottomSheet';
import { ConfirmDestructiveSheetContent, RowActionSheetContent } from '../components/sheets/RowActionSheetContent';
import { TodayWithFinnCard, type TodayWithFinnQueueItem } from '../components/workspace/TodayWithFinnCard';
import { WorkflowStepsRail } from '../components/workspace/WorkflowStepsRail';
import { WorkspaceHeroSection } from '../components/workspace/WorkspaceHeroSection';
import { listRowStandards } from '../constants/listRows';
import { StatusTone, theme } from '../constants/theme';
import { typography } from '../constants/typography';
import { useIntelligenceContext } from '../contexts/ActiveIntelligenceContext';
import { useFinnOverlay } from '../contexts/FinnOverlayContext';
import { useApiResource } from '../hooks/useApiResource';
import { translate, translateFinnTag } from '../i18n';
import { localizedBackendText } from '../i18n';
import { preferenceColors, useAppPreferences } from '../preferences/AppPreferencesProvider';
import { trackAssistantEvent } from '../services/assistantAnalytics';
import { mapBotDecision } from '../services/dataMappers';
import { intelligenceApi, mobileApi, type MobileOverviewResponse } from '../services/tradamindApi';
import { triggerHaptic } from '../utils/haptics';

type UnknownRecord = Record<string, unknown>;
type AutomationFilter = 'all' | 'active' | 'paused';

type AutomationBot = {
  id: number;
  isActive: boolean;
  isLive: boolean;
  budgetTotal: number;
  exposure: number;
  mode: string;
  name: string;
  symbol: string;
  timeframe: string;
};

export function AutomationScreen() {
  const { context } = useIntelligenceContext();
  const { openFinn } = useFinnOverlay();
  const { appearance, language } = useAppPreferences();
  const colors = preferenceColors(appearance);
  const [filter, setFilter] = useState<AutomationFilter>('all');
  const [botActionItem, setBotActionItem] = useState<AutomationBot | null>(null);
  const [botRemoveItem, setBotRemoveItem] = useState<AutomationBot | null>(null);
  const [botDetailItem, setBotDetailItem] = useState<AutomationBot | null>(null);
  const activeAsset = context.asset;

  useEffect(() => {
    trackAssistantEvent({
      asset: activeAsset,
      event_name: 'screen_view',
      flow_type: 'automation',
      page: 'automation',
    });
  }, [activeAsset]);

  const overviewResource = useApiResource<MobileOverviewResponse | undefined>({
    fallbackData: undefined,
    fetcher: useCallback(() => mobileApi.overview(activeAsset), [activeAsset]),
  });
  const configsResource = useApiResource<UnknownRecord[]>({
    fallbackData: [],
    fetcher: useCallback(async () => asArray(await intelligenceApi.botConfigs()), []),
  });
  const portfoliosResource = useApiResource<UnknownRecord[]>({
    fallbackData: [],
    fetcher: useCallback(async () => asArray(await intelligenceApi.botPortfolios()), []),
  });
  const decisionResource = useApiResource<UnknownRecord | UnknownRecord[] | undefined>({
    fallbackData: undefined,
    fetcher: useCallback(() => intelligenceApi.botToday(activeAsset), [activeAsset]),
  });

  const overviewBots = useMemo(
    () => mapOverviewAutomationBots(overviewResource.data),
    [overviewResource.data],
  );
  const bots = useMemo(
    () =>
      sortAutomationBots(
        mergeAutomationBots(
          mapAutomationBots(configsResource.data, portfoliosResource.data),
          overviewBots,
        ),
        activeAsset,
      ),
    [activeAsset, configsResource.data, overviewBots, portfoliosResource.data],
  );
  const filteredBots = useMemo(() => filterAutomationBots(bots, filter), [bots, filter]);
  const activeBots = useMemo(() => bots.filter((bot) => bot.isActive), [bots]);
  const pausedBots = useMemo(() => bots.filter((bot) => !bot.isActive), [bots]);
  const liveBots = useMemo(() => bots.filter((bot) => bot.isLive), [bots]);
  const topBot =
    filteredBots.find((bot) => needsAutomationReview(bot) && bot.symbol === activeAsset) ??
    bots.find((bot) => needsAutomationReview(bot) && bot.symbol === activeAsset) ??
    filteredBots.find((bot) => needsAutomationReview(bot)) ??
    bots.find((bot) => needsAutomationReview(bot)) ??
    filteredBots.find((bot) => bot.symbol === activeAsset && bot.isActive) ??
    bots.find((bot) => bot.symbol === activeAsset && bot.isActive) ??
    filteredBots.find((bot) => bot.symbol === activeAsset) ??
    bots.find((bot) => bot.symbol === activeAsset) ??
    filteredBots[0] ??
    bots[0] ??
    null;
  const staleMessage =
    configsResource.error?.message ||
    portfoliosResource.error?.message ||
    decisionResource.error?.message ||
    overviewResource.error?.message;
  const hasRenderableAutomationCore =
    bots.length > 0 ||
    activeBots.length > 0 ||
    pausedBots.length > 0 ||
    liveBots.length > 0 ||
    Boolean(overviewResource.data?.active_bots?.length) ||
    Boolean(decisionResource.data);
  const visibleTopBot = topBot;
  const visibleBots = filteredBots.length > 0 ? sortAutomationBots(filteredBots, activeAsset) : [];
  const decision = useMemo(() => mapBotDecision(extractRecord(decisionResource.data)), [decisionResource.data]);
  const loading = (configsResource.loading || portfoliosResource.loading) && bots.length === 0;

  async function openBot(bot: AutomationBot) {
    await triggerHaptic('selection');
    setBotDetailItem(bot);
  }

  async function openBotActions(bot: AutomationBot) {
    await triggerHaptic('selection');
    setBotActionItem(bot);
  }

  async function editBot(bot: AutomationBot) {
    setBotActionItem(null);
    await triggerHaptic('selection');
    openFinn({
      prefill: `Help me edit bot ${bot.name} for ${bot.symbol}. Review execution mode, risk settings and budget, then suggest the smallest safe config change.`,
      source: 'automation-bot-edit',
      symbol: bot.symbol,
    });
  }

  function promptDeleteBot(bot: AutomationBot) {
    setBotActionItem(null);
    setBotRemoveItem(bot);
  }

  async function confirmDeleteBot() {
    if (!botRemoveItem) return;

    await intelligenceApi.deleteBotConfig(botRemoveItem.id);
    setBotRemoveItem(null);
    overviewResource.refresh();
    configsResource.refresh();
    portfoliosResource.refresh();
    decisionResource.refresh();
  }

  return (
    <ScreenContainer
      edgeToEdge={true}
      contentInsetBottom={320}
      refreshing={
        overviewResource.refreshing ||
        configsResource.refreshing ||
        portfoliosResource.refreshing ||
        decisionResource.refreshing
      }
      onRefresh={() => {
        overviewResource.refresh();
        configsResource.refresh();
        portfoliosResource.refresh();
        decisionResource.refresh();
      }}
    >
      {visibleTopBot ? (
      <AutomationTodayHero
          activeAsset={activeAsset}
          activeCount={activeBots.length}
          bot={visibleTopBot}
          briefing={overviewResource.data?.finn_briefing}
          decision={decision}
          liveCount={liveBots.length}
          onOpen={() =>
            openFinn({
              prefill: `Open the automation workspace for ${visibleTopBot.name} on ${visibleTopBot.symbol}. Summarize today's execution state, key blockers and the first review step.`,
              source: 'automation-today',
              symbol: visibleTopBot.symbol,
            })
          }
          pausedCount={pausedBots.length}
          reviewCount={Math.max(1, pausedBots.length)}
        />
      ) : null}
      <WorkflowStepsRail
        steps={[
          {
            body: translate(language, 'automation.stepPlanBody'),
            icon: 'layers',
            step: 1,
            title: translate(language, 'automation.stepPlanTitle'),
          },
          {
            body: translate(language, 'automation.stepExecutionBody'),
            icon: 'cpu',
            step: 2,
            title: translate(language, 'automation.stepExecutionTitle'),
          },
          {
            body: translate(language, 'automation.stepMonitoringBody'),
            icon: 'shield',
            step: 3,
            title: translate(language, 'automation.stepMonitoringTitle'),
          },
        ]}
      />

      {loading ? <LoadingSkeletonCard /> : null}

      {visibleTopBot ? (
        <>
          <AutomationBotsSection
            bots={visibleBots}
            colors={colors}
            filter={filter}
            liveCount={liveBots.length}
            onAskFinn={openBot}
            onChangeFilter={setFilter}
            onDeleteBot={promptDeleteBot}
            onEditBot={editBot}
            onOpenActions={openBotActions}
          />
        </>
      ) : null}

      {staleMessage && !hasRenderableAutomationCore ? (
        <InsightCard
          body={staleMessage}
          cta={translate(language, 'automation.syncRefresh')}
          label={translate(language, 'automation.syncLabel')}
          onPress={() => {
            configsResource.refresh();
            portfoliosResource.refresh();
            decisionResource.refresh();
            overviewResource.refresh();
          }}
          title={translate(language, 'automation.syncTitle')}
          tone="warning"
        />
      ) : null}

      <BottomSheet
        visible={Boolean(botDetailItem)}
        title={botDetailItem?.name ?? 'Bot details'}
        onClose={() => setBotDetailItem(null)}
      >
        {botDetailItem ? (
          <AutomationBotDetailSheet
            bot={botDetailItem}
            onAskFinn={() =>
              openFinn({
                prefill: `Open the automation context for ${botDetailItem.name} on ${botDetailItem.symbol}. Explain status, risk and next review step.`,
                source: 'automation-bot-detail',
                symbol: botDetailItem.symbol,
              })
            }
            onEdit={async () => {
              setBotDetailItem(null);
              await editBot(botDetailItem);
            }}
          />
        ) : null}
      </BottomSheet>

      <BottomSheet
        visible={Boolean(botActionItem)}
        title={translate(language, 'common.actions')}
        onClose={() => setBotActionItem(null)}
      >
        <RowActionSheetContent
          actions={
            botActionItem
              ? [
                  {
                    key: 'edit',
                    label: translate(language, 'common.edit'),
                    description: `${botActionItem.name} · ${botActionItem.symbol} · ${botActionItem.isLive ? 'Live' : 'Paper'}`,
                    icon: 'edit-3',
                    onPress: () => editBot(botActionItem),
                  },
                  {
                    key: 'delete',
                    label: translate(language, 'common.delete'),
                    description: botActionItem.isActive || botActionItem.isLive
                      ? 'Actieve of live bot: extra controle aanbevolen.'
                      : 'Verwijder deze botconfiguratie.',
                    icon: 'trash-2',
                    tone: 'danger',
                    onPress: () => promptDeleteBot(botActionItem),
                  },
                ]
              : []
          }
        />
      </BottomSheet>

      <BottomSheet
        visible={Boolean(botRemoveItem)}
        title="Bot verwijderen?"
        onClose={() => setBotRemoveItem(null)}
      >
        {botRemoveItem ? (
          <ConfirmDestructiveSheetContent
            body={
              botRemoveItem.isActive || botRemoveItem.isLive
                ? `${botRemoveItem.name} is ${botRemoveItem.isLive ? 'live' : 'actief'}. Verwijderen stopt deze configuratie en kan lopende monitoring onderbreken. Controleer eerst budget, exchange en open exposure.`
                : `Verwijder ${botRemoveItem.name} voor ${botRemoveItem.symbol}. Deze botconfiguratie wordt permanent verwijderd.`
            }
            confirmLabel={translate(language, 'common.delete')}
            onConfirm={confirmDeleteBot}
            title={botRemoveItem.isActive || botRemoveItem.isLive ? 'Actieve bot verwijderen?' : 'Bot verwijderen?'}
          />
        ) : null}
      </BottomSheet>
    </ScreenContainer>
  );
}

function AutomationBotDetailSheet({
  bot,
  onAskFinn,
  onEdit,
}: {
  bot: AutomationBot;
  onAskFinn: () => void;
  onEdit: () => void | Promise<void>;
}) {
  const { appearance, language } = useAppPreferences();
  const colors = preferenceColors(appearance);
  const state = deriveAutomationBotState(bot);

  return (
    <View style={{ gap: theme.spacing.md }}>
      <View
        style={{
          backgroundColor: colors.surfaceMuted,
          borderColor: colors.borderSubtle,
          borderRadius: theme.radius.card,
          borderWidth: 1,
          padding: theme.spacing.md,
        }}
      >
        <View style={{ alignItems: 'center', flexDirection: 'row', justifyContent: 'space-between', gap: theme.spacing.sm }}>
          <View style={{ flex: 1 }}>
            <Text style={[typography.eyebrow, { color: colors.textDim }]}>Bot detail</Text>
            <Text style={[typography.sectionTitle, { color: colors.text }]}>{bot.name}</Text>
            <Text style={[typography.body, { color: colors.textMuted }]}>
              {bot.symbol} · {bot.timeframe || '—'} · {translateFinnTag(language, bot.isLive ? 'Live' : 'Paper')}
            </Text>
          </View>
          <StatusChip compact label={bot.isActive ? translate(language, 'automation.active') : translate(language, 'automation.paused')} tone={bot.isActive ? 'success' : 'warning'} />
        </View>
      </View>

      <View style={{ gap: theme.spacing.sm }}>
        <View style={{ flexDirection: 'row', gap: theme.spacing.sm }}>
          <View style={{ flex: 1 }}>
            <AutomationDetailMetric label="Status" value={state.label} />
          </View>
          <View style={{ flex: 1 }}>
            <AutomationDetailMetric label="Actie" value={state.action} />
          </View>
        </View>
        <View style={{ flexDirection: 'row', gap: theme.spacing.sm }}>
          <View style={{ flex: 1 }}>
            <AutomationDetailMetric label="Mode" value={bot.mode || '—'} />
          </View>
          <View style={{ flex: 1 }}>
            <AutomationDetailMetric label="Kapitaal" value={bot.isLive ? 'Live' : 'Paper'} />
          </View>
        </View>
        <View style={{ flexDirection: 'row', gap: theme.spacing.sm }}>
          <View style={{ flex: 1 }}>
            <AutomationDetailMetric label="Budget" value={formatEUR(bot.budgetTotal)} />
          </View>
          <View style={{ flex: 1 }}>
            <AutomationDetailMetric label="Exposure" value={formatEUR(bot.exposure)} />
          </View>
        </View>
      </View>

      <View
        style={{
          borderColor: colors.borderSubtle,
          borderRadius: theme.radius.card,
          borderWidth: 1,
          padding: theme.spacing.md,
        }}
      >
        <Text style={[typography.sectionTitle, { color: colors.text }]}>Wat je nu ziet</Text>
        <Text style={[typography.body, { color: colors.textMuted, marginTop: theme.spacing.xs }]}>
          {bot.isActive
            ? `${bot.name} draait momenteel ${bot.isLive ? 'met live kapitaal' : 'in paper mode'} en heeft zichtbare exposure van ${formatEUR(bot.exposure)}.`
            : `${bot.name} staat nu niet actief. Controleer of budget, setupkwaliteit en execution mode nog kloppen voordat je hem opnieuw activeert.`}
        </Text>
        <Text style={[typography.body, { color: colors.textMuted, marginTop: theme.spacing.xs }]}>
          {bot.budgetTotal > 0
            ? `Het ingestelde budget is ${formatEUR(bot.budgetTotal)}.`
            : 'Er staat nog geen bruikbaar budget op deze botconfiguratie.'}
        </Text>
      </View>

      <View style={{ gap: theme.spacing.sm }}>
        <Pressable
          onPress={async () => {
            await triggerHaptic('selection');
            await onEdit();
          }}
          style={{
            alignItems: 'center',
            backgroundColor: colors.surfaceMuted,
            borderColor: colors.borderSubtle,
            borderRadius: theme.radius.button,
            borderWidth: 1,
            paddingHorizontal: theme.spacing.md,
            paddingVertical: theme.spacing.sm,
          }}
        >
          <Text style={[typography.actionStrong, { color: colors.text }]}>Bot bewerken</Text>
        </Pressable>
        <Pressable
          onPress={async () => {
            await triggerHaptic('selection');
            onAskFinn();
          }}
          style={{
            alignItems: 'center',
            backgroundColor: colors.accent,
            borderRadius: theme.radius.button,
            paddingHorizontal: theme.spacing.md,
            paddingVertical: theme.spacing.sm,
          }}
        >
          <Text style={{ color: theme.colors.white, fontSize: 13, fontWeight: '800', letterSpacing: 0.3 }}>
            Vraag FINN om extra botuitleg
          </Text>
        </Pressable>
      </View>
    </View>
  );
}

function AutomationDetailMetric({
  label,
  value,
}: {
  label: string;
  value: string;
}) {
  const { appearance } = useAppPreferences();
  const colors = preferenceColors(appearance);

  return (
    <View
      style={{
        backgroundColor: colors.surfaceMuted,
        borderColor: colors.borderSubtle,
        borderRadius: theme.radius.card,
        borderWidth: 1,
        gap: 4,
        padding: theme.spacing.sm,
      }}
    >
      <Text style={[typography.metricLabel, { color: colors.textDim }]}>{label}</Text>
      <Text style={[typography.bodyStrong, { color: colors.text }]}>{value}</Text>
    </View>
  );
}

function AutomationBotsSection({
  bots,
  colors,
  filter,
  liveCount,
  onAskFinn,
  onChangeFilter,
  onDeleteBot,
  onEditBot,
  onOpenActions,
}: {
  bots: AutomationBot[];
  colors: ReturnType<typeof preferenceColors>;
  filter: AutomationFilter;
  liveCount: number;
  onAskFinn: (bot: AutomationBot) => void;
  onChangeFilter: (value: AutomationFilter) => void;
  onDeleteBot: (bot: AutomationBot) => void;
  onEditBot: (bot: AutomationBot) => void | Promise<void>;
  onOpenActions: (bot: AutomationBot) => void | Promise<void>;
}) {
  const { language } = useAppPreferences();
  const pausedCount = bots.filter((bot) => deriveAutomationBotState(bot).kind === 'paused').length;
  const reviewCount = Math.max(1, bots.filter((bot) => deriveAutomationBotState(bot).action === 'Review').length);

  return (
    <View style={styles.automationSection}>
      <View style={styles.automationBotsHeader}>
        <Text style={[styles.automationBotsTitle, { color: colors.text }]}>
          {translate(language, 'automation.sectionBotsTitle')}
        </Text>
        <Pressable accessibilityRole="button">
          <Text style={styles.automationNewBotLink}>{translate(language, 'automation.newBot')}</Text>
        </Pressable>
      </View>

      <SegmentedControl
        compact
        items={[
          { key: 'all', label: translate(language, 'automation.filter.all') },
          { key: 'active', label: translate(language, 'automation.filter.active') },
          { key: 'paused', label: translate(language, 'automation.filter.paused') },
        ]}
        selected={filter}
        onChange={(value) => onChangeFilter(value as AutomationFilter)}
      />

      <View style={styles.automationBotList}>
        {bots.map((bot) => (
          <SwipeActionRow
            key={`${bot.id}-${bot.name}`}
            actions={[
              {
                key: 'edit',
                label: translate(language, 'common.edit'),
                icon: 'edit-3',
                onPress: () => onEditBot(bot),
              },
              {
                key: 'delete',
                label: translate(language, 'common.delete'),
                icon: 'trash-2',
                tone: 'danger',
                onPress: () => onDeleteBot(bot),
              },
            ]}
          >
            <Pressable
              onPress={() => onAskFinn(bot)}
              style={({ pressed }) => [
                styles.automationBotRow,
                { borderBottomColor: colors.borderSubtle },
                pressed && styles.pressed,
              ]}
            >
              <View style={styles.automationBotLeft}>
                <View style={[styles.automationBotIcon, { backgroundColor: colors.surfaceMuted }]}>
                  <Feather color={colors.accent} name="cpu" size={listRowStandards.iconGlyphSize} />
                </View>
                <View style={styles.automationBotCopy}>
                  <Text numberOfLines={2} style={[styles.automationBotTitle, { color: colors.text }]}>
                    {bot.name}
                  </Text>
                  {([bot.symbol, bot.timeframe, translateFinnTag(language, bot.isLive ? 'Live' : 'Paper')].filter(Boolean).join(' · ')) ? (
                    <Text style={[styles.automationBotMeta, { color: colors.textMuted }]}>
                      {[bot.symbol, bot.timeframe, translateFinnTag(language, bot.isLive ? 'Live' : 'Paper')].filter(Boolean).join(' · ')}
                    </Text>
                  ) : null}
                </View>
              </View>
              <View style={styles.automationBotRight}>
                {(() => {
                  const state = deriveAutomationBotState(bot);
                  return (
                    <>
                      <Text style={[styles.automationBotStatus, { color: state.color(colors) }]}>
                        {state.label}
                      </Text>
                      <Text style={[styles.automationBotAction, { color: colors.accent }]}>
                        {state.action}
                      </Text>
                    </>
                  );
                })()}
                <Pressable
                  hitSlop={10}
                  onPress={(event) => {
                    event.stopPropagation();
                    onOpenActions(bot);
                  }}
                  style={[styles.automationBotOverflowButton, { borderColor: colors.borderSubtle, backgroundColor: colors.surfaceMuted }]}
                >
                  <Feather color={colors.textDim} name="more-horizontal" size={15} />
                </Pressable>
              </View>
            </Pressable>
          </SwipeActionRow>
        ))}
      </View>
    </View>
  );
}

function AutomationTodayHero({
  activeAsset,
  activeCount,
  bot,
  briefing,
  decision,
  liveCount,
  pausedCount,
  reviewCount,
  onOpen,
}: {
  activeAsset: string;
  activeCount: number;
  bot: AutomationBot;
  briefing?: MobileOverviewResponse['finn_briefing'];
  decision: ReturnType<typeof mapBotDecision>;
  liveCount: number;
  pausedCount: number;
  reviewCount: number;
  onOpen: () => void;
}) {
  const { language } = useAppPreferences();
  const headline = localizedBackendText(
    language,
    briefing?.summary?.trim(),
    translate(language, 'finn.noBriefingReady'),
  );
  const support =
    bot.budgetTotal <= 0
      ? translate(language, 'automation.noBudgetSupport')
      : translate(language, 'automation.pausedLiveSupport', { liveCount, pausedCount });

  const metaItems = [
    translateFinnTag(language, bot.isActive ? 'Active bot' : 'Paused bot'),
    translate(language, 'common.confidence', { count: decision.confidence }),
    translateFinnTag(language, bot.isLive ? 'Live' : 'Paper'),
  ];

  const queueItems: TodayWithFinnQueueItem[] = [
    {
      body: translate(language, 'queue.body.botsWaitingReview'),
      key: 'tasks',
      label: translate(language, 'queue.label.tasks'),
      value: reviewCount,
      detail: translate(language, 'queue.body.botsPausedOrBlocked'),
    },
    {
      body: translate(language, 'queue.body.botsCurrentlyEnabled'),
      key: 'bots',
      label: translate(language, 'queue.label.bots'),
      value: activeCount,
    },
    {
      body: translate(language, 'queue.body.botsWaitingReview'),
      key: 'reviews',
      label: translate(language, 'queue.label.reviews'),
      value: reviewCount,
    },
    {
      body: translate(language, 'queue.body.botsUsingLiveCapital'),
      key: 'live',
      label: translate(language, 'queue.label.live'),
      value: liveCount,
    },
    {
      body: translate(language, 'queue.body.botsPausedOrBlocked'),
      key: 'paused',
      label: translate(language, 'queue.label.paused'),
      value: pausedCount,
    },
  ];

  return (
    <WorkspaceHeroSection>
      <TodayWithFinnCard
        headline={headline}
        metaItems={metaItems}
        queueItems={queueItems}
        queueStatusLabel={translate(language, 'common.itemsOpen', { count: reviewCount })}
        support={support}
      />
    </WorkspaceHeroSection>
  );
}

function PrimaryAutomationBotCard({
  bot,
  checkedAt,
  colors,
  decision,
  onAskFinn,
  onReviewTrade,
  onViewDiagnostics,
}: {
  bot: AutomationBot;
  checkedAt?: string | null;
  colors: ReturnType<typeof preferenceColors>;
  decision: ReturnType<typeof mapBotDecision>;
  onAskFinn: () => void;
  onReviewTrade: () => void;
  onViewDiagnostics: () => void;
}) {
  const { language } = useAppPreferences();
  const missingBudget = bot.budgetTotal <= 0;
  const statusReaction = missingBudget ? translate(language, 'automation.waiting') : decision.guardrail;
  const whyText = missingBudget
    ? translate(language, 'automation.noBudgetWhy')
    : decision.reason;
  const metricCards = [
    {
      key: 'status',
      label: translate(language, 'automation.statusReaction'),
      tone: missingBudget ? ('warning' as StatusTone) : decision.tone,
      value: statusReaction,
    },
    {
      key: 'action',
      label: translate(language, 'automation.marketAction'),
      tone: decision.tone,
      value: decision.action.toUpperCase(),
    },
    { key: 'why', label: translate(language, 'automation.why'), tone: 'neutral' as StatusTone, value: truncate(whyText, 72) },
    {
      key: 'checked',
      label: translate(language, 'automation.lastChecked'),
      tone: 'neutral' as StatusTone,
      value: formatCheckedAt(checkedAt),
    },
  ];

  return (
    <View style={[styles.primaryBotPanel, { backgroundColor: colors.surface, borderColor: colors.borderSubtle }]}>
      <View style={styles.primaryBotHeader}>
        <View style={styles.primaryBotIdentity}>
          <View style={[styles.primaryBotIcon, { backgroundColor: colors.surfaceMuted }]}>
            <Feather color={colors.accent} name="cpu" size={20} />
          </View>
          <View style={styles.primaryBotTitleWrap}>
            <Text style={[styles.sectionEyebrow, { color: colors.textDim }]}>System control</Text>
            <Text style={[styles.primaryBotTitle, { color: colors.text }]}>{bot.name}</Text>
            <Text style={[styles.primaryBotMeta, { color: colors.textMuted }]}>
              {bot.symbol} · {bot.timeframe} · {translateFinnTag(language, bot.isLive ? 'Live' : 'Paper')}
            </Text>
          </View>
        </View>
        <StatusChip
          compact
          label={translate(language, bot.isActive ? 'automation.active' : 'automation.paused')}
          tone={bot.isActive ? 'success' : 'warning'}
        />
      </View>

      <View style={styles.primaryBotBadgeRow}>
        <StatusChip compact label={bot.mode} tone="neutral" />
        <StatusChip
          compact
          label={translate(language, bot.isLive ? 'automation.liveCapital' : 'automation.paperTracking')}
          tone={bot.isLive ? 'danger' : 'accent'}
        />
      </View>

      {missingBudget ? (
        <View style={styles.warningPanel}>
          <Text style={styles.warningEyebrow}>{translate(language, 'automation.directlyVisible')}</Text>
          <Text style={styles.warningTitle}>{translate(language, 'automation.budgetRequired')}</Text>
          <Text style={styles.warningBody}>
            {whyText}
          </Text>
          <Text style={styles.warningNextStep}>{translate(language, 'automation.nextStepAddBudget')}</Text>
        </View>
      ) : null}

      <View style={styles.metricGrid}>
        {metricCards.map((item) => (
          <Pressable
            key={item.key}
            onPress={item.key === 'why' ? onAskFinn : undefined}
            style={[
              styles.metricCard,
              { backgroundColor: colors.surfaceMuted, borderColor: colors.borderSubtle },
            ]}
          >
            <Text style={[styles.metricLabel, { color: colors.textDim }]}>{item.label}</Text>
            <Text style={[styles.metricValue, { color: toneColor(item.tone, colors) }]}>{item.value}</Text>
          </Pressable>
        ))}
      </View>

      <Pressable
        onPress={async () => {
          await triggerHaptic('selection');
          onViewDiagnostics();
        }}
        style={[styles.diagnosticsLink, { borderColor: colors.borderSubtle }]}
      >
        <Feather color={colors.textDim} name="chevron-down" size={16} />
        <Text style={[styles.diagnosticsLinkText, { color: colors.textDim }]}>
          {translate(language, 'automation.viewFullDiagnostics')}
        </Text>
      </Pressable>

      <View style={styles.primaryBotActions}>
        <Pressable
          onPress={async () => {
            await triggerHaptic('selection');
            onReviewTrade();
          }}
          style={[styles.secondaryAction, { backgroundColor: colors.surfaceMuted, borderColor: colors.borderSubtle }]}
        >
          <Text style={[styles.secondaryActionText, { color: colors.text }]}>{translate(language, 'automation.trade')}</Text>
        </Pressable>
        <Pressable
          onPress={async () => {
            await triggerHaptic('selection');
            onAskFinn();
          }}
          style={styles.primaryAction}
        >
          <Text style={styles.primaryActionText}>{translate(language, 'automation.askFinn')}</Text>
        </Pressable>
      </View>
    </View>
  );
}

function AutomationBotList({
  bots,
  colors,
  filter,
  onAskFinn,
  onChangeFilter,
}: {
  bots: AutomationBot[];
  colors: ReturnType<typeof preferenceColors>;
  filter: AutomationFilter;
  onAskFinn: (bot: AutomationBot) => void;
  onChangeFilter: (value: AutomationFilter) => void;
}) {
  const { language } = useAppPreferences();
  const automationFilters: Array<{ key: AutomationFilter; label: string }> = [
    { key: 'all', label: translate(language, 'automation.filter.all') },
    { key: 'active', label: translate(language, 'automation.filter.active') },
    { key: 'paused', label: translate(language, 'automation.filter.paused') },
  ];
  return (
    <View style={styles.listSection}>
      <View style={styles.listSectionHeader}>
        <View>
          <Text style={[styles.sectionEyebrow, { color: colors.textDim }]}>My bots</Text>
          <Text style={[styles.listSubtitle, { color: colors.textMuted }]}>
            Overview and management of your active trading strategies.
          </Text>
        </View>
      </View>

      <SegmentedControl
        compact
        items={automationFilters.map((item) => ({ key: item.key, label: item.label }))}
        selected={filter}
        onChange={(value: AutomationFilter) => onChangeFilter(value)}
      />

      <View style={styles.botList}>
        {bots.map((bot) => (
          <Pressable
            key={`${bot.id}-${bot.name}`}
            onPress={async () => {
              await triggerHaptic('selection');
              onAskFinn(bot);
            }}
            style={[styles.botRow, { borderColor: colors.borderSubtle }]}
          >
            <View style={styles.botRowLeft}>
              <View style={[styles.botRowIcon, { backgroundColor: colors.surfaceMuted }]}>
                <Feather color={colors.accent} name="cpu" size={16} />
              </View>
              <View style={styles.botRowCopy}>
                <Text numberOfLines={2} style={[styles.botRowTitle, { color: colors.text }]}>
                  {bot.name}
                </Text>
                <Text style={[styles.botRowMeta, { color: colors.textMuted }]}>
                  {bot.symbol} · {bot.timeframe} · {translateFinnTag(language, bot.isLive ? 'Live' : 'Paper').toUpperCase()}
                </Text>
              </View>
            </View>

            <View style={styles.botRowRight}>
              <Text
                style={[
                  styles.botRowStatus,
                  { color: bot.isActive ? theme.colors.success : colors.textDim },
                ]}
              >
                {translate(language, bot.isActive ? 'automation.active' : 'automation.paused')}
              </Text>
              <Text style={[styles.botRowAction, { color: colors.accent }]}>
                {translate(language, bot.isActive ? 'automation.hold' : 'automation.review')}
              </Text>
              <Feather color={colors.textDim} name="chevron-right" size={16} />
            </View>
          </Pressable>
        ))}
      </View>
    </View>
  );
}

function asArray(value: unknown): UnknownRecord[] {
  return Array.isArray(value) ? value.filter(isRecord) : isRecord(value) ? [value] : [];
}

function isRecord(value: unknown): value is UnknownRecord {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value);
}

function extractRecord(source?: unknown) {
  if (Array.isArray(source)) return source.find(isRecord);
  return isRecord(source) ? source : undefined;
}

function mapAutomationBots(configs: UnknownRecord[], portfolios: UnknownRecord[]): AutomationBot[] {
  return configs.map((config, index) => {
    const id = readNumber(config, ['id', 'bot_id'], index + 1);
    const portfolio = portfolios.find((item) => readNumber(item, ['bot_id', 'id'], -1) === id) || {};
    const budget = isRecord(config.budget) ? config.budget : isRecord(portfolio.budget) ? portfolio.budget : {};
    const stats = isRecord(portfolio.stats) ? portfolio.stats : {};
    const strategy = isRecord(config.strategy) ? config.strategy : {};
    const setup = isRecord(strategy.setup) ? strategy.setup : {};

    return {
      budgetTotal: readNumber(budget, ['total_eur', 'budget_total_eur'], readNumber(config, ['budget_total_eur', 'budget_total'], 0)),
      exposure: readNumber(
        stats,
        ['position_value_eur', 'value_eur', 'invested_eur'],
        readNumber(portfolio, ['position_value_eur', 'value_eur', 'invested_eur'], 0),
      ),
      id,
      isActive: readBool(config, ['is_active', 'active'], false),
      isLive: readBool(config, ['is_live', 'live'], false),
      mode: readString(config, ['mode', 'execution_mode'], ''),
      name: readString(config, ['name', 'bot_name'], 'Bot'),
      symbol: readString(config, ['symbol', 'asset'], ''),
      timeframe: readString(setup, ['timeframe'], readString(config, ['timeframe', 'frequency'], '')).toUpperCase(),
    };
  });
}

function mapOverviewAutomationBots(overview?: MobileOverviewResponse): AutomationBot[] {
  if (!overview) return [];

  return overview.active_bots.map((bot) => ({
    budgetTotal: 0,
    exposure: bot.position_value_eur ?? bot.invested_eur ?? 0,
    id: bot.bot_id,
    isActive: bot.is_active,
    isLive: bot.is_live,
    mode: '',
    name: bot.name,
    symbol: bot.symbol,
    timeframe: '',
  }));
}

function mergeAutomationBots(primary: AutomationBot[], fallback: AutomationBot[]) {
  if (primary.length === 0) return [];

  const fallbackById = new Map<number, AutomationBot>();
  fallback.forEach((bot) => fallbackById.set(bot.id, bot));
  const merged = primary.map((bot) => {
    const overviewBot = fallbackById.get(bot.id);
    if (!overviewBot) return bot;

    return {
      ...overviewBot,
      ...bot,
      exposure: bot.exposure || overviewBot.exposure,
      isActive: bot.isActive || overviewBot.isActive,
      isLive: bot.isLive || overviewBot.isLive,
      name: bot.name || overviewBot.name,
      symbol: bot.symbol || overviewBot.symbol,
    };
  });

  const seen = new Set<number>();
  return merged.filter((bot) => {
    if (seen.has(bot.id)) return false;
    seen.add(bot.id);
    return true;
  });
}

function filterAutomationBots(bots: AutomationBot[], filter: AutomationFilter) {
  if (filter === 'active') return bots.filter((bot) => bot.isActive);
  if (filter === 'paused') return bots.filter((bot) => !bot.isActive);
  return bots;
}

function needsAutomationReview(bot: AutomationBot) {
  return !bot.isActive && bot.exposure <= 0;
}

function sortAutomationBots(bots: AutomationBot[], activeAsset: string) {
  return [...bots].sort((left, right) => {
    const leftRank = automationBotRank(left, activeAsset);
    const rightRank = automationBotRank(right, activeAsset);
    if (leftRank !== rightRank) return leftRank - rightRank;
    return left.name.localeCompare(right.name);
  });
}

function automationBotRank(bot: AutomationBot, activeAsset: string) {
  const assetBonus = bot.symbol === activeAsset ? -0.5 : 0;
  const state = deriveAutomationBotState(bot).kind;
  if (state === 'paused') return 0 + assetBonus;
  if (state === 'active') return 1 + assetBonus;
  return 2 + assetBonus;
}

function deriveAutomationBotState(bot: AutomationBot) {
  if (bot.isActive) {
    return {
      action: 'Vasthouden',
      color: (colors: ReturnType<typeof preferenceColors>) => colors.success,
      kind: 'active' as const,
      label: 'Actief',
    };
  }
  if (bot.exposure > 0 || bot.budgetTotal > 0) {
    return {
      action: 'Bekijken',
      color: (colors: ReturnType<typeof preferenceColors>) => colors.textDim,
      kind: 'off' as const,
      label: 'Uit',
    };
  }
  return {
    action: 'Review',
    color: (colors: ReturnType<typeof preferenceColors>) => colors.danger,
    kind: 'paused' as const,
    label: 'Gepauzeerd',
  };
}

function readString(source: UnknownRecord, keys: string[], fallback = '') {
  for (const key of keys) {
    const value = source[key];
    if (typeof value === 'string' && value.trim()) return value.trim();
  }
  return fallback;
}

function readNumber(source: UnknownRecord, keys: string[], fallback = 0) {
  for (const key of keys) {
    const value = source[key];
    if (typeof value === 'number' && Number.isFinite(value)) return value;
    if (typeof value === 'string' && value.trim()) {
      const parsed = Number(value);
      if (Number.isFinite(parsed)) return parsed;
    }
  }
  return fallback;
}

function readBool(source: UnknownRecord, keys: string[], fallback = false) {
  for (const key of keys) {
    const value = source[key];
    if (typeof value === 'boolean') return value;
    if (typeof value === 'number') return value === 1;
    if (typeof value === 'string') return value === 'true' || value === '1';
  }
  return fallback;
}

function truncate(value: string, maxLength: number) {
  if (value.length <= maxLength) return value;
  return `${value.slice(0, maxLength - 1).trimEnd()}…`;
}

function formatCheckedAt(value?: string | null) {
  if (!value) return 'Waiting for sync';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString([], {
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    month: 'short',
  });
}

function formatAutomationCheckedAt(value?: string | null) {
  if (!value) return 'Wacht op sync';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  const diffMs = Date.now() - date.getTime();
  const diffMin = Math.max(1, Math.round(diffMs / 60000));
  if (diffMin < 60) return `${diffMin} min geleden`;
  return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

function formatEUR(value: number) {
  return new Intl.NumberFormat('nl-NL', {
    currency: 'EUR',
    maximumFractionDigits: Math.abs(value) >= 100 ? 0 : 2,
    style: 'currency',
  }).format(Number.isFinite(value) ? value : 0);
}

function toneColor(tone: StatusTone, colors: ReturnType<typeof preferenceColors>) {
  if (tone === 'success') return colors.success;
  if (tone === 'warning') return colors.warning;
  if (tone === 'danger') return colors.danger;
  if (tone === 'accent') return colors.accent;
  return colors.text;
}

const styles = StyleSheet.create({
  automationBotAction: {
    ...typography.listRowAction,
    letterSpacing: 0.2,
  },
  automationBotCopy: {
    flex: 1,
    minWidth: 0,
  },
  automationBotIcon: {
    alignItems: 'center',
    borderColor: listRowStandards.iconBorderColor,
    borderRadius: listRowStandards.iconRadius,
    borderWidth: 1,
    height: listRowStandards.iconSize,
    justifyContent: 'center',
    width: listRowStandards.iconSize,
  },
  automationBotLeft: {
    alignItems: 'center',
    flex: 1,
    flexDirection: 'row',
    gap: listRowStandards.rowGap,
    minWidth: 0,
  },
  automationBotList: {
    marginTop: theme.spacing.md,
  },
  automationBotMeta: {
    ...typography.listRowMeta,
    marginTop: 1,
  },
  automationBotRight: {
    alignItems: 'center',
    flexDirection: 'row',
    gap: 8,
    marginLeft: 10,
  },
  automationBotOverflowButton: {
    alignItems: 'center',
    borderRadius: 14,
    borderWidth: 1,
    height: 30,
    justifyContent: 'center',
    width: 30,
  },
  automationBotRow: {
    alignItems: 'center',
    borderBottomWidth: 1,
    flexDirection: 'row',
    justifyContent: 'space-between',
    paddingVertical: listRowStandards.rowPaddingY,
  },
  pressed: {
    opacity: 0.72,
  },
  automationBotStatus: {
    ...typography.listRowStatus,
    minWidth: listRowStandards.statusMinWidth,
    textAlign: 'right',
  },
  automationBotTitle: {
    ...typography.listRowTitle,
  },
  automationBotsHeader: {
    alignItems: 'center',
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginBottom: theme.spacing.md,
  },
  automationBotsTitle: {
    ...typography.sectionTitle,
  },
  automationNewBotLink: {
    color: theme.colors.accent,
    fontSize: 15,
    fontWeight: '600',
    lineHeight: 20,
  },
  automationSafetyLabel: {
    fontSize: 15,
    fontWeight: '500',
    lineHeight: 20,
  },
  automationSafetyLeft: {
    alignItems: 'center',
    flexDirection: 'row',
    gap: 12,
  },
  automationSafetyList: {
    marginTop: theme.spacing.md,
  },
  automationSafetyNote: {
    alignItems: 'center',
    flexDirection: 'row',
    gap: 10,
    marginTop: theme.spacing.md,
  },
  automationSafetyNoteText: {
    flex: 1,
    ...typography.body,
  },
  automationSafetyRight: {
    alignItems: 'center',
    flexDirection: 'row',
    gap: 8,
    marginLeft: theme.spacing.md,
  },
  automationSafetyRow: {
    alignItems: 'center',
    borderBottomWidth: 1,
    flexDirection: 'row',
    justifyContent: 'space-between',
    paddingVertical: 14,
  },
  automationSafetyRowLast: {
    borderBottomWidth: 0,
    paddingBottom: 0,
  },
  automationSafetyTitle: {
    ...typography.metricValue,
  },
  automationSafetyValue: {
    ...typography.bodyStrong,
    lineHeight: 20,
  },
  automationSection: {
    paddingHorizontal: theme.spacing.lg,
    paddingVertical: theme.spacing.md,
  },
  automationSummaryPill: {
    alignItems: 'center',
    borderRadius: 12,
    borderWidth: 1,
    marginTop: theme.spacing.md,
    paddingHorizontal: theme.spacing.md,
    paddingVertical: 12,
  },
  automationSummaryPillText: {
    ...typography.body,
  },
  botList: {
    gap: theme.spacing.sm,
    marginTop: theme.spacing.md,
    paddingBottom: 120,
  },
  botRow: {
    alignItems: 'center',
    borderBottomWidth: 1,
    flexDirection: 'row',
    gap: 8,
    justifyContent: 'space-between',
    paddingVertical: listRowStandards.rowPaddingY,
  },
  botRowAction: {
    ...typography.listRowAction,
  },
  botRowCopy: {
    flex: 1,
    gap: 2,
    minWidth: 0,
  },
  botRowIcon: {
    alignItems: 'center',
    borderColor: listRowStandards.iconBorderColor,
    borderRadius: listRowStandards.iconRadius,
    borderWidth: 1,
    height: listRowStandards.iconSize,
    justifyContent: 'center',
    width: listRowStandards.iconSize,
  },
  botRowLeft: {
    alignItems: 'center',
    flex: 1,
    flexDirection: 'row',
    gap: 10,
    minWidth: 0,
  },
  botRowMeta: {
    ...typography.listRowMeta,
  },
  botRowRight: {
    alignItems: 'center',
    flexDirection: 'row',
    gap: 6,
    marginLeft: 10,
  },
  botRowStatus: {
    ...typography.listRowStatus,
  },
  botRowTitle: {
    ...typography.listRowTitle,
  },
  diagnosticsLink: {
    alignItems: 'center',
    borderBottomWidth: 1,
    borderTopWidth: 1,
    flexDirection: 'row',
    gap: 8,
    justifyContent: 'center',
    marginTop: theme.spacing.md,
    paddingVertical: theme.spacing.md,
  },
  diagnosticsLinkText: {
    ...typography.chipLabel,
    letterSpacing: 1.1,
  },
  introBody: {
    ...typography.action,
    lineHeight: 22,
  },
  introCopy: {
    flex: 1,
  },
  introHeader: {
    alignItems: 'flex-start',
    flexDirection: 'row',
    gap: theme.spacing.sm,
    justifyContent: 'space-between',
  },
  introPanel: {
    borderRadius: 20,
    borderWidth: 1,
    marginHorizontal: theme.spacing.lg,
    marginTop: theme.spacing.md,
    padding: theme.spacing.md,
  },
  listSection: {
    marginHorizontal: theme.spacing.lg,
    marginTop: theme.spacing.lg,
  },
  listSectionHeader: {
    alignItems: 'flex-start',
    flexDirection: 'row',
    justifyContent: 'space-between',
  },
  listSubtitle: {
    ...typography.subcopy,
    marginTop: 4,
  },
  metricCard: {
    borderRadius: 22,
    borderWidth: 1,
    marginBottom: 12,
    minHeight: 132,
    paddingHorizontal: theme.spacing.md,
    paddingVertical: theme.spacing.md,
    width: '48.75%',
  },
  metricGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    justifyContent: 'space-between',
    marginTop: theme.spacing.lg,
  },
  metricLabel: {
    ...typography.metricLabelStrong,
    letterSpacing: 1.3,
  },
  metricValue: {
    ...typography.metricValue,
    marginTop: theme.spacing.sm,
  },
  primaryAction: {
    alignItems: 'center',
    backgroundColor: theme.colors.accent,
    borderRadius: theme.radius.pill,
    flex: 1,
    justifyContent: 'center',
    minHeight: 46,
    paddingHorizontal: theme.spacing.md,
  },
  primaryActionText: {
    color: '#FFFFFF',
    fontSize: 12,
    fontWeight: '900',
    letterSpacing: 1.1,
    textTransform: 'uppercase',
  },
  primaryBotActions: {
    flexDirection: 'row',
    gap: theme.spacing.sm,
    marginTop: theme.spacing.md,
  },
  primaryBotBadgeRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 6,
    marginTop: theme.spacing.sm,
  },
  primaryBotHeader: {
    alignItems: 'flex-start',
    flexDirection: 'row',
    gap: theme.spacing.md,
    justifyContent: 'space-between',
  },
  primaryBotIcon: {
    alignItems: 'center',
    borderRadius: 18,
    height: 40,
    justifyContent: 'center',
    width: 40,
  },
  primaryBotIdentity: {
    flex: 1,
    flexDirection: 'row',
    gap: theme.spacing.sm,
  },
  primaryBotMeta: {
    ...typography.subcopy,
    fontWeight: '700',
    lineHeight: 16,
    marginTop: 4,
  },
  primaryBotPanel: {
    borderRadius: 20,
    borderWidth: 1,
    marginHorizontal: theme.spacing.lg,
    marginTop: theme.spacing.lg,
    padding: theme.spacing.md,
  },
  primaryBotTitle: {
    ...typography.sectionTitle,
    fontWeight: '900',
    lineHeight: 22,
    marginTop: 2,
  },
  primaryBotTitleWrap: {
    flex: 1,
  },
  secondaryAction: {
    alignItems: 'center',
    borderRadius: theme.radius.pill,
    borderWidth: 1,
    flex: 1,
    justifyContent: 'center',
    minHeight: 46,
    paddingHorizontal: theme.spacing.md,
  },
  secondaryActionText: {
    fontSize: 12,
    fontWeight: '800',
    letterSpacing: 1,
    textTransform: 'uppercase',
  },
  sectionBody: {
    ...typography.bodyStrong,
    marginTop: theme.spacing.xs,
  },
  sectionEyebrow: {
    ...typography.eyebrow,
  },
  sectionTitle: {
    ...typography.cardTitle,
    marginTop: 4,
  },
  stepBody: {
    ...typography.chipLabelCompact,
    fontWeight: '600',
    lineHeight: 13,
    textTransform: 'none',
    marginTop: 1,
  },
  stepCard: {
    alignItems: 'center',
    borderRadius: 14,
    borderWidth: 1,
    flexDirection: 'row',
    marginRight: 6,
    minHeight: 48,
    paddingHorizontal: theme.spacing.sm,
    paddingVertical: 8,
    width: 138,
  },
  stepCopy: {
    flex: 1,
  },
  stepIconWrap: {
    alignItems: 'center',
    borderRadius: 12,
    height: 32,
    justifyContent: 'center',
    marginRight: theme.spacing.sm,
    width: 32,
  },
  stepRail: {
    marginTop: theme.spacing.sm,
  },
  stepRailContent: {
    paddingRight: theme.spacing.md,
  },
  stepTitle: {
    ...typography.subcopy,
    fontWeight: '800',
    lineHeight: 14,
  },
  warningBody: {
    color: '#8A4B00',
    ...typography.bodyLarge,
    fontWeight: '700',
    lineHeight: 20,
    marginTop: theme.spacing.sm,
  },
  warningEyebrow: {
    color: '#C06A00',
    ...typography.metricLabelStrong,
    letterSpacing: 2,
  },
  warningNextStep: {
    color: '#B45309',
    ...typography.subcopy,
    fontWeight: '700',
    lineHeight: 18,
    marginTop: theme.spacing.xs,
  },
  warningPanel: {
    backgroundColor: '#FFF7E6',
    borderColor: '#F5D592',
    borderRadius: 24,
    borderWidth: 1,
    marginTop: theme.spacing.lg,
    padding: theme.spacing.md,
  },
  warningTitle: {
    color: '#9A4A00',
    ...typography.cardTitle,
    fontWeight: '900',
    lineHeight: 20,
    marginTop: theme.spacing.xs,
  },
});
