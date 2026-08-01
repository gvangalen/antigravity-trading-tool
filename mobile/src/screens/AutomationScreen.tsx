import { useCallback, useEffect, useMemo, useState } from 'react';
import { Feather } from '@expo/vector-icons';
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';

import { InsightCard } from '../components/cards/InsightCard';
import { LoadingSkeletonCard } from '../components/layout/LoadingSkeletonCard';
import { ScreenContainer } from '../components/layout/ScreenContainer';
import { StatusChip } from '../components/layout/StatusChip';
import { TodayWithFinnCard, type TodayWithFinnQueueItem, type TodayWithFinnTag } from '../components/workspace/TodayWithFinnCard';
import { WorkspaceHeroSection } from '../components/workspace/WorkspaceHeroSection';
import { StatusTone, theme } from '../constants/theme';
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

const automationFilters: Array<{ key: AutomationFilter; label: string }> = [
  { key: 'all', label: 'All' },
  { key: 'active', label: 'Active' },
  { key: 'paused', label: 'Paused' },
];

export function AutomationScreen() {
  const { context } = useIntelligenceContext();
  const { openFinn } = useFinnOverlay();
  const { appearance } = useAppPreferences();
  const colors = preferenceColors(appearance);
  const [filter, setFilter] = useState<AutomationFilter>('all');
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
    () => mergeAutomationBots(
      mapAutomationBots(configsResource.data, portfoliosResource.data),
      overviewBots,
    ),
    [configsResource.data, overviewBots, portfoliosResource.data],
  );
  const filteredBots = useMemo(() => filterAutomationBots(bots, filter), [bots, filter]);
  const activeBots = useMemo(() => bots.filter((bot) => bot.isActive), [bots]);
  const pausedBots = useMemo(() => bots.filter((bot) => !bot.isActive), [bots]);
  const liveBots = useMemo(() => bots.filter((bot) => bot.isLive), [bots]);
  const topBot =
    filteredBots.find((bot) => bot.symbol === activeAsset && bot.isActive) ??
    bots.find((bot) => bot.symbol === activeAsset && bot.isActive) ??
    filteredBots.find((bot) => bot.symbol === activeAsset) ??
    bots.find((bot) => bot.symbol === activeAsset) ??
    filteredBots.find((bot) => bot.isActive) ??
    bots.find((bot) => bot.isActive) ??
    filteredBots[0] ??
    bots[0] ??
    null;
  const decision = useMemo(() => mapBotDecision(extractRecord(decisionResource.data)), [decisionResource.data]);
  const remainingBots = useMemo(
    () => filteredBots.filter((bot) => !topBot || bot.id !== topBot.id),
    [filteredBots, topBot],
  );
  const loading = (configsResource.loading || portfoliosResource.loading) && bots.length === 0;
  const staleMessage =
    configsResource.error?.message ||
    portfoliosResource.error?.message ||
    decisionResource.error?.message ||
    overviewResource.error?.message;

  return (
    <ScreenContainer
      edgeToEdge={true}
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
      {topBot ? (
        <AutomationTodayHero
          activeAsset={activeAsset}
          activeCount={activeBots.length}
          bot={topBot}
          briefing={overviewResource.data?.finn_briefing}
          decision={decision}
          liveCount={liveBots.length}
          pausedCount={pausedBots.length}
          onOpen={() =>
            openFinn({
              prefill: `Open the automation workspace for ${topBot.name} on ${topBot.symbol}. Summarize today's execution state, key blockers and the first review step.`,
              source: 'automation-today',
              symbol: topBot.symbol,
            })
          }
        />
      ) : null}

      <AutomationWorkspaceIntro />

      {loading ? <LoadingSkeletonCard /> : null}

      {topBot ? (
        <PrimaryAutomationBotCard
          bot={topBot}
          checkedAt={decisionResource.updatedAt ?? overviewResource.updatedAt}
          colors={colors}
          decision={decision}
          onAskFinn={() =>
            openFinn({
              prefill: `Explain the automation diagnostics for ${topBot.name} on ${topBot.symbol}. Focus on budget, risk state, and what should happen next.`,
              source: 'automation-primary-bot',
              symbol: topBot.symbol,
            })
          }
          onReviewTrade={() =>
            openFinn({
              prefill: `Review whether ${topBot.name} on ${topBot.symbol} is safe to execute today. Translate the diagnostics into a concrete next action.`,
              source: 'automation-trade-review',
              symbol: topBot.symbol,
            })
          }
          onViewDiagnostics={() =>
            openFinn({
              prefill: `Show the full diagnostics for ${topBot.name} on ${topBot.symbol}. I want the complete explanation behind status, action, confidence and blockers.`,
              source: 'automation-full-diagnostics',
              symbol: topBot.symbol,
            })
          }
        />
      ) : (
        <InsightCard
          body="Desktop parity here starts when at least one reviewed bot configuration is available from the backend."
          label="Automation"
          title="No bot configuration found."
          tone="warning"
        />
      )}

      <AutomationBotList
        bots={remainingBots}
        colors={colors}
        filter={filter}
        onAskFinn={(bot) =>
          openFinn({
            prefill: `Open the automation context for ${bot.name} on ${bot.symbol}. Explain status, risk and next review step.`,
            source: 'automation-bot-row',
            symbol: bot.symbol,
          })
        }
        onChangeFilter={setFilter}
      />

      {staleMessage ? (
        <InsightCard
          body={staleMessage}
          cta="Refresh"
          label="Automation sync"
          onPress={() => {
            configsResource.refresh();
            portfoliosResource.refresh();
            decisionResource.refresh();
            overviewResource.refresh();
          }}
          title="Part of the automation state is stale."
          tone="warning"
        />
      ) : null}
    </ScreenContainer>
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
  onOpen,
}: {
  activeAsset: string;
  activeCount: number;
  bot: AutomationBot;
  briefing?: MobileOverviewResponse['finn_briefing'];
  decision: ReturnType<typeof mapBotDecision>;
  liveCount: number;
  pausedCount: number;
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

  const tags: TodayWithFinnTag[] = [
    {
      label: translateFinnTag(language, bot.isActive ? 'Active bot' : 'Paused bot'),
      tone: bot.isActive ? 'success' : 'warning',
    },
    { label: translateFinnTag(language, decision.action), tone: decision.tone },
    { label: translate(language, 'common.confidence', { count: decision.confidence }), tone: 'accent' },
    { label: translateFinnTag(language, bot.isLive ? 'Live' : 'Paper'), tone: bot.isLive ? 'danger' : 'neutral' },
  ];

  const queueItems: TodayWithFinnQueueItem[] = [
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
      value: Math.max(1, pausedCount),
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
        onPrimaryAction={onOpen}
        primaryActionLabel={translate(language, 'finn.openAutomationReview')}
        queueItems={queueItems}
        queueStatusLabel={translate(language, 'common.itemsOpen', { count: Number(queueItems[0]?.value ?? 0) })}
        support={support}
        tags={tags}
      />
    </WorkspaceHeroSection>
  );
}

function AutomationWorkspaceIntro() {
  const { appearance, language } = useAppPreferences();
  const colors = preferenceColors(appearance);
  const automationSteps = [
    {
      body: translate(language, 'automation.stepPlanBody'),
      icon: 'clipboard',
      index: '1',
      title: translate(language, 'automation.stepPlanTitle'),
    },
    {
      body: translate(language, 'automation.stepExecutionBody'),
      icon: 'cpu',
      index: '2',
      title: translate(language, 'automation.stepExecutionTitle'),
    },
    {
      body: translate(language, 'automation.stepMonitoringBody'),
      icon: 'shield',
      index: '3',
      title: translate(language, 'automation.stepMonitoringTitle'),
    },
  ] as const;

  return (
    <View style={[styles.introPanel, { backgroundColor: colors.surface, borderColor: colors.borderSubtle }]}>
      <View style={styles.introHeader}>
        <View style={styles.introCopy}>
          <Text style={[styles.sectionEyebrow, { color: colors.textDim }]}>
            {translate(language, 'automation.workspaceEyebrow')}
          </Text>
          <Text style={[styles.sectionTitle, { color: colors.text }]}>
            {translate(language, 'automation.workspaceTitle')}
          </Text>
          <Text style={[styles.sectionBody, { color: colors.textMuted }]}>
            {translate(language, 'automation.workspaceSubtitle')}
          </Text>
        </View>
        <StatusChip label={translate(language, 'automation.active')} tone="success" />
      </View>

      <ScrollView
        horizontal
        showsHorizontalScrollIndicator={false}
        style={styles.stepRail}
        contentContainerStyle={styles.stepRailContent}
      >
        {automationSteps.map((step) => (
          <View
            key={step.index}
            style={[styles.stepCard, { backgroundColor: colors.surface, borderColor: colors.borderSubtle }]}
          >
            <View style={[styles.stepIconWrap, { backgroundColor: colors.surfaceMuted }]}>
              <Feather color={colors.accent} name={step.icon} size={18} />
            </View>
            <View style={styles.stepCopy}>
              <Text style={[styles.stepTitle, { color: colors.text }]}>{`${step.index} ${step.title}`}</Text>
              <Text style={[styles.stepBody, { color: colors.textMuted }]}>{step.body}</Text>
            </View>
          </View>
        ))}
      </ScrollView>
    </View>
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
          label={translate(language, bot.isActive ? 'automation.active' : 'automation.paused')}
          tone={bot.isActive ? 'success' : 'warning'}
        />
      </View>

      <View style={styles.primaryBotBadgeRow}>
        <StatusChip label={bot.mode} tone="neutral" />
        <StatusChip
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
          <Text style={styles.primaryActionText}>Ask FINN</Text>
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

      <ScrollView
        horizontal
        showsHorizontalScrollIndicator={false}
        style={styles.filterRail}
        contentContainerStyle={styles.filterRailContent}
      >
        {automationFilters.map((item) => {
          const active = filter === item.key;
          return (
            <Pressable
              key={item.key}
              onPress={async () => {
                await triggerHaptic('selection');
                onChangeFilter(item.key);
              }}
              style={[
                styles.filterPill,
                active
                  ? styles.filterPillActive
                  : { backgroundColor: colors.surfaceMuted, borderColor: colors.surfaceMuted },
              ]}
            >
              <Text
                style={[
                  styles.filterPillText,
                  { color: active ? '#FFFFFF' : colors.textDim },
                ]}
              >
                {item.label}
              </Text>
            </Pressable>
          );
        })}
      </ScrollView>

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
                <Feather color={colors.accent} name="cpu" size={18} />
              </View>
              <View style={styles.botRowCopy}>
                <Text style={[styles.botRowTitle, { color: colors.text }]}>{bot.name}</Text>
                <Text style={[styles.botRowMeta, { color: colors.textMuted }]}>
                  {bot.symbol} · {bot.timeframe} · {translateFinnTag(language, bot.isLive ? 'Live' : 'Paper').toUpperCase()}
                </Text>
              </View>
            </View>

            <View style={styles.botRowRight}>
              <StatusChip
                label={translate(language, bot.isActive ? 'automation.active' : 'automation.paused')}
                tone={bot.isActive ? 'success' : 'warning'}
              />
              <Text style={[styles.botRowAction, { color: colors.accent }]}>
                {translate(language, bot.isActive ? 'automation.hold' : 'automation.review')}
              </Text>
              <Feather color={colors.textDim} name="chevron-down" size={18} />
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
      mode: readString(config, ['mode', 'execution_mode'], 'read-only'),
      name: readString(config, ['name', 'bot_name'], 'Bot'),
      symbol: readString(config, ['symbol', 'asset'], 'BTC'),
      timeframe: readString(setup, ['timeframe'], readString(config, ['timeframe', 'frequency'], '1D')).toUpperCase(),
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
    mode: bot.is_live ? 'live' : 'paper',
    name: bot.name,
    symbol: bot.symbol,
    timeframe: '1D',
  }));
}

function mergeAutomationBots(primary: AutomationBot[], fallback: AutomationBot[]) {
  if (primary.length === 0) return fallback;

  const fallbackById = new Map<number, AutomationBot>();
  fallback.forEach((bot) => fallbackById.set(bot.id, bot));

  return primary.map((bot) => {
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
}

function filterAutomationBots(bots: AutomationBot[], filter: AutomationFilter) {
  if (filter === 'active') return bots.filter((bot) => bot.isActive);
  if (filter === 'paused') return bots.filter((bot) => !bot.isActive);
  return bots;
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

function toneColor(tone: StatusTone, colors: ReturnType<typeof preferenceColors>) {
  if (tone === 'success') return colors.success;
  if (tone === 'warning') return colors.warning;
  if (tone === 'danger') return colors.danger;
  if (tone === 'accent') return colors.accent;
  return colors.text;
}

const styles = StyleSheet.create({
  botList: {
    gap: theme.spacing.sm,
    marginTop: theme.spacing.md,
    paddingBottom: 120,
  },
  botRow: {
    alignItems: 'center',
    borderBottomWidth: 1,
    flexDirection: 'row',
    gap: theme.spacing.sm,
    justifyContent: 'space-between',
    paddingVertical: theme.spacing.md,
  },
  botRowAction: {
    fontSize: 13,
    fontWeight: '800',
    letterSpacing: 0.3,
    textTransform: 'uppercase',
  },
  botRowCopy: {
    flex: 1,
    gap: 4,
  },
  botRowIcon: {
    alignItems: 'center',
    borderRadius: 20,
    height: 40,
    justifyContent: 'center',
    width: 40,
  },
  botRowLeft: {
    alignItems: 'center',
    flex: 1,
    flexDirection: 'row',
    gap: theme.spacing.sm,
  },
  botRowMeta: {
    fontSize: 12,
    fontWeight: '700',
    letterSpacing: 0.6,
  },
  botRowRight: {
    alignItems: 'center',
    flexDirection: 'row',
    gap: theme.spacing.xs,
  },
  botRowTitle: {
    fontSize: 15,
    fontWeight: '800',
    lineHeight: 20,
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
    fontSize: 11,
    fontWeight: '900',
    letterSpacing: 1.1,
    textTransform: 'uppercase',
  },
  filterPill: {
    alignItems: 'center',
    borderRadius: theme.radius.pill,
    borderWidth: 1,
    justifyContent: 'center',
    marginRight: 8,
    minHeight: 38,
    paddingHorizontal: 18,
  },
  filterPillActive: {
    backgroundColor: theme.colors.accent,
    borderColor: theme.colors.accent,
  },
  filterPillText: {
    fontSize: 12,
    fontWeight: '800',
    letterSpacing: 0.8,
    textTransform: 'uppercase',
  },
  filterRail: {
    marginTop: theme.spacing.md,
  },
  filterRailContent: {
    paddingRight: theme.spacing.lg,
  },
  introBody: {
    fontSize: 15,
    fontWeight: '600',
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
    borderRadius: 28,
    borderWidth: 1,
    marginHorizontal: theme.spacing.lg,
    marginTop: theme.spacing.md,
    padding: theme.spacing.lg,
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
    fontSize: 14,
    fontWeight: '600',
    lineHeight: 20,
    marginTop: 6,
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
    fontSize: 10,
    fontWeight: '900',
    letterSpacing: 1.3,
    textTransform: 'uppercase',
  },
  metricValue: {
    fontSize: 16,
    fontWeight: '800',
    lineHeight: 22,
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
    gap: theme.spacing.xs,
    marginTop: theme.spacing.md,
  },
  primaryBotHeader: {
    alignItems: 'flex-start',
    flexDirection: 'row',
    gap: theme.spacing.md,
    justifyContent: 'space-between',
  },
  primaryBotIcon: {
    alignItems: 'center',
    borderRadius: 24,
    height: 48,
    justifyContent: 'center',
    width: 48,
  },
  primaryBotIdentity: {
    flex: 1,
    flexDirection: 'row',
    gap: theme.spacing.sm,
  },
  primaryBotMeta: {
    fontSize: 13,
    fontWeight: '700',
    lineHeight: 18,
    marginTop: 4,
  },
  primaryBotPanel: {
    borderRadius: 28,
    borderWidth: 1,
    marginHorizontal: theme.spacing.lg,
    marginTop: theme.spacing.lg,
    padding: theme.spacing.lg,
  },
  primaryBotTitle: {
    fontSize: 22,
    fontWeight: '900',
    letterSpacing: -0.6,
    marginTop: 4,
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
    fontSize: 15,
    fontWeight: '600',
    lineHeight: 22,
    marginTop: theme.spacing.sm,
  },
  sectionEyebrow: {
    fontSize: theme.typography.label,
    fontWeight: '900',
    letterSpacing: 3.2,
    textTransform: 'uppercase',
  },
  sectionTitle: {
    fontSize: 34,
    fontWeight: '900',
    letterSpacing: -1.1,
    lineHeight: 38,
    marginTop: 6,
  },
  stepBody: {
    fontSize: 13,
    fontWeight: '700',
    lineHeight: 18,
    marginTop: 2,
  },
  stepCard: {
    alignItems: 'center',
    borderRadius: 24,
    borderWidth: 1,
    flexDirection: 'row',
    marginRight: theme.spacing.sm,
    minHeight: 104,
    paddingHorizontal: theme.spacing.md,
    paddingVertical: theme.spacing.md,
    width: 268,
  },
  stepCopy: {
    flex: 1,
  },
  stepIconWrap: {
    alignItems: 'center',
    borderRadius: 18,
    height: 48,
    justifyContent: 'center',
    marginRight: theme.spacing.md,
    width: 48,
  },
  stepRail: {
    marginTop: theme.spacing.lg,
  },
  stepRailContent: {
    paddingRight: theme.spacing.xl,
  },
  stepTitle: {
    fontSize: 16,
    fontWeight: '800',
    lineHeight: 20,
  },
  warningBody: {
    color: '#8A4B00',
    fontSize: 14,
    fontWeight: '700',
    lineHeight: 20,
    marginTop: theme.spacing.sm,
  },
  warningEyebrow: {
    color: '#C06A00',
    fontSize: 10,
    fontWeight: '900',
    letterSpacing: 2,
    textTransform: 'uppercase',
  },
  warningNextStep: {
    color: '#B45309',
    fontSize: 12,
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
    fontSize: 16,
    fontWeight: '900',
    lineHeight: 20,
    marginTop: theme.spacing.xs,
  },
});
