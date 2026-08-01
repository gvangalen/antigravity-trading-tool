import { useCallback, useEffect, useMemo, useState } from 'react';
import { Feather } from '@expo/vector-icons';
import { useNavigation } from '@react-navigation/native';
import type { NavigationProp } from '@react-navigation/native';
import { Pressable, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';
import Svg, { Path } from 'react-native-svg';

import { CardShell } from '../components/cards/CardShell';
import { InsightCard } from '../components/cards/InsightCard';
import { LoadingSkeletonCard } from '../components/layout/LoadingSkeletonCard';
import { ScreenContainer } from '../components/layout/ScreenContainer';
import { StatusChip } from '../components/layout/StatusChip';
import { SegmentedControl } from '../components/layout/SegmentedControl';
import { BottomSheet } from '../components/sheets/BottomSheet';
import { TodayWithFinnCard } from '../components/workspace/TodayWithFinnCard';
import { WorkspaceHeroSection } from '../components/workspace/WorkspaceHeroSection';
import { StatusTone, theme } from '../constants/theme';
import { useApiResource } from '../hooks/useApiResource';
import { localizedBackendText, translate, translateFinnTag } from '../i18n';
import { preferenceColors, useAppPreferences } from '../preferences/AppPreferencesProvider';
import type { MainTabParamList } from '../navigation/MainTabNavigator';
import {
  MobileOverviewResponse,
  OrderPreviewResponse,
  intelligenceApi,
  mobileApi,
} from '../services/tradamindApi';
import { triggerHaptic } from '../utils/haptics';
import { useIntelligenceContext } from '../contexts/ActiveIntelligenceContext';
import { useFinnOverlay } from '../contexts/FinnOverlayContext';
import { trackAssistantEvent } from '../services/assistantAnalytics';

type UnknownRecord = Record<string, unknown>;
type EnvFilter = 'all' | 'paper' | 'live';
type RangeKey = '1D' | '1W' | '1M' | '1Y' | 'ALL';
type MetricKey = 'equity' | 'cash' | 'btc_value' | 'btc_qty' | 'invested' | 'unrealized_pnl';
type TradeMode = 'buy' | 'sell' | 'dca' | 'bot';
type AmountUnit = 'EUR' | 'BTC';

type PortfolioBot = {
  id: number;
  name: string;
  symbol: string;
  timeframe: string;
  strategy: string;
  mode: string;
  riskProfile: string;
  isActive: boolean;
  isLive: boolean;
  budgetTotal: number;
  budgetDailyLimit: number;
  budgetMaxOrder: number;
  todaySpent: number;
  invested: number;
  positionValue: number;
  netQty: number;
  available: number;
};

type ExchangeSummary = {
  count: number;
  freeEur: number;
  names: string[];
  totalEur: number;
};

const envFilters: EnvFilter[] = ['all', 'paper', 'live'];
const ranges: Array<{ key: RangeKey; bucket: string; limit: number }> = [
  { key: '1D', bucket: '1h', limit: 24 },
  { key: '1W', bucket: '1h', limit: 24 * 7 },
  { key: '1M', bucket: '1d', limit: 30 },
  { key: '1Y', bucket: '1d', limit: 365 },
  { key: 'ALL', bucket: '1d', limit: 2000 },
];
const metrics: Array<{ key: MetricKey; label: string }> = [
  { key: 'equity', label: 'Equity' },
  { key: 'cash', label: 'Cash' },
  { key: 'btc_value', label: 'BTC value' },
  { key: 'btc_qty', label: 'BTC qty' },
  { key: 'invested', label: 'Invested' },
  { key: 'unrealized_pnl', label: 'Unrealized PnL' },
];

export function PortfolioScreen() {
  const navigation = useNavigation<NavigationProp<MainTabParamList>>();
  const { context } = useIntelligenceContext();
  const activeAsset = context.asset;
  const { openFinn } = useFinnOverlay();
  const [envFilter, setEnvFilter] = useState<EnvFilter>('all');
  const [range, setRange] = useState<RangeKey>('1W');
  const [metric, setMetric] = useState<MetricKey>('equity');
  const [tradeSheetOpen, setTradeSheetOpen] = useState(false);
  const [tradeMode, setTradeMode] = useState<TradeMode>('buy');
  const [executionExpanded, setExecutionExpanded] = useState(false);
  const [amountUnit, setAmountUnit] = useState<AmountUnit>('EUR');

  useEffect(() => {
    trackAssistantEvent({
      event_name: 'screen_view',
      page: 'portfolio',
      flow_type: 'portfolio_review',
    });
  }, []);
  const [amountValue, setAmountValue] = useState('');
  const [amountPreset, setAmountPreset] = useState(0);
  const [tradePreview, setTradePreview] = useState<OrderPreviewResponse | null>(null);
  const [tradePreviewError, setTradePreviewError] = useState('');
  const [tradePreviewLoading, setTradePreviewLoading] = useState(false);

  const rangeConfig = ranges.find((item) => item.key === range) ?? ranges[1];
  const isLiveFilter = envFilter === 'all' ? undefined : envFilter === 'live';

  const fetchOverview = useCallback(() => mobileApi.overview(activeAsset), [activeAsset]);
  const overviewResource = useApiResource<MobileOverviewResponse | undefined>({
    fallbackData: undefined,
    fetcher: fetchOverview,
  });

  const fetchPortfolios = useCallback(async () => asArray(await intelligenceApi.botPortfolios()), []);
  const portfoliosResource = useApiResource<UnknownRecord[]>({
    fallbackData: [],
    fetcher: fetchPortfolios,
  });

  const fetchConfigs = useCallback(async () => asArray(await intelligenceApi.botConfigs()), []);
  const configsResource = useApiResource<UnknownRecord[]>({
    fallbackData: [],
    fetcher: fetchConfigs,
  });

  const fetchExchangeBalances = useCallback(async () => {
    try {
      return asArray(await intelligenceApi.exchangeBalances());
    } catch {
      return [];
    }
  }, []);
  const exchangeResource = useApiResource<UnknownRecord[]>({
    fallbackData: [],
    fetcher: fetchExchangeBalances,
  });

  const fetchHistory = useCallback(
    async () =>
      asArray(
        await intelligenceApi.balanceHistory({
          bucket: rangeConfig.bucket,
          is_live: isLiveFilter,
          limit: rangeConfig.limit,
        }),
      ),
    [isLiveFilter, rangeConfig.bucket, rangeConfig.limit],
  );
  const historyResource = useApiResource<UnknownRecord[]>({
    fallbackData: [],
    fetcher: fetchHistory,
  });

  const overviewBots = useMemo(
    () => mapOverviewBots(overviewResource.data),
    [overviewResource.data],
  );
  const bots = useMemo(
    () => mergePortfolioBots(mapBots(portfoliosResource.data, configsResource.data), overviewBots),
    [configsResource.data, overviewBots, portfoliosResource.data],
  );
  const filteredBots = useMemo(
    () => bots.filter((bot) => envFilter === 'all' || bot.isLive === (envFilter === 'live')),
    [bots, envFilter],
  );
  const aggregate = useMemo(
    () => aggregateBots(filteredBots, overviewResource.data?.portfolio),
    [filteredBots, overviewResource.data?.portfolio],
  );
  const exchangeSummary = useMemo(() => summarizeExchange(exchangeResource.data), [exchangeResource.data]);
  const history = useMemo(() => normalizeHistory(historyResource.data), [historyResource.data]);
  const performance = useMemo(() => getPerformance(history, metric, aggregate), [aggregate, history, metric]);
  const { updateContext } = useIntelligenceContext();
  const activeOverviewAsset = overviewResource.data?.watchlist.find((asset) => asset.symbol === activeAsset);
  const primaryBot = filteredBots.find((bot) => bot.symbol === activeAsset && bot.isActive) ?? filteredBots.find((bot) => bot.isActive) ?? filteredBots[0];
  const loading =
    overviewResource.loading ||
    portfoliosResource.loading ||
    configsResource.loading ||
    exchangeResource.loading ||
    historyResource.loading;
  const isStale =
    overviewResource.isStale ||
    portfoliosResource.isStale ||
    configsResource.isStale ||
    exchangeResource.isStale ||
    historyResource.isStale;
  async function changeEnv(next: EnvFilter) {
    await triggerHaptic('selection');
    setEnvFilter(next);
  }

  async function changeRange(next: RangeKey) {
    await triggerHaptic('selection');
    setRange(next);
  }

  async function changeMetric(next: MetricKey) {
    await triggerHaptic('selection');
    setMetric(next);
  }

  async function openTradeSheet() {
    await triggerHaptic('selection');
    setTradeSheetOpen(true);
  }

  async function askFinnTradeCheck() {
    await triggerHaptic('selection');
    setTradeSheetOpen(false);
    openFinn({
      prefill: buildTradePrefill({
        activeAsset,
        amountUnit,
        amountValue,
        bot: primaryBot,
        exchangeSummary,
        mode: tradeMode,
        overview: activeOverviewAsset,
      }),
      source: 'portfolio_trade_sheet',
    });
  }

  async function requestTradePreview() {
    await triggerHaptic('selection');
    setTradePreviewError('');
    setTradePreview(null);

    if (!primaryBot) {
      setTradePreviewError('Geen actieve bot gevonden voor deze trade preview.');
      return;
    }

    const payload = buildOrderPreviewPayload({
      activeAsset,
      amountUnit,
      amountValue,
      bot: primaryBot,
      mode: tradeMode,
      overview: activeOverviewAsset,
    });

    if (!payload) {
      setTradePreviewError('Vul eerst een geldig bedrag in voor de preview.');
      return;
    }

    setTradePreviewLoading(true);
    try {
      const preview = await intelligenceApi.previewOrder(payload);
      setTradePreview(preview);
    } catch (error) {
      setTradePreviewError(error instanceof Error ? error.message : 'Order preview is mislukt.');
    } finally {
      setTradePreviewLoading(false);
    }
  }

  function updateTradeMode(next: TradeMode) {
    setTradeMode(next);
    setTradePreview(null);
    setTradePreviewError('');
  }

  function updateAmountUnit(next: AmountUnit) {
    setAmountUnit(next);
    setTradePreview(null);
    setTradePreviewError('');
  }

  function updateAmountValue(next: string) {
    setAmountValue(next);
    setTradePreview(null);
    setTradePreviewError('');
  }

  return (
    <View style={styles.screenWrap}>
      <ScreenContainer
        edgeToEdge={true}
        contentInsetBottom={170}
        refreshing={
          overviewResource.refreshing ||
          portfoliosResource.refreshing ||
          configsResource.refreshing ||
          exchangeResource.refreshing ||
          historyResource.refreshing
        }
        onRefresh={() => {
          overviewResource.refresh();
          portfoliosResource.refresh();
          configsResource.refresh();
          exchangeResource.refresh();
          historyResource.refresh();
        }}
      >
        {loading && bots.length === 0 ? (
          <LoadingSkeletonCard />
        ) : (
          <>
            <PortfolioWorkspaceHero
              activeAsset={activeAsset}
              briefing={overviewResource.data?.finn_briefing}
              filteredBots={filteredBots.length}
              isStale={isStale}
              metric={metric}
              onAskFinn={askFinnTradeCheck}
              performance={performance.last}
            />
            <PortfolioWorkspaceIntro />
            <PortfolioPerformanceCard
              delta={performance.delta}
              metric={metric}
              onMetricChange={changeMetric}
              onRangeChange={changeRange}
              points={history}
              range={range}
              total={performance.last}
            />
            <PortfolioCapitalAllocationCard
              aggregate={aggregate}
              bots={filteredBots}
              envFilter={envFilter}
              exchangeSummary={exchangeSummary}
              onEnvFilterChange={changeEnv}
            />
            <MyBotsSection bots={filteredBots} totalBots={bots.length} onOpenTrade={openTradeSheet} />
          </>
        )}

        {portfoliosResource.error || configsResource.error || exchangeResource.error || historyResource.error ? (
          <InsightCard
            label="Portfolio sync"
            title="Een deel van de portfolio-data is stale."
            body={
              portfoliosResource.error?.message ||
              configsResource.error?.message ||
              exchangeResource.error?.message ||
              historyResource.error?.message ||
              'Controleer backend/API status.'
            }
            tone="warning"
            cta="Pull to refresh"
          />
        ) : null}
      </ScreenContainer>



      <BottomSheet visible={tradeSheetOpen} title="AI trade flow" onClose={() => setTradeSheetOpen(false)}>
        <TradeActionSheet
          activeAsset={activeAsset}
          amountPreset={amountPreset}
          amountUnit={amountUnit}
          amountValue={amountValue}
          bot={primaryBot}
          executionExpanded={executionExpanded}
          exchangeSummary={exchangeSummary}
          mode={tradeMode}
          overview={activeOverviewAsset}
          preview={tradePreview}
          previewError={tradePreviewError}
          previewLoading={tradePreviewLoading}
          stale={isStale}
          onAmountPresetChange={setAmountPreset}
          onAmountUnitChange={updateAmountUnit}
          onAmountValueChange={updateAmountValue}
          onAskFinn={askFinnTradeCheck}
          onExecutionExpandedChange={setExecutionExpanded}
          onModeChange={updateTradeMode}
          onPreview={requestTradePreview}
        />
      </BottomSheet>
    </View>
  );
}

function PortfolioWorkspaceIntro() {
  const { appearance } = useAppPreferences();
  const colors = preferenceColors(appearance);
  const steps = [
    { icon: 'pie-chart', title: '1 Balance', text: 'How much capital, cash and exposure is active?' },
    { icon: 'trending-up', title: '2 Performance', text: 'How is equity evolving across the selected range?' },
    { icon: 'briefcase', title: '3 Bots', text: 'Which live or paper bots currently drive portfolio risk?' },
  ] as const;

  return (
    <View style={[styles.workspaceIntroPanel, { borderColor: colors.borderSubtle }]}>
      <View style={styles.sectionTop}>
        <View style={styles.flexText}>
          <Text style={[styles.workspaceEyebrow, { color: colors.textDim }]}>Portfolio workspace</Text>
          <Text style={[styles.workspaceIntroTitle, { color: colors.text }]}>Portfolio</Text>
          <Text style={[styles.workspaceIntroSubtitle, { color: colors.textMuted }]}>
            Review positions, exposure and actions that need attention.
          </Text>
        </View>
        <StatusChip label="Active" tone="success" />
      </View>

      <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.workflowRail}>
        {steps.map((step) => (
          <View
            key={step.title}
            style={[styles.workflowCard, { backgroundColor: colors.surfaceMuted, borderColor: colors.borderSubtle }]}
          >
            <View style={[styles.workflowIcon, { backgroundColor: colors.surface }]}>
              <Feather name={step.icon} size={16} color={colors.accent} />
            </View>
            <View style={styles.workflowCopy}>
              <Text style={[styles.workflowTitle, { color: colors.accent }]}>{step.title}</Text>
              <Text style={[styles.workflowText, { color: colors.textMuted }]}>{step.text}</Text>
            </View>
          </View>
        ))}
      </ScrollView>
    </View>
  );
}

function PortfolioWorkspaceHero({
  activeAsset,
  briefing,
  filteredBots,
  isStale,
  metric,
  onAskFinn,
  performance,
}: {
  activeAsset: string;
  briefing?: MobileOverviewResponse['finn_briefing'];
  filteredBots: number;
  isStale: boolean;
  metric: MetricKey;
  onAskFinn: () => void;
  performance: number;
}) {
  const { language } = useAppPreferences();
  const tags = [
    {
      label: translate(language, 'portfolio.activeSources', { count: filteredBots }),
      tone: 'accent' as StatusTone,
    },
    {
      label: metric.replace('_', ' '),
      tone: 'neutral' as StatusTone,
    },
    { label: isStale ? 'Stale sync' : 'Live', tone: isStale ? ('warning' as StatusTone) : ('success' as StatusTone) },
  ];
  const queueItems = [
    {
      key: 'tasks',
      label: translate(language, 'queue.label.tasks'),
      value: filteredBots,
      body: translate(language, 'queue.body.botsInCurrentPortfolioLens'),
    },
    {
      key: 'reviews',
      label: translate(language, 'queue.label.reviews'),
      value: filteredBots > 0 ? 1 : 0,
      body: translate(language, 'queue.body.executionFlowNeedsReview'),
    },
    {
      key: 'risks',
      label: translate(language, 'queue.label.risks'),
      value: isStale ? 1 : 0,
      body: translate(language, 'queue.body.staleSyncMissingBackendContext'),
    },
    {
      key: 'performance',
      label: translate(language, 'queue.label.performance'),
      value: performance >= 0 ? 1 : 0,
      body: translate(language, 'queue.body.visiblePerformanceMatchesMetric'),
    },
  ];
  const headline = localizedBackendText(
    language,
    briefing?.summary?.trim(),
    translate(language, 'finn.noBriefingReady'),
  );
  const support = isStale
    ? translate(language, 'portfolio.staleSupport')
    : translate(language, 'portfolio.metricSupport', { metric: metric.replace('_', ' ') });

  return (
    <WorkspaceHeroSection>
      <TodayWithFinnCard
        headline={headline}
        support={support}
        tags={tags.map((tag) => ({ ...tag, label: translateFinnTag(language, tag.label) }))}
        primaryActionLabel={translate(language, 'finn.askAboutExposure')}
        onPrimaryAction={onAskFinn}
        queueItems={queueItems}
        queueStatusLabel={translate(language, 'common.itemsOpen', { count: filteredBots })}
      />
    </WorkspaceHeroSection>
  );
}

function FilledBadge({ label, tone }: { label: string; tone: StatusTone }) {
  const { appearance } = useAppPreferences();
  const colors = preferenceColors(appearance);
  const palettes: Record<StatusTone, { background: string; border: string; color: string }> = {
    accent: { background: '#E8F0FF', border: '#C7D7FE', color: colors.accent },
    success: { background: '#EAF9F3', border: '#C8EFD9', color: colors.success },
    warning: { background: '#FEF5E7', border: '#F9D9A7', color: colors.warning },
    danger: { background: '#FDECEF', border: '#F8C7D1', color: colors.danger },
    neutral: { background: colors.surface, border: colors.borderSubtle, color: colors.textDim },
  };
  const palette = palettes[tone];

  return (
    <View style={[styles.filledBadge, { backgroundColor: palette.background, borderColor: palette.border }]}>
      <View style={[styles.filledBadgeDot, { backgroundColor: palette.color }]} />
      <Text style={[styles.filledBadgeText, { color: palette.color }]}>{label}</Text>
    </View>
  );
}

function PortfolioPerformanceCard({
  delta,
  metric,
  onMetricChange,
  onRangeChange,
  points,
  range,
  total,
}: {
  delta: { absolute: number; percent: number | null };
  metric: MetricKey;
  onMetricChange: (value: MetricKey) => void;
  onRangeChange: (value: RangeKey) => void;
  points: UnknownRecord[];
  range: RangeKey;
  total: number;
}) {
  const { appearance } = useAppPreferences();
  const colors = preferenceColors(appearance);
  const isDown = delta.absolute < 0;
  const accentColor = metric === 'unrealized_pnl' ? (isDown ? theme.colors.danger : theme.colors.success) : theme.colors.accent;
  const deltaLabel =
    delta.percent === null
      ? formatMetric(delta.absolute, metric)
      : `${formatMetric(delta.absolute, metric)} · ${formatPercent(delta.percent)}`;

  return (
    <View style={[styles.portfolioHeroCard, { backgroundColor: colors.surfaceMuted, borderColor: colors.borderSubtle }]}>
      <View style={styles.performanceHeader}>
        <View style={styles.performanceCopy}>
          <Text style={[styles.heroKicker, { color: colors.textDim }]}>Portfolio overview</Text>
          <Text style={[styles.heroValue, { color: colors.text }]}>{formatMetric(total, metric)}</Text>
          <View style={styles.deltaRow}>
            <View style={[styles.deltaSoftBadge, { backgroundColor: isDown ? '#FDECEF' : '#EAF9F3' }]}>
              <Text style={[styles.deltaSoftText, { color: isDown ? theme.colors.danger : theme.colors.success }]}>
                {deltaLabel}
              </Text>
            </View>
          </View>
        </View>
        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.rangeRail}>
          <SegmentedControl
            compact
            items={ranges.map((item) => ({ key: item.key, label: item.key }))}
            selected={range}
            onChange={(value) => onRangeChange(value as RangeKey)}
          />
        </ScrollView>
      </View>

      <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.metricRail}>
        <SegmentedControl
          compact
          items={metrics.map((item) => ({ key: item.key, label: item.label.toUpperCase() }))}
          selected={metric}
          onChange={(value) => onMetricChange(value as MetricKey)}
        />
      </ScrollView>

      <SparkChart accentColor={accentColor} metric={metric} points={points} />
    </View>
  );
}

function PortfolioCapitalAllocationCard({
  aggregate,
  bots,
  envFilter,
  exchangeSummary,
  onEnvFilterChange,
}: {
  aggregate: ReturnType<typeof aggregateBots>;
  bots: PortfolioBot[];
  envFilter: EnvFilter;
  exchangeSummary: ReturnType<typeof summarizeExchange>;
  onEnvFilterChange: (value: EnvFilter) => void;
}) {
  const { appearance } = useAppPreferences();
  const colors = preferenceColors(appearance);
  const budgetItems = [
    { label: 'Today spent', value: formatEUR(aggregate.todaySpent), tone: 'warning' as const },
    { label: 'Daily limit', value: formatEUR(aggregate.dailyLimit), tone: 'neutral' as const },
    { label: 'Sum max/trade', value: formatEUR(aggregate.maxOrder), tone: 'accent' as const },
  ];
  const portfolioMetrics = [
    { label: 'Positions', value: String(aggregate.assetRows.length), tone: 'accent' as StatusTone },
    { label: 'Total value', value: formatEUR(aggregate.positionValue), tone: 'neutral' as StatusTone },
    { label: 'Invested', value: formatEUR(aggregate.invested), tone: 'neutral' as StatusTone },
    {
      label: 'PnL total',
      value: `${formatEUR(aggregate.pnl)} ${formatPercent(aggregate.pnlPct)}`,
      tone: aggregate.pnl >= 0 ? ('success' as StatusTone) : ('danger' as StatusTone),
    },
  ];
  const available = Math.max(aggregate.totalBudget - aggregate.invested, 0);
  const usedPct = aggregate.totalBudget > 0 ? Math.min(100, (aggregate.invested / aggregate.totalBudget) * 100) : 0;

  return (
    <View style={styles.portfolioSection}>
      <View style={styles.sectionTop}>
        <View>
          <Text style={styles.kicker}>Portfolio data</Text>
          <Text style={[styles.cardTitle, { color: colors.text }]}>Capital allocation</Text>
        </View>
        <StatusChip label={`${bots.filter((bot) => bot.isActive).length} active`} tone="accent" />
      </View>

      <SegmentedControl
        items={envFilters.map((item) => ({ key: item, label: item.toUpperCase() }))}
        selected={envFilter}
        onChange={(value) => onEnvFilterChange(value as EnvFilter)}
      />

      <View style={[styles.allocationCard, { backgroundColor: colors.surfaceMuted, borderColor: colors.borderSubtle }]}>
        <Text style={[styles.allocationLabel, { color: colors.text }]}>Combined allocation</Text>
        <View style={styles.allocationRow}>
          <Text style={[styles.allocationValue, { color: colors.textMuted }]}>
            {formatEUR(aggregate.invested)} / {formatEUR(aggregate.totalBudget)}
          </Text>
        </View>
        <View style={[styles.progressTrack, { backgroundColor: colors.borderSubtle }]}>
          <View style={[styles.progressFill, { width: `${usedPct}%`, backgroundColor: theme.colors.success }]} />
        </View>
        <View style={[styles.availableRow, { borderBottomColor: colors.borderSubtle }]}>
          <Text style={[styles.availableLabel, { color: colors.textMuted }]}>Available</Text>
          <Text style={[styles.availableValue, { color: colors.text }]}>{formatEUR(available)}</Text>
        </View>
        <View style={styles.allocationMetrics}>
          {budgetItems.map((item) => (
            <View key={item.label} style={styles.allocationMetric}>
              <Text style={[styles.allocationMetricLabel, { color: colors.textDim }]}>{item.label}</Text>
              <Text style={[styles.allocationMetricValue, { color: toneColor(item.tone) }]}>{item.value}</Text>
            </View>
          ))}
        </View>
      </View>

      <View style={styles.portfolioMetricGrid}>
        {portfolioMetrics.map((item) => (
          <View
            key={item.label}
            style={[styles.portfolioMetricCard, { backgroundColor: colors.surfaceMuted, borderColor: colors.borderSubtle }]}
          >
            <Text style={[styles.portfolioMetricLabel, { color: colors.textDim }]}>{item.label}</Text>
            <Text style={[styles.portfolioMetricValue, { color: toneColor(item.tone) }]}>{item.value}</Text>
          </View>
        ))}
      </View>

      <View style={styles.breakdownSection}>
        <View style={styles.sectionTop}>
          <View>
            <Text style={styles.kicker}>Breakdown by asset</Text>
            <Text style={[styles.exchangeSubtitle, { color: colors.textMuted }]}>
              {exchangeSummary.count > 0 && envFilter !== 'paper'
                ? `${exchangeSummary.count} active source${exchangeSummary.count === 1 ? '' : 's'}`
                : 'Current visible asset exposure.'}
            </Text>
          </View>
        </View>
        <View style={styles.breakdownList}>
          {aggregate.assetRows.map((row, index) => (
            <View
              key={row.symbol}
              style={[
                styles.breakdownRow,
                { borderBottomColor: colors.borderSubtle },
                index === aggregate.assetRows.length - 1 && styles.breakdownRowLast,
              ]}
            >
              <View style={styles.breakdownIdentity}>
                <View style={[styles.breakdownDot, { backgroundColor: index === 0 ? theme.colors.accent : colors.textSoft }]} />
                <View>
                  <Text style={[styles.breakdownSymbol, { color: colors.text }]}>{row.symbol}</Text>
                  <Text style={[styles.breakdownQty, { color: colors.textDim }]}>
                    {row.netQty.toFixed(6)} {row.symbol}
                  </Text>
                </View>
              </View>
              <View style={styles.breakdownValues}>
                <Text style={[styles.breakdownPrice, { color: colors.text }]}>{formatEUR(row.positionValue)}</Text>
                <Text style={[styles.breakdownPnl, { color: row.pnl >= 0 ? theme.colors.success : theme.colors.danger }]}>
                  {formatEUR(row.pnl)} {formatPercent(row.pnlPct)}
                </Text>
              </View>
            </View>
          ))}
        </View>
      </View>
    </View>
  );
}

function MyBotsSection({ bots, totalBots, onOpenTrade }: { bots: PortfolioBot[]; totalBots: number; onOpenTrade: () => void }) {
  const { appearance } = useAppPreferences();
  const colors = preferenceColors(appearance);

  return (
    <View style={styles.myBots}>
      <View style={{ paddingHorizontal: theme.spacing.lg }}>
        <Text style={[styles.myBotsTitle, { color: colors.text }]}>Active sources</Text>
        <Text style={[styles.myBotsSubtitle, { color: colors.textMuted }]}>Same live and paper bot state as desktop, compact for mobile review.</Text>
      </View>
      <View style={[styles.filterPills, { paddingHorizontal: theme.spacing.lg }]}>
        <StatusChip label={`All ${totalBots}`} tone="accent" />
        <StatusChip label={`Active ${bots.filter((bot) => bot.isActive).length}`} tone="success" />
      </View>
      <Pressable
        onPress={onOpenTrade}
        style={({ pressed }) => [
          styles.inlineTradeButton,
          { backgroundColor: colors.backgroundSoft, borderColor: colors.border },
          pressed && { opacity: 0.8 }
        ]}
      >
        <Text style={[styles.inlineTradeButtonText, { color: colors.text }]}>Open AI Trade Flow</Text>
      </Pressable>
      {bots.length === 0 ? (
        <InsightCard
          label="Bots"
          title="Geen bots in deze filter."
          body="Wissel naar All of refresh de backenddata."
          tone="neutral"
        />
      ) : (
        bots.map((bot) => <BotCard bot={bot} key={bot.id} />)
      )}
    </View>
  );
}

function BotCard({ bot }: { bot: PortfolioBot }) {
  const { appearance } = useAppPreferences();
  const colors = preferenceColors(appearance);
  const pnl = bot.positionValue - bot.invested;
  const pnlPct = bot.invested > 0 ? (pnl / bot.invested) * 100 : 0;

  return (
    <View style={[styles.botRow, { borderBottomColor: colors.borderSubtle }]}>
      <View style={styles.botTop}>
        <View style={styles.botIcon}>
          <Text style={styles.botIconText}>BT</Text>
        </View>
        <View style={styles.botTitleBlock}>
          <View style={styles.botNameRow}>
            <Text style={[styles.botName, { color: colors.text }]}>{bot.name}</Text>
            <View style={[styles.statusDot, { backgroundColor: bot.isActive ? theme.colors.warning : theme.colors.neutral }]} />
          </View>
          <Text style={[styles.botMeta, { color: colors.textDim }]}>
            {bot.symbol}  -  {bot.timeframe}  -  {bot.strategy}
          </Text>
        </View>
      </View>
      <View style={styles.botChips}>
        <Tag label={bot.riskProfile || 'Strategy'} tone={bot.riskProfile.toLowerCase().includes('aggressive') ? 'danger' : 'warning'} />
        <Tag label={bot.isLive ? 'Live' : 'Paper'} tone={bot.isLive ? 'danger' : 'accent'} />
        <Tag label={bot.mode || 'Manual-link'} tone="neutral" />
      </View>
      <View style={styles.botMetricGrid}>
        <BotMetric label="Execution state" value={bot.isActive ? (bot.isLive ? 'Live ready' : 'Paper ready') : 'Paused'} tone={bot.isActive ? (bot.isLive ? 'danger' : 'accent') : 'neutral'} />
        <BotMetric label="Market action" value={bot.positionValue > 0 ? 'Manage' : 'Hold'} tone="accent" />
        <BotMetric label="PnL status" value={pnlPct >= 0 ? 'Constructive' : 'Review'} tone={pnlPct >= 0 ? 'success' : 'warning'} />
        <BotMetric label="Budget" value={formatEUR(bot.budgetTotal)} tone="neutral" />
      </View>
      <View style={styles.botFooter}>
        <Text style={[styles.botFooterText, { color: colors.textDim }]}>Invested {formatEUR(bot.invested)}</Text>
        <Text style={[styles.botFooterText, { color: pnl >= 0 ? theme.colors.success : theme.colors.danger }]}>
          PnL {formatEUR(pnl)} {formatPercent(pnlPct)}
        </Text>
      </View>
    </View>
  );
}

function WorkspaceStatRow({ label, value }: { label: string; value: string }) {
  const { appearance } = useAppPreferences();
  const colors = preferenceColors(appearance);

  return (
    <View style={styles.workspaceRow}>
      <Text style={[styles.workspaceRowLabel, { color: colors.textDim }]}>{label}</Text>
      <Text style={[styles.workspaceRowValue, { color: colors.text }]}>{value}</Text>
    </View>
  );
}



function SparkChart({
  accentColor,
  metric,
  points,
}: {
  accentColor: string;
  metric: MetricKey;
  points: UnknownRecord[];
}) {
  const values = points.map((point) => readNumber(point, [metric], 0));
  const visible = values.slice(Math.max(0, values.length - 52));
  const max = Math.max(...visible, 1);
  const min = Math.min(...visible);
  const span = Math.max(max - min, 1);

  if (visible.length === 0) {
    return (
      <View style={styles.chartBox}>
        <Text style={styles.emptyChartText}>Geen balance history beschikbaar</Text>
      </View>
    );
  }

  const stepX = 100 / Math.max(visible.length - 1, 1);
  
  // Construct path points
  const pathPoints = visible.map((value, index) => {
    const x = index * stepX;
    const heightPct = 14 + ((value - min) / span) * 78;
    const y = 100 - heightPct;
    return { x, y };
  });

  // Construct Line Path
  const linePath = pathPoints.map((p, i) => `${i === 0 ? 'M' : 'L'} ${p.x} ${p.y}`).join(' ');

  // Construct Area Path
  const areaPath = `${linePath} L 100 100 L 0 100 Z`;

  // Get timestamps for visible points (fallback to mock dates if missing)
  const visiblePoints = points.slice(Math.max(0, points.length - 52));
  
  const formatDataDate = (ts: string | undefined) => {
    if (!ts) return '';
    const d = new Date(ts);
    return d.toLocaleDateString('nl-NL', { day: '2-digit', month: 'short' });
  };

  // Calculate 5 points for X-axis
  const len = visiblePoints.length;
  const firstDate = formatDataDate(visiblePoints[0]?.ts as string);
  const lastDate = formatDataDate(visiblePoints[len - 1]?.ts as string);
  const p25Date = formatDataDate(visiblePoints[Math.floor(len * 0.25)]?.ts as string);
  const p50Date = formatDataDate(visiblePoints[Math.floor(len * 0.50)]?.ts as string);
  const p75Date = formatDataDate(visiblePoints[Math.floor(len * 0.75)]?.ts as string);

  return (
    <View style={styles.chartBox}>
      <View style={styles.chartCanvas}>
        <Svg width="100%" height="100%" viewBox="0 0 100 100">
          <Path
            d={areaPath}
            fill={accentColor}
            opacity={0.15}
          />
          <Path
            d={linePath}
            stroke={accentColor}
            strokeWidth={2}
            fill="none"
          />
        </Svg>
      </View>

      <View style={styles.chartAxisLabels}>
        <Text style={styles.chartAxisText}>{firstDate}</Text>
        <Text style={styles.chartAxisText}>{p25Date}</Text>
        <Text style={styles.chartAxisText}>{p50Date}</Text>
        <Text style={styles.chartAxisText}>{p75Date}</Text>
        <Text style={styles.chartAxisText}>{lastDate}</Text>
      </View>
    </View>
  );
}

function SmallStat({ label, value }: { label: string; value: string }) {
  const { appearance } = useAppPreferences();
  const colors = preferenceColors(appearance);

  return (
    <View style={styles.smallStat}>
      <Text style={[styles.metricLabel, { color: colors.textDim }]}>{label}</Text>
      <Text style={[styles.smallStatValue, { color: colors.text }]}>{value}</Text>
    </View>
  );
}

function BigStat({ label, tone, value }: { label: string; tone?: StatusTone; value: string }) {
  const { appearance } = useAppPreferences();
  const colors = preferenceColors(appearance);

  return (
    <View style={[styles.bigStat, { backgroundColor: colors.backgroundSoft, borderColor: colors.border }]}>
      <Text style={[styles.metricLabel, { color: colors.textDim }]}>{label}</Text>
      <Text style={[styles.bigStatValue, { color: colors.text }, tone && { color: toneColor(tone) }]}>{value}</Text>
    </View>
  );
}

function Tag({ label, tone }: { label: string; tone: StatusTone }) {
  return (
    <View style={[styles.tag, { borderColor: toneColor(tone) }]}>
      <Text style={[styles.tagText, { color: toneColor(tone) }]}>{label}</Text>
    </View>
  );
}

function BotMetric({ label, tone, value }: { label: string; tone: StatusTone; value: string }) {
  const { appearance } = useAppPreferences();
  const colors = preferenceColors(appearance);

  return (
    <View style={styles.botMetric}>
      <Text style={[styles.metricLabel, { color: colors.textDim }]}>{label}</Text>
      <Text style={[styles.botMetricValue, { color: toneColor(tone) }]}>{value}</Text>
    </View>
  );
}

function TradeActionSheet({
  activeAsset,
  amountPreset,
  amountUnit,
  amountValue,
  bot,
  executionExpanded,
  exchangeSummary,
  mode,
  overview,
  preview,
  previewError,
  previewLoading,
  stale,
  onAmountPresetChange,
  onAmountUnitChange,
  onAmountValueChange,
  onAskFinn,
  onExecutionExpandedChange,
  onModeChange,
  onPreview,
}: {
  activeAsset: string;
  amountPreset: number;
  amountUnit: AmountUnit;
  amountValue: string;
  bot?: PortfolioBot;
  executionExpanded: boolean;
  exchangeSummary: ExchangeSummary;
  mode: TradeMode;
  overview?: MobileOverviewResponse['watchlist'][number];
  preview: OrderPreviewResponse | null;
  previewError: string;
  previewLoading: boolean;
  stale: boolean;
  onAmountPresetChange: (value: number) => void;
  onAmountUnitChange: (value: AmountUnit) => void;
  onAmountValueChange: (value: string) => void;
  onAskFinn: () => void;
  onExecutionExpandedChange: (value: boolean) => void;
  onModeChange: (value: TradeMode) => void;
  onPreview: () => void;
}) {
  const { appearance } = useAppPreferences();
  const colors = preferenceColors(appearance);

  const actionItems: Array<{ key: TradeMode; label: string; body: string }> = [
    { key: 'buy', label: 'Buy', body: 'Maak een gecontroleerde koopdraft.' },
    { key: 'sell', label: 'Sell', body: 'Controleer exit, positie en risico.' },
    { key: 'dca', label: 'DCA', body: 'Past bij botbudget en cadence.' },
    { key: 'bot', label: 'Bot Action', body: 'Laat FINN de botactie wegen.' },
  ];
  const setupScore = clampScore(overview?.setup_score);
  const conviction = Math.round(
    (clampScore(overview?.macro_score) +
      clampScore(overview?.market_score) +
      clampScore(overview?.technical_score) +
      setupScore) /
      4,
  );
  const exposurePct = bot?.budgetTotal ? Math.min(100, (bot.positionValue / bot.budgetTotal) * 100) : 0;
  const riskTone: StatusTone = stale || exposurePct > 75 ? 'warning' : setupScore >= 55 && conviction >= 55 ? 'success' : 'neutral';
  const riskLabel = stale ? 'Data stale' : exposurePct > 75 ? 'Exposure hoog' : setupScore >= 55 ? 'Guardrails ok' : 'Setup zwak';
  const livePrice = Number.isFinite(overview?.price ?? NaN) ? Number(overview?.price) : 0;
  const estimatedBtc =
    amountUnit === 'BTC'
      ? Number(amountValue.replace(',', '.')) || 0
      : livePrice > 0
        ? (Number(amountValue.replace(',', '.')) || 0) / livePrice
        : 0;

  return (
    <View style={styles.tradeSheet}>
      <View style={styles.tradeHeroCompact}>
        <View style={styles.tradeHeroCopy}>
          <Text style={styles.kicker}>Execution workspace</Text>
          <Text style={[styles.tradeHeroTitle, { color: colors.text }]}>{bot?.name || `${activeAsset} trade flow`}</Text>
          <Text style={[styles.tradeHeroMeta, { color: colors.textDim }]}>
            {activeAsset} · {bot?.isLive ? 'Live' : 'Paper'} · FINN review before execution
          </Text>
        </View>
        <StatusChip label={riskLabel} tone={riskTone} />
      </View>

      <View style={styles.tradeOverviewGrid}>
        <TradeContextStat label="Setup" value={setupScore > 0 ? `${setupScore}` : 'n/a'} tone={setupScore >= 60 ? 'success' : 'warning'} />
        <TradeContextStat label="Conviction" value={`${conviction}`} tone={conviction >= 70 ? 'success' : conviction >= 50 ? 'warning' : 'danger'} />
        <TradeContextStat label="Exposure" value={`${Math.round(exposurePct)}%`} tone={exposurePct > 75 ? 'warning' : 'accent'} />
        <TradeContextStat label="Max order" value={formatEUR(bot?.budgetMaxOrder ?? 0)} tone="neutral" />
      </View>

      <View style={styles.tradeStep}>
        <Text style={styles.tradeStepLabel}>Stap 1</Text>
        <Text style={[styles.tradeStepTitle, { color: colors.text }]}>Kies de actie</Text>
        <View style={styles.tradeModeGrid}>
          {actionItems.map((item) => {
            const active = mode === item.key;
            return (
              <Pressable
                accessibilityRole="button"
                key={item.key}
                onPress={async () => {
                  await triggerHaptic('selection');
                  onModeChange(item.key);
                  onExecutionExpandedChange(false);
                }}
                style={[styles.tradeModeTile, { borderColor: colors.border }, active && styles.tradeModeTileActive]}
              >
                <Text style={[styles.tradeModeLabel, { color: colors.textDim }, active && styles.tradeModeLabelActive]}>{item.label}</Text>
                <Text style={[styles.tradeModeBody, { color: colors.textMuted }]}>{item.body}</Text>
              </Pressable>
            );
          })}
        </View>
      </View>

      <View style={styles.tradeStep}>
        <View style={styles.tradeStepHeader}>
          <View>
            <Text style={styles.tradeStepLabel}>Stap 2</Text>
            <Text style={[styles.tradeStepTitle, { color: colors.text }]}>FINN context</Text>
          </View>
          <StatusChip label={riskLabel} tone={riskTone} />
        </View>
        <View style={styles.tradeContextGrid}>
          <TradeContextStat label="Risk" value={riskLabel} tone={riskTone} />
          <TradeContextStat label="Available EUR" value={formatEUR(exchangeSummary.freeEur)} tone="neutral" />
          <TradeContextStat label="Environment" value={bot?.isLive ? 'Live' : 'Paper'} tone={bot?.isLive ? 'danger' : 'accent'} />
          <TradeContextStat label="Asset" value={activeAsset} tone="accent" />
        </View>
        <View style={[styles.tradeWarning, { borderColor: colors.border }, stale && styles.tradeWarningStrong]}>
          <Text style={[styles.tradeWarningTitle, { color: colors.text }]}>{stale ? 'Ververs voordat je bevestigt.' : 'Geen one-tap execution.'}</Text>
          <Text style={[styles.tradeWarningBody, { color: colors.textMuted }]}>
            Deze sheet maakt alleen een gecontroleerde trade-draft. FINN checkt exposure, setup en botcontext voordat je iets uitvoert.
          </Text>
        </View>
      </View>

      <View style={styles.tradeStep}>
        <Pressable
          accessibilityRole="button"
          onPress={async () => {
            await triggerHaptic('selection');
            onExecutionExpandedChange(!executionExpanded);
          }}
          style={styles.executionToggle}
        >
          <View>
            <Text style={styles.tradeStepLabel}>Stap 3</Text>
            <Text style={[styles.tradeStepTitle, { color: colors.text }]}>{executionExpanded ? 'Execution draft' : 'Execution uitklappen'}</Text>
          </View>
          <Text style={[styles.executionToggleIcon, { color: colors.text }]}>{executionExpanded ? '-' : '+'}</Text>
        </Pressable>

        {executionExpanded ? (
          <View style={styles.executionPanel}>
            <View style={[styles.sideSwitch, { backgroundColor: colors.surfaceMuted }]}>
              {(['buy', 'sell'] as const).map((side) => {
                const active = mode === side;
                return (
                  <Pressable
                    key={side}
                    onPress={async () => {
                      await triggerHaptic('selection');
                      onModeChange(side);
                    }}
                    style={[styles.sideButton, active && (side === 'buy' ? styles.sideButtonBuy : styles.sideButtonSell)]}
                  >
                    <Text style={[styles.sideButtonText, { color: colors.textDim }, active && styles.sideButtonTextActive]}>
                      {side === 'buy' ? 'Kopen' : 'Verkopen'}
                    </Text>
                  </Pressable>
                );
              })}
            </View>

            <View style={styles.executionField}>
              <View style={styles.executionFieldHeader}>
                <Text style={[styles.metricLabel, { color: colors.textDim }]}>Order prijs</Text>
                <Text style={[styles.executionLive, { color: colors.textDim }]}>{livePrice > 0 ? `Live: ${formatEUR(livePrice)}` : 'Live: n/a'}</Text>
              </View>
              <View style={[styles.readOnlyInput, { backgroundColor: colors.backgroundSoft, borderColor: colors.border }]}>
                <Text style={[styles.readOnlyInputText, { color: colors.text }]}>{livePrice > 0 ? livePrice.toFixed(2).replace('.', ',') : '-'}</Text>
              </View>
            </View>

            <View style={styles.executionField}>
              <View style={styles.executionFieldHeader}>
                <Text style={[styles.metricLabel, { color: colors.textDim }]}>Aantal</Text>
                <View style={styles.unitSwitch}>
                  {(['EUR', 'BTC'] as const).map((unit) => (
                    <Pressable
                      key={unit}
                      onPress={async () => {
                        await triggerHaptic('selection');
                        onAmountUnitChange(unit);
                      }}
                      style={[styles.unitButton, { backgroundColor: colors.surfaceMuted }, amountUnit === unit && styles.unitButtonActive]}
                    >
                      <Text style={[styles.unitButtonText, { color: colors.textDim }, amountUnit === unit && styles.unitButtonTextActive]}>{unit}</Text>
                    </Pressable>
                  ))}
                </View>
              </View>
              <TextInput
                keyboardType="decimal-pad"
                onChangeText={onAmountValueChange}
                placeholder={amountUnit === 'EUR' ? 'Bedrag in EUR' : 'Aantal BTC'}
                placeholderTextColor={colors.textDim}
                style={[styles.amountInput, { backgroundColor: colors.surface, borderColor: colors.border, color: colors.text }]}
                value={amountValue}
              />
              <View style={styles.presetRail}>
                {[0, 25, 50, 75, 100].map((preset) => (
                  <Pressable
                    key={preset}
                    onPress={async () => {
                      await triggerHaptic('selection');
                      onAmountPresetChange(preset);
                    }}
                    style={styles.presetItem}
                  >
                    <View style={[styles.presetDot, { backgroundColor: colors.border }, amountPreset === preset && styles.presetDotActive]} />
                    <Text style={[styles.presetLabel, { color: colors.textDim }]}>{preset}%</Text>
                  </Pressable>
                ))}
              </View>
            </View>

            <View style={[styles.expectationBox, { borderColor: colors.border }]}>
              <SmallStat label="Verwacht" value={`${estimatedBtc.toFixed(6)} BTC`} />
              <SmallStat label="Beschikbaar" value={formatEUR(exchangeSummary.freeEur)} />
              <SmallStat label="Max order" value={formatEUR(bot?.budgetMaxOrder ?? 0)} />
            </View>

            {preview ? <OrderPreviewCard preview={preview} /> : null}
            {previewError ? (
              <View style={[styles.tradeWarning, styles.tradeWarningStrong]}>
                <Text style={[styles.tradeWarningTitle, { color: colors.text }]}>Preview niet beschikbaar</Text>
                <Text style={[styles.tradeWarningBody, { color: colors.textMuted }]}>{previewError}</Text>
              </View>
            ) : null}
          </View>
        ) : null}
      </View>

      <Pressable
        accessibilityRole="button"
        onPress={executionExpanded ? onPreview : onAskFinn}
        style={[styles.tradePrimaryButton, previewLoading && styles.tradePrimaryButtonDisabled]}
      >
        <Text style={styles.tradePrimaryText}>
          {previewLoading
            ? 'Preview laden...'
            : executionExpanded
              ? 'Maak veilige backend preview'
              : 'Vraag FINN om trade check'}
        </Text>
      </Pressable>
      {preview ? (
        <Pressable accessibilityRole="button" onPress={onAskFinn} style={[styles.tradeSecondaryButton, { borderColor: colors.borderStrong }]}>
          <Text style={[styles.tradeSecondaryText, { color: colors.textSoft }]}>Vraag FINN om uitleg</Text>
        </Pressable>
      ) : null}
    </View>
  );
}

function OrderPreviewCard({ preview }: { preview: OrderPreviewResponse }) {
  const { appearance } = useAppPreferences();
  const colors = preferenceColors(appearance);
  const guardrails = isRecord(preview.guardrails) ? preview.guardrails : undefined;
  const allowed = readBool(guardrails, ['allowed'], false);
  const reason = readString(guardrails, ['reason'], allowed ? 'Guardrails akkoord' : 'Preview geblokkeerd');
  const warnings = Array.isArray(guardrails?.warnings) ? guardrails.warnings.map(String) : [];

  return (
    <View style={[styles.previewCard, { borderColor: colors.border }, allowed ? styles.previewCardAllowed : styles.previewCardBlocked]}>
      <View style={styles.tradeStepHeader}>
        <View>
          <Text style={[styles.tradeStepLabel, { color: colors.textDim }]}>Backend preview</Text>
          <Text style={[styles.previewTitle, { color: colors.text }]}>{allowed ? 'Conceptorder is mogelijk' : 'Niet uitvoeren'}</Text>
        </View>
        <StatusChip label={preview.is_live ? 'Live' : 'Paper'} tone={preview.is_live ? 'warning' : 'accent'} />
      </View>
      <View style={styles.previewGrid}>
        <SmallStat label="Side" value={preview.side.toUpperCase()} />
        <SmallStat label="Prijs" value={formatEUR(preview.price)} />
        <SmallStat label="Netto" value={formatEUR(preview.net_eur)} />
        <SmallStat label="Fee" value={formatEUR(preview.fee_eur)} />
        <SmallStat label="Aantal" value={`${preview.quantity.toFixed(8)} ${preview.symbol}`} />
      </View>
      <View style={[styles.previewReason, { borderTopColor: colors.border }]}>
        <Text style={[styles.tradeWarningTitle, { color: colors.text }]}>{reason}</Text>
        <Text style={[styles.tradeWarningBody, { color: colors.textMuted }]}>
          {warnings.length > 0
            ? `Warnings: ${warnings.join(', ')}`
            : 'Dit is alleen een preview. Er is nog niets geplaatst of opgeslagen.'}
        </Text>
      </View>
    </View>
  );
}

function TradeContextStat({ label, tone, value }: { label: string; tone: StatusTone; value: string }) {
  const { appearance } = useAppPreferences();
  const colors = preferenceColors(appearance);

  return (
    <View style={[styles.tradeContextTile, { borderColor: colors.border }]}>
      <Text style={[styles.metricLabel, { color: colors.textDim }]}>{label}</Text>
      <Text style={[styles.tradeContextValue, { color: toneColor(tone) }]}>{value}</Text>
    </View>
  );
}

function buildTradePrefill({
  activeAsset,
  amountUnit,
  amountValue,
  bot,
  exchangeSummary,
  mode,
  overview,
}: {
  activeAsset: string;
  amountUnit: AmountUnit;
  amountValue: string;
  bot?: PortfolioBot;
  exchangeSummary: ExchangeSummary;
  mode: TradeMode;
  overview?: MobileOverviewResponse['watchlist'][number];
}) {
  const scoreLine = overview
    ? `macro ${clampScore(overview.macro_score)}, market ${clampScore(overview.market_score)}, technical ${clampScore(overview.technical_score)}, setup ${clampScore(overview.setup_score)}`
    : 'geen scoredata beschikbaar';
  const requestedAmount = amountValue.trim() ? `${amountValue.trim()} ${amountUnit}` : 'nog geen bedrag gekozen';

  return [
    `Check deze mobiele trade-draft voor ${activeAsset}.`,
    `Actie: ${mode.toUpperCase()}. Bedrag: ${requestedAmount}.`,
    `Botcontext: ${bot?.name ?? 'geen actieve bot'} (${bot?.isLive ? 'live' : 'paper/unknown'}).`,
    `Beschikbaar EUR: ${formatEUR(exchangeSummary.freeEur)}. Max order: ${formatEUR(bot?.budgetMaxOrder ?? 0)}.`,
    `Scores: ${scoreLine}.`,
    'Geef eerst conclusie, risico, guardrail-status en veilige volgende stap. Maak niets automatisch aan zonder bevestiging.',
  ].join('\n');
}

function buildOrderPreviewPayload({
  activeAsset,
  amountUnit,
  amountValue,
  bot,
  mode,
  overview,
}: {
  activeAsset: string;
  amountUnit: AmountUnit;
  amountValue: string;
  bot: PortfolioBot;
  mode: TradeMode;
  overview?: MobileOverviewResponse['watchlist'][number];
}) {
  const numericAmount = Number(amountValue.replace(',', '.'));
  if (!Number.isFinite(numericAmount) || numericAmount <= 0) return null;

  const price = Number.isFinite(overview?.price ?? NaN) ? Number(overview?.price) : 0;
  const side: 'buy' | 'sell' = mode === 'sell' ? 'sell' : 'buy';
  const quantity = amountUnit === 'BTC' ? numericAmount : price > 0 ? numericAmount / price : 0;
  const valueEur = amountUnit === 'EUR' ? numericAmount : numericAmount * price;

  return {
    bot_id: bot.id,
    price,
    quantity,
    side,
    symbol: activeAsset,
    value_eur: Number.isFinite(valueEur) ? valueEur : undefined,
  };
}

function mapBots(portfolios: UnknownRecord[], configs: UnknownRecord[]): PortfolioBot[] {
  const configById = new Map<number, UnknownRecord>();
  configs.forEach((config) => {
    const id = readNumber(config, ['id', 'bot_id'], NaN);
    if (Number.isFinite(id)) configById.set(id, config);
  });

  const source = portfolios.length > 0 ? portfolios : configs;
  return source
    .map((portfolio) => {
      const id = readNumber(portfolio, ['bot_id', 'id'], 0);
      const config = configById.get(id) ?? portfolio;
      const stats = record(portfolio.stats);
      const budget = record(portfolio.budget);
      const symbol = readString(portfolio, ['symbol'], readString(config, ['symbol', 'asset'], 'BTC'));
      const invested = Math.abs(
        readNumber(stats, ['net_executed_cash_delta_eur', 'invested_eur', 'invested'], readNumber(portfolio, ['invested_eur'], 0)),
      );
      const positionValue = readNumber(stats, ['position_value_eur', 'value_eur'], readNumber(portfolio, ['position_value_eur', 'value_eur'], invested));
      const budgetTotal = readNumber(budget, ['total_eur'], readNumber(config, ['budget_total_eur', 'budget_total'], 0));

      return {
        available: readNumber(stats, ['available_eur'], Math.max(budgetTotal - invested, 0)),
        budgetDailyLimit: readNumber(budget, ['daily_limit_eur'], readNumber(config, ['budget_daily_limit_eur'], 0)),
        budgetMaxOrder: readNumber(budget, ['max_order_eur'], readNumber(config, ['budget_max_order_eur'], 0)),
        budgetTotal,
        id,
        invested,
        isActive: readBool(portfolio, ['is_active'], readBool(config, ['is_active'], false)),
        isLive: readBool(portfolio, ['is_live'], readBool(config, ['is_live'], false)),
        mode: readString(portfolio, ['mode'], readString(config, ['mode'], 'manual-link')),
        name: readString(portfolio, ['name'], readString(config, ['name', 'bot_name'], `Bot ${id || ''}`.trim())),
        netQty: readNumber(stats, ['net_qty', 'qty'], readNumber(portfolio, ['qty', 'btc_qty'], 0)),
        positionValue,
        riskProfile: readString(portfolio, ['risk_profile'], readString(config, ['risk_profile'], 'standard')),
        strategy: readString(config, ['strategy_name', 'strategy', 'description'], readString(portfolio, ['strategy_name'], 'strategie')),
        symbol,
        timeframe: readString(config, ['timeframe', 'frequency'], readString(portfolio, ['timeframe'], '1W')).toUpperCase(),
        todaySpent: readNumber(stats, ['today_spent_eur', 'today_executed_eur'], 0),
      };
    })
    .filter((bot) => bot.id > 0 || bot.name !== 'Bot');
}

function mapOverviewBots(overview?: MobileOverviewResponse): PortfolioBot[] {
  if (!overview) return [];

  return overview.active_bots.map((bot) => ({
    available: 0,
    budgetDailyLimit: 0,
    budgetMaxOrder: 0,
    budgetTotal: 0,
    id: bot.bot_id,
    invested: bot.invested_eur ?? 0,
    isActive: bot.is_active,
    isLive: bot.is_live,
    mode: bot.is_live ? 'live' : 'paper',
    name: bot.name,
    netQty: 0,
    positionValue: bot.position_value_eur ?? bot.invested_eur ?? 0,
    riskProfile: 'standard',
    strategy: 'strategy',
    symbol: bot.symbol,
    timeframe: '1D',
    todaySpent: 0,
  }));
}

function mergePortfolioBots(primary: PortfolioBot[], fallback: PortfolioBot[]) {
  if (primary.length === 0) return fallback;

  const fallbackById = new Map<number, PortfolioBot>();
  fallback.forEach((bot) => fallbackById.set(bot.id, bot));

  return primary.map((bot) => {
    const overviewBot = fallbackById.get(bot.id);
    if (!overviewBot) return bot;

    return {
      ...overviewBot,
      ...bot,
      invested: bot.invested || overviewBot.invested,
      isActive: bot.isActive || overviewBot.isActive,
      isLive: bot.isLive || overviewBot.isLive,
      name: bot.name || overviewBot.name,
      positionValue: bot.positionValue || overviewBot.positionValue,
      symbol: bot.symbol || overviewBot.symbol,
    };
  });
}

function aggregateBots(
  bots: PortfolioBot[],
  overviewPortfolio?: MobileOverviewResponse['portfolio'],
) {
  const totalBudget = sum(bots, (bot) => bot.budgetTotal);
  const dailyLimit = sum(bots, (bot) => bot.budgetDailyLimit);
  const maxOrder = sum(bots, (bot) => bot.budgetMaxOrder);
  const invested =
    overviewPortfolio?.total_invested_eur ??
    sum(bots, (bot) => bot.invested);
  const positionValue =
    overviewPortfolio?.total_balance_eur ??
    sum(bots, (bot) => bot.positionValue);
  const todaySpent = sum(bots, (bot) => bot.todaySpent);
  const pnl = positionValue - invested;
  const pnlPct = overviewPortfolio?.total_profit_pct ?? (invested > 0 ? (pnl / invested) * 100 : 0);

  const rowsBySymbol = bots.reduce<Record<string, { invested: number; netQty: number; positionValue: number; symbol: string }>>(
    (acc, bot) => {
      const symbol = bot.symbol || 'BTC';
      acc[symbol] = acc[symbol] ?? { invested: 0, netQty: 0, positionValue: 0, symbol };
      acc[symbol].invested += bot.invested;
      acc[symbol].netQty += bot.netQty;
      acc[symbol].positionValue += bot.positionValue;
      return acc;
    },
    {},
  );

  const assetRows = Object.values(rowsBySymbol)
    .map((row) => {
      const rowPnl = row.positionValue - row.invested;
      return {
        ...row,
        pnl: rowPnl,
        pnlPct: row.invested > 0 ? (rowPnl / row.invested) * 100 : 0,
      };
    })
    .sort((a, b) => b.positionValue - a.positionValue);

  return {
    assetRows,
    dailyLimit,
    invested,
    maxOrder,
    pnl,
    pnlPct,
    positionValue,
    todaySpent,
    totalBudget,
  };
}

function summarizeExchange(balances: UnknownRecord[]): ExchangeSummary {
  return balances.reduce<ExchangeSummary>(
    (summary, balance) => {
      const free = record(balance.free);
      const exchange = readString(balance, ['exchange', 'name'], '');
      const totalEur = readNumber(balance, ['total_eur', 'value_eur'], 0);
      const freeEur = readNumber(free, ['EUR', 'eur'], 0);

      return {
        count: summary.count + 1,
        freeEur: summary.freeEur + freeEur,
        names: exchange ? [...summary.names, exchange.toUpperCase()] : summary.names,
        totalEur: summary.totalEur + totalEur,
      };
    },
    { count: 0, freeEur: 0, names: [] as string[], totalEur: 0 },
  );
}

function normalizeHistory(history: UnknownRecord[]) {
  return history;
}

function getPerformance(history: UnknownRecord[], metric: MetricKey, aggregate: ReturnType<typeof aggregateBots>) {
  const first = readNumber(history[0], [metric], 0);
  const rawLast = readNumber(history[history.length - 1], [metric], NaN);
  const last = Number.isFinite(rawLast)
    ? rawLast
    : metric === 'equity'
      ? aggregate.positionValue
      : metric === 'invested'
        ? aggregate.invested
        : 0;
  const absolute = last - first;
  const percent = Math.abs(first) > 1 ? (absolute / first) * 100 : null;
  return { delta: { absolute, percent }, last };
}

function asArray(value: unknown): UnknownRecord[] {
  if (Array.isArray(value)) return value.filter(isRecord);
  if (isRecord(value)) return [value];
  return [];
}

function isRecord(value: unknown): value is UnknownRecord {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function record(value: unknown): UnknownRecord | undefined {
  return isRecord(value) ? value : undefined;
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

function readBool(source: UnknownRecord | undefined, keys: string[], fallback = false) {
  for (const key of keys) {
    const value = source?.[key];
    if (typeof value === 'boolean') return value;
    if (typeof value === 'number') return value !== 0;
    if (typeof value === 'string') return ['true', '1', 'yes', 'live'].includes(value.toLowerCase());
  }
  return fallback;
}

function sum<T>(items: T[], getter: (item: T) => number) {
  return items.reduce((total, item) => total + (Number(getter(item)) || 0), 0);
}

function clampScore(value: unknown) {
  const score = Number(value);
  if (!Number.isFinite(score)) return 0;
  return Math.max(0, Math.min(100, Math.round(score)));
}

function colorForScore(score: number) {
  if (score >= 70) return theme.colors.success;
  if (score >= 50) return theme.colors.warning;
  return theme.colors.danger;
}

function toneColor(tone: StatusTone) {
  if (tone === 'success') return theme.colors.success;
  if (tone === 'warning') return theme.colors.warning;
  if (tone === 'danger') return theme.colors.danger;
  if (tone === 'accent') return theme.colors.accent;
  return theme.colors.textDim;
}

function formatEUR(value: number) {
  return new Intl.NumberFormat('nl-NL', {
    currency: 'EUR',
    maximumFractionDigits: Math.abs(value) >= 100 ? 0 : 2,
    style: 'currency',
  }).format(Number.isFinite(value) ? value : 0);
}

function formatPercent(value: number) {
  return `${value >= 0 ? '+' : ''}${value.toFixed(1)}%`;
}

function formatMetric(value: number, metric: MetricKey) {
  if (metric === 'btc_qty') return `${(Number.isFinite(value) ? value : 0).toFixed(6)} BTC`;
  return formatEUR(value);
}

function portfolioUpdatedAt(values: string[]) {
  return values.find(Boolean) ?? new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
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
  flexText: {
    flex: 1,
  },
  analysisMetaCard: {
    borderRadius: 18,
    borderWidth: 1,
    flex: 1,
    gap: 4,
    paddingHorizontal: theme.spacing.md,
    paddingVertical: theme.spacing.md,
  },
  analysisMetaLabel: {
    color: theme.colors.textDim,
    fontSize: 10,
    fontWeight: '800',
    letterSpacing: 0.6,
    textTransform: 'uppercase',
  },
  analysisMetaRow: {
    flexDirection: 'row',
    gap: theme.spacing.sm,
    marginTop: theme.spacing.md,
  },
  analysisMetaValue: {
    fontSize: 14,
    fontWeight: '800',
    lineHeight: 19,
  },
  bodyText: {
    fontSize: 14,
    fontWeight: '600',
    lineHeight: 21,
    marginTop: theme.spacing.sm,
  },
  cardTitle: {
    fontSize: theme.typography.cardTitle,
    fontWeight: '900',
    marginTop: 4,
  },
  portfolioSection: {
    paddingHorizontal: theme.spacing.lg,
    paddingVertical: theme.spacing.md,
  },
  allocationCard: {
    borderRadius: 24,
    borderWidth: 1,
    marginTop: theme.spacing.md,
    padding: theme.spacing.lg,
  },
  allocationLabel: {
    fontSize: 14,
    fontWeight: '700',
    lineHeight: 20,
  },
  allocationRow: {
    alignItems: 'center',
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginTop: theme.spacing.xs,
  },
  allocationValue: {
    fontSize: 15,
    fontWeight: '700',
    lineHeight: 20,
  },
  availableRow: {
    alignItems: 'center',
    borderBottomWidth: 1,
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginTop: theme.spacing.sm,
    paddingBottom: theme.spacing.md,
  },
  availableLabel: {
    fontSize: 13,
    fontWeight: '700',
    lineHeight: 18,
  },
  availableValue: {
    fontSize: 16,
    fontWeight: '800',
    lineHeight: 20,
  },
  allocationMetrics: {
    flexDirection: 'row',
    gap: theme.spacing.md,
    marginTop: theme.spacing.lg,
  },
  allocationMetric: {
    flex: 1,
    minWidth: 90,
  },
  allocationMetricLabel: {
    fontSize: 10,
    fontWeight: '900',
    letterSpacing: 1.1,
    textTransform: 'uppercase',
  },
  allocationMetricValue: {
    fontSize: 15,
    fontWeight: '800',
    lineHeight: 20,
    marginTop: 4,
  },
  portfolioMetricGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: theme.spacing.sm,
    marginTop: theme.spacing.lg,
  },
  portfolioMetricCard: {
    borderRadius: 22,
    borderWidth: 1,
    minHeight: 108,
    paddingHorizontal: theme.spacing.md,
    paddingVertical: theme.spacing.md,
    width: '48.5%',
  },
  portfolioMetricLabel: {
    fontSize: 10,
    fontWeight: '900',
    letterSpacing: 1.1,
    textTransform: 'uppercase',
  },
  portfolioMetricValue: {
    fontSize: 22,
    fontWeight: '900',
    letterSpacing: -0.8,
    lineHeight: 28,
    marginTop: theme.spacing.sm,
  },
  breakdownSection: {
    marginTop: theme.spacing.lg,
  },
  breakdownList: {
    marginTop: theme.spacing.sm,
  },
  breakdownIdentity: {
    alignItems: 'center',
    flexDirection: 'row',
    gap: theme.spacing.sm,
  },
  breakdownDot: {
    borderRadius: theme.radius.pill,
    height: 14,
    width: 14,
  },
  breakdownRow: {
    alignItems: 'center',
    borderBottomWidth: 1,
    flexDirection: 'row',
    justifyContent: 'space-between',
    paddingVertical: theme.spacing.md,
  },
  breakdownRowLast: {
    borderBottomWidth: 0,
    paddingBottom: theme.spacing.xs,
  },
  breakdownSymbol: {
    fontSize: 16,
    fontWeight: '900',
    lineHeight: 21,
  },
  breakdownQty: {
    fontSize: 13,
    fontWeight: '600',
    lineHeight: 18,
    marginTop: 4,
  },
  breakdownValues: {
    alignItems: 'flex-end',
  },
  breakdownPrice: {
    fontSize: 18,
    fontWeight: '900',
    lineHeight: 22,
  },
  breakdownPnl: {
    fontSize: 13,
    fontWeight: '700',
    lineHeight: 18,
    marginTop: 4,
  },
  inlineTradeButton: {
    alignItems: 'center',
    borderRadius: theme.radius.pill,
    borderWidth: 0.5,
    flexDirection: 'row',
    gap: theme.spacing.sm,
    justifyContent: 'center',
    marginHorizontal: theme.spacing.lg,
    marginVertical: theme.spacing.sm,
    paddingVertical: 10,
  },
  inlineTradeButtonText: {
    fontSize: 13,
    fontWeight: '700',
  },
  botRow: {
    borderBottomWidth: 0.5,
    paddingVertical: theme.spacing.md,
    paddingHorizontal: theme.spacing.lg,
    gap: theme.spacing.md,
  },
  amountInput: {
    backgroundColor: theme.colors.surfaceMuted,
    borderColor: theme.colors.borderStrong,
    borderRadius: theme.radius.md,
    borderWidth: 1,
    color: theme.colors.text,
    fontSize: 26,
    fontWeight: '900',
    minHeight: 72,
    paddingHorizontal: theme.spacing.lg,
  },
  tradePrimaryButton: {
    alignItems: 'center',
    backgroundColor: theme.colors.accent,
    borderRadius: theme.radius.md,
    justifyContent: 'center',
    minHeight: 58,
    paddingHorizontal: theme.spacing.lg,
  },
  tradePrimaryButtonDisabled: {
    opacity: 0.72,
  },
  tradeHeroCompact: {
    alignItems: 'flex-start',
    flexDirection: 'row',
    gap: theme.spacing.md,
    justifyContent: 'space-between',
  },
  tradeOverviewGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: theme.spacing.sm,
    marginTop: theme.spacing.md,
  },
  tradePrimaryText: {
    color: theme.colors.white,
    fontSize: theme.typography.small,
    fontWeight: '900',
    letterSpacing: 1.2,
    textAlign: 'center',
    textTransform: 'uppercase',
  },
  tradeSecondaryButton: {
    alignItems: 'center',
    backgroundColor: theme.colors.surfaceMuted,
    borderColor: theme.colors.borderStrong,
    borderRadius: theme.radius.md,
    borderWidth: 1,
    justifyContent: 'center',
    minHeight: 52,
    paddingHorizontal: theme.spacing.lg,
  },
  tradeSecondaryText: {
    color: theme.colors.textMuted,
    fontSize: theme.typography.small,
    fontWeight: '900',
    letterSpacing: 1.1,
    textTransform: 'uppercase',
  },
  activeBotCount: {
    color: theme.colors.text,
    fontSize: 28,
    fontWeight: '900',
    marginTop: 4,
  },
  activeBotTile: {
    alignSelf: 'flex-start',
    backgroundColor: theme.colors.surfaceMuted,
    borderColor: theme.colors.border,
    borderRadius: theme.radius.md,
    borderWidth: 1,
    marginTop: theme.spacing.md,
    minWidth: 126,
    padding: theme.spacing.md,
  },
  workspaceCell: {
    borderRadius: theme.radius.md,
    borderWidth: 0.5,
    gap: 4,
    minHeight: 82,
    paddingHorizontal: theme.spacing.md,
    paddingVertical: theme.spacing.md,
    width: '48.5%',
  },
  workspaceGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: theme.spacing.sm,
  },
  workspaceGridWrap: {
    paddingHorizontal: theme.spacing.lg,
    paddingVertical: theme.spacing.md,
  },
  workspacePanel: {
    borderRadius: theme.radius.lg,
    borderWidth: 0.5,
    marginTop: theme.spacing.md,
    paddingHorizontal: theme.spacing.md,
    paddingVertical: theme.spacing.md,
  },
  workspaceLabel: {
    fontSize: 11,
    fontWeight: '800',
    letterSpacing: 0.5,
    textTransform: 'uppercase',
  },
  contextPanel: {
    borderRadius: 22,
    borderWidth: 1,
    gap: theme.spacing.sm,
    marginTop: theme.spacing.md,
    paddingHorizontal: theme.spacing.md,
    paddingVertical: theme.spacing.md,
  },
  contextTitle: {
    fontSize: 17,
    fontWeight: '900',
    lineHeight: 22,
    marginTop: 2,
  },
  workspaceRow: {
    alignItems: 'center',
    flexDirection: 'row',
    gap: theme.spacing.md,
    justifyContent: 'space-between',
  },
  workspaceRowLabel: {
    flex: 1,
    fontSize: 13,
    fontWeight: '600',
  },
  workspaceRowValue: {
    fontSize: 13,
    fontWeight: '700',
  },
  workspaceValue: {
    fontSize: 15,
    fontWeight: '800',
    lineHeight: 20,
  },
  compactStatCard: {
    borderRadius: theme.radius.md,
    borderWidth: 0.5,
    gap: 4,
    minHeight: 74,
    paddingHorizontal: theme.spacing.md,
    paddingVertical: theme.spacing.md,
    width: '48.5%',
  },
  compactStatLabel: {
    fontSize: 11,
    fontWeight: '800',
    letterSpacing: 0.5,
    textTransform: 'uppercase',
  },
  compactStatsGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: theme.spacing.sm,
    marginTop: theme.spacing.md,
  },
  compactStatValue: {
    fontSize: 14,
    fontWeight: '800',
    lineHeight: 19,
  },
  panelRows: {
    gap: theme.spacing.sm,
    marginTop: theme.spacing.md,
  },
  portfolioHeroWrap: {
    borderRadius: 28,
    borderWidth: 1,
    gap: theme.spacing.sm,
    marginHorizontal: theme.spacing.lg,
    paddingHorizontal: 20,
    paddingVertical: 20,
  },
  assetBreakdown: {
    borderTopColor: theme.colors.border,
    borderTopWidth: 1,
    gap: theme.spacing.sm,
    marginTop: theme.spacing.lg,
    paddingTop: theme.spacing.lg,
  },
  assetPnl: {
    fontSize: theme.typography.small,
    fontWeight: '900',
    marginTop: 2,
  },
  assetQty: {
    color: theme.colors.textDim,
    fontSize: theme.typography.small,
    fontWeight: '800',
    marginTop: 2,
  },
  assetRow: {
    alignItems: 'center',
    backgroundColor: theme.colors.backgroundSoft,
    borderColor: theme.colors.border,
    borderRadius: theme.radius.md,
    borderWidth: 1,
    flexDirection: 'row',
    justifyContent: 'space-between',
    padding: theme.spacing.md,
  },
  assetSymbol: {
    color: theme.colors.accent,
    fontSize: theme.typography.body,
    fontWeight: '900',
    letterSpacing: 1.5,
  },
  assetValue: {
    color: theme.colors.text,
    fontSize: theme.typography.body,
    fontWeight: '900',
  },
  assetValueBlock: {
    alignItems: 'flex-end',
  },
  bigStat: {
    gap: theme.spacing.xs,
    width: '48%',
  },
  bigStatValue: {
    color: theme.colors.text,
    fontSize: 21,
    fontWeight: '900',
  },
  bigStatsGrid: {
    borderBottomColor: theme.colors.border,
    borderBottomWidth: 1,
    borderTopColor: theme.colors.border,
    borderTopWidth: 1,
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: theme.spacing.lg,
    marginTop: theme.spacing.lg,
    paddingVertical: theme.spacing.lg,
  },
  botChips: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: theme.spacing.sm,
    marginTop: theme.spacing.md,
  },
  botFooter: {
    borderTopColor: theme.colors.border,
    borderTopWidth: 1,
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginTop: theme.spacing.md,
    paddingTop: theme.spacing.md,
  },
  botFooterText: {
    color: theme.colors.textDim,
    fontSize: theme.typography.small,
    fontWeight: '900',
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
  botMeta: {
    color: theme.colors.textDim,
    fontSize: theme.typography.label,
    fontWeight: '900',
    letterSpacing: 1.2,
    marginTop: 6,
    textTransform: 'uppercase',
  },
  botMetric: {
    flex: 1,
    minWidth: '45%',
    paddingVertical: theme.spacing.sm,
  },
  botMetricGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: theme.spacing.md,
    marginTop: theme.spacing.md,
  },
  botMetricValue: {
    fontSize: theme.typography.body,
    fontWeight: '900',
    lineHeight: 21,
    marginTop: 8,
  },
  botName: {
    color: theme.colors.text,
    flex: 1,
    fontSize: 18,
    fontWeight: '700',
    lineHeight: 22,
  },
  botNameRow: {
    alignItems: 'center',
    flexDirection: 'row',
    gap: theme.spacing.sm,
  },
  botTitleBlock: {
    flex: 1,
  },
  botTop: {
    alignItems: 'center',
    flexDirection: 'row',
    gap: theme.spacing.md,
  },
  budgetCard: {
    backgroundColor: theme.colors.backgroundSoft,
    borderColor: theme.colors.border,
    borderRadius: theme.radius.lg,
    borderWidth: 1,
    marginTop: theme.spacing.lg,
    padding: theme.spacing.lg,
  },
  budgetLabel: {
    color: theme.colors.textMuted,
    fontSize: theme.typography.small,
    fontWeight: '800',
  },
  budgetLine: {
    alignItems: 'center',
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginTop: theme.spacing.md,
  },
  budgetSub: {
    color: '#93C5FD',
    fontSize: theme.typography.label,
    fontWeight: '900',
    letterSpacing: 1.1,
    marginTop: 3,
    textTransform: 'uppercase',
  },
  budgetValue: {
    color: theme.colors.text,
    fontSize: theme.typography.small,
    fontWeight: '900',
  },
  chartBar: {
    minHeight: 4,
    width: '100%',
  },
  chartBars: {
    alignItems: 'flex-end',
    flexDirection: 'row',
    height: '100%',
    paddingHorizontal: theme.spacing.sm,
  },
  chartBox: {
    backgroundColor: 'transparent',
    height: 220,
    justifyContent: 'center',
    marginTop: theme.spacing.lg,
    overflow: 'hidden',
  },
  chartCanvas: {
    flex: 1,
    width: '100%',
  },
  chartAxisLabels: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginTop: theme.spacing.sm,
    paddingHorizontal: 4,
  },
  chartAxisText: {
    color: theme.colors.textDim,
    fontSize: 9,
    fontWeight: '700',
  },
  chartColumn: {
    alignItems: 'center',
    flex: 1,
    height: '100%',
    justifyContent: 'flex-end',
  },
  chartGridLine: {
    backgroundColor: theme.colors.border,
    height: 1,
    left: theme.spacing.md,
    opacity: 0.8,
    position: 'absolute',
    right: theme.spacing.md,
    top: '55%',
  },
  deltaAbsolute: {
    color: theme.colors.textDim,
    fontSize: theme.typography.small,
    fontWeight: '900',
  },
  deltaBadge: {
    backgroundColor: 'transparent',
    borderRadius: theme.radius.sm,
    borderWidth: 1,
    paddingHorizontal: theme.spacing.sm,
    paddingVertical: theme.spacing.xs,
  },
  deltaRow: {
    alignItems: 'center',
    flexDirection: 'row',
    gap: theme.spacing.sm,
    marginTop: theme.spacing.sm,
  },
  deltaSoftBadge: {
    borderRadius: theme.radius.pill,
    paddingHorizontal: 10,
    paddingVertical: 6,
  },
  deltaSoftText: {
    fontSize: 12,
    fontWeight: '800',
    letterSpacing: 0.2,
  },
  deltaText: {
    fontSize: theme.typography.small,
    fontWeight: '900',
  },
  emptyChartText: {
    color: theme.colors.textDim,
    fontSize: theme.typography.label,
    fontWeight: '900',
    letterSpacing: 1.2,
    textAlign: 'center',
    textTransform: 'uppercase',
  },
  exchangeGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: theme.spacing.md,
    marginTop: theme.spacing.md,
  },
  exchangeNames: {
    color: theme.colors.textDim,
    fontSize: theme.typography.label,
    fontWeight: '900',
    letterSpacing: 1.4,
    marginTop: theme.spacing.md,
    textTransform: 'uppercase',
  },
  exchangePanel: {
    backgroundColor: theme.colors.successSoft,
    borderColor: '#10B98144',
    borderRadius: theme.radius.lg,
    borderWidth: 1,
    marginTop: theme.spacing.lg,
    padding: theme.spacing.lg,
  },
  exchangeSubtitle: {
    color: theme.colors.textMuted,
    fontSize: theme.typography.small,
    fontWeight: '800',
    marginTop: 4,
  },
  filterPills: {
    flexDirection: 'row',
    gap: theme.spacing.sm,
  },
  heroBody: {
    color: theme.colors.textMuted,
    fontSize: theme.typography.body,
    fontWeight: '700',
    lineHeight: 21,
    marginTop: theme.spacing.sm,
  },
  heroContent: {
    flex: 1,
  },
  heroDash: {
    color: theme.colors.accent,
  },
  heroTitle: {
    color: theme.colors.text,
    fontSize: 20,
    fontWeight: '700',
    letterSpacing: 0,
    lineHeight: 24,
    marginTop: 5,
    textTransform: 'uppercase',
  },
  inlineStats: {
    borderTopColor: theme.colors.border,
    borderTopWidth: 1,
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: theme.spacing.md,
    marginTop: theme.spacing.lg,
    paddingTop: theme.spacing.lg,
  },
  kicker: {
    color: theme.colors.accent,
    fontSize: theme.typography.label,
    fontWeight: '900',
    letterSpacing: 2.7,
    textTransform: 'uppercase',
  },
  primaryButton: {
    alignItems: 'center',
    backgroundColor: theme.colors.accent,
    borderRadius: theme.radius.pill,
    justifyContent: 'center',
    marginTop: theme.spacing.md,
    minHeight: 52,
    paddingHorizontal: theme.spacing.lg,
  },
  primaryButtonText: {
    color: '#ffffff',
    fontSize: 13,
    fontWeight: '900',
    letterSpacing: 1.1,
    textTransform: 'uppercase',
  },
  leftRail: {
    backgroundColor: theme.colors.accent,
    borderRadius: theme.radius.pill,
    width: 4,
  },
  metricLabel: {
    color: theme.colors.textDim,
    fontSize: theme.typography.label,
    fontWeight: '900',
    letterSpacing: 1.2,
    textTransform: 'uppercase',
  },
  myBots: {
    gap: theme.spacing.lg,
  },
  myBotsSubtitle: {
    color: theme.colors.textDim,
    fontSize: theme.typography.body,
    fontWeight: '700',
    marginTop: theme.spacing.xs,
  },
  myBotsTitle: {
    color: theme.colors.text,
    fontSize: 18,
    fontWeight: '900',
    lineHeight: 22,
  },
  performanceHeader: {
    alignItems: 'flex-start',
    flexDirection: 'row',
    justifyContent: 'space-between',
  },
  performanceCopy: {
    flex: 1,
    paddingRight: theme.spacing.md,
  },
  heroKicker: {
    fontSize: 11,
    fontWeight: '900',
    letterSpacing: 2.2,
    textTransform: 'uppercase',
  },
  heroValue: {
    fontSize: 34,
    fontWeight: '900',
    letterSpacing: -1.2,
    lineHeight: 40,
    marginTop: theme.spacing.sm,
  },
  rangeRail: {
    paddingLeft: theme.spacing.sm,
  },
  metricRail: {
    marginTop: theme.spacing.md,
    paddingRight: theme.spacing.sm,
  },
  portfolioHeroCard: {
    borderRadius: 28,
    borderWidth: 1,
    marginHorizontal: theme.spacing.lg,
    marginTop: theme.spacing.md,
    padding: theme.spacing.lg,
  },
  performanceTitle: {
    color: theme.colors.textDim,
    fontSize: theme.typography.label,
    fontWeight: '900',
    letterSpacing: 1.8,
    marginTop: theme.spacing.lg,
    textTransform: 'uppercase',
  },
  performanceValue: {
    color: theme.colors.text,
    fontSize: 18,
    fontWeight: '900',
    letterSpacing: 0,
    marginTop: theme.spacing.xs,
  },
  portfolioHero: {
    flexDirection: 'row',
    gap: theme.spacing.md,
  },
  workflowCard: {
    borderRadius: 20,
    borderWidth: 1,
    flexDirection: 'row',
    gap: 12,
    minHeight: 88,
    padding: theme.spacing.md,
    width: 256,
  },
  workflowCopy: {
    flex: 1,
    gap: 4,
    justifyContent: 'center',
  },
  workflowIcon: {
    alignItems: 'center',
    borderRadius: 16,
    height: 52,
    justifyContent: 'center',
    width: 52,
  },
  workflowRail: {
    gap: theme.spacing.sm,
    paddingRight: theme.spacing.lg,
  },
  workflowText: {
    fontSize: 14,
    fontWeight: '600',
    lineHeight: 19,
  },
  workflowTitle: {
    fontSize: 16,
    fontWeight: '900',
    lineHeight: 20,
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
    fontSize: 19,
    fontWeight: '900',
    letterSpacing: -0.6,
    lineHeight: 28,
    marginTop: 4,
  },
  workspaceHeadlineCompact: {
    fontSize: 18,
    lineHeight: 26,
    marginTop: 2,
  },
  workspaceIntroPanel: {
    borderColor: theme.colors.border,
    borderRadius: 28,
    borderWidth: 1,
    gap: theme.spacing.sm,
    marginHorizontal: theme.spacing.lg,
    paddingHorizontal: 20,
    paddingVertical: 20,
  },
  workspaceIntroSubtitle: {
    fontSize: 16,
    fontWeight: '600',
    lineHeight: 24,
  },
  workspaceIntroTitle: {
    fontSize: 18,
    fontWeight: '900',
    lineHeight: 24,
  },
  workspaceLead: {
    fontSize: 15,
    fontWeight: '700',
    marginTop: 6,
  },
  workspaceMutedPanel: {
    borderRadius: 28,
    borderWidth: 1,
    gap: theme.spacing.sm,
    marginHorizontal: theme.spacing.lg,
    paddingHorizontal: 20,
    paddingVertical: 20,
  },
  pressed: {
    opacity: 0.86,
    transform: [{ scale: 0.98 }],
  },
  previewCard: {
    borderRadius: theme.radius.lg,
    borderWidth: 0.5,
    gap: theme.spacing.md,
    padding: theme.spacing.md,
  },
  previewCardAllowed: {
    backgroundColor: theme.colors.successSoft,
    borderColor: '#10B98155',
  },
  previewCardBlocked: {
    backgroundColor: theme.colors.warningSoft,
    borderColor: '#F59E0B55',
  },
  previewGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: theme.spacing.lg,
  },
  previewReason: {
    borderTopColor: theme.colors.border,
    borderTopWidth: 1,
    paddingTop: theme.spacing.md,
  },
  previewTitle: {
    color: theme.colors.text,
    fontSize: theme.typography.cardTitle,
    fontWeight: '900',
    marginTop: 4,
  },
  presetDot: {
    backgroundColor: theme.colors.surfaceElevated,
    borderColor: theme.colors.borderStrong,
    borderRadius: theme.radius.pill,
    borderWidth: 2,
    height: 24,
    width: 24,
  },
  presetDotActive: {
    borderColor: theme.colors.success,
    borderWidth: 3,
  },
  presetItem: {
    alignItems: 'center',
    flex: 1,
    gap: theme.spacing.xs,
  },
  presetLabel: {
    color: theme.colors.textMuted,
    fontSize: theme.typography.small,
    fontWeight: '800',
  },
  presetRail: {
    flexDirection: 'row',
    gap: theme.spacing.xs,
    marginTop: theme.spacing.md,
  },
  progressFill: {
    backgroundColor: theme.colors.warning,
    borderRadius: theme.radius.pill,
    height: '100%',
  },
  progressTrack: {
    backgroundColor: theme.colors.border,
    borderRadius: theme.radius.pill,
    height: 10,
    marginTop: theme.spacing.sm,
    overflow: 'hidden',
  },
  scoreGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: theme.spacing.sm,
    marginTop: theme.spacing.lg,
  },
  scoreLabel: {
    color: theme.colors.textMuted,
    fontSize: theme.typography.label,
    fontWeight: '900',
    letterSpacing: 1,
    textTransform: 'uppercase',
  },
  scoreTile: {
    backgroundColor: theme.colors.surfaceMuted,
    borderColor: theme.colors.border,
    borderRadius: theme.radius.md,
    borderWidth: 1,
    minHeight: 86,
    padding: theme.spacing.md,
    width: '48%',
  },
  scoreTileStrong: {
    backgroundColor: theme.colors.successSoft,
    borderColor: '#10B98144',
  },
  scoreValue: {
    fontSize: 18,
    fontWeight: '900',
    marginTop: theme.spacing.sm,
  },
  screenWrap: {
    backgroundColor: theme.colors.background,
    flex: 1,
  },
  sectionTop: {
    alignItems: 'flex-start',
    flexDirection: 'row',
    justifyContent: 'space-between',
  },
  summaryAction: {
    alignItems: 'center',
    backgroundColor: theme.colors.accent,
    borderRadius: theme.radius.button,
    justifyContent: 'center',
    minHeight: 48,
    marginTop: theme.spacing.md,
  },
  summaryActionText: {
    color: '#ffffff',
    fontSize: 11,
    fontWeight: '900',
    letterSpacing: 0.9,
    textTransform: 'uppercase',
  },
  segment: {
    alignItems: 'center',
    borderRadius: theme.radius.pill,
    flex: 1,
    justifyContent: 'center',
    paddingVertical: 6,
    paddingHorizontal: theme.spacing.sm,
  },
  segmentActive: {
    backgroundColor: theme.colors.surfaceMuted,
  },
  segmentCompact: {
    flex: 0,
    minWidth: 106,
  },
  segmentText: {
    color: theme.colors.textDim,
    fontSize: 11,
    fontWeight: '700',
    letterSpacing: 0.5,
    textTransform: 'uppercase',
  },
  segmentTextActive: {
    color: theme.colors.accent,
  },
  segmented: {
    backgroundColor: 'transparent',
    flexDirection: 'row',
    gap: 4,
    marginTop: theme.spacing.md,
    padding: 2,
  },
  segmentedCompact: {
    alignSelf: 'flex-start',
  },
  smallStat: {
    minWidth: 96,
  },
  smallStatValue: {
    color: theme.colors.text,
    fontSize: theme.typography.cardTitle,
    fontWeight: '900',
    marginTop: 6,
  },
  statusDot: {
    borderRadius: theme.radius.pill,
    height: 10,
    width: 10,
  },
  expectationBox: {
    borderColor: theme.colors.border,
    borderRadius: theme.radius.md,
    borderWidth: 0.5,
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: theme.spacing.lg,
    padding: theme.spacing.md,
  },
  executionField: {
    backgroundColor: theme.colors.backgroundSoft,
    borderColor: theme.colors.border,
    borderRadius: theme.radius.lg,
    borderWidth: 0.5,
    gap: theme.spacing.md,
    padding: theme.spacing.md,
  },
  executionFieldHeader: {
    alignItems: 'center',
    flexDirection: 'row',
    justifyContent: 'space-between',
  },
  executionLive: {
    color: '#93C5FD',
    fontSize: theme.typography.small,
    fontWeight: '900',
  },
  executionPanel: {
    gap: theme.spacing.lg,
    marginTop: theme.spacing.lg,
  },
  executionToggle: {
    alignItems: 'center',
    backgroundColor: theme.colors.backgroundSoft,
    borderColor: theme.colors.border,
    borderRadius: theme.radius.lg,
    borderWidth: 1,
    flexDirection: 'row',
    justifyContent: 'space-between',
    padding: theme.spacing.lg,
  },
  executionToggleIcon: {
    color: theme.colors.textDim,
    fontSize: 30,
    fontWeight: '900',
    lineHeight: 32,
  },
  readOnlyInput: {
    backgroundColor: theme.colors.surfaceMuted,
    borderColor: theme.colors.borderStrong,
    borderRadius: theme.radius.md,
    borderWidth: 1,
    justifyContent: 'center',
    minHeight: 72,
    paddingHorizontal: theme.spacing.lg,
  },
  readOnlyInputText: {
    color: theme.colors.text,
    fontSize: 18,
    fontWeight: '900',
  },
  sideButton: {
    alignItems: 'center',
    borderRadius: theme.radius.md,
    flex: 1,
    justifyContent: 'center',
    minHeight: 58,
  },
  sideButtonBuy: {
    backgroundColor: theme.colors.success,
  },
  sideButtonSell: {
    backgroundColor: theme.colors.danger,
  },
  sideButtonText: {
    color: theme.colors.textDim,
    fontSize: theme.typography.small,
    fontWeight: '900',
    letterSpacing: 1.2,
    textTransform: 'uppercase',
  },
  sideButtonTextActive: {
    color: theme.colors.white,
  },
  sideSwitch: {
    backgroundColor: theme.colors.surfaceMuted,
    borderColor: theme.colors.border,
    borderRadius: theme.radius.lg,
    borderWidth: 1,
    flexDirection: 'row',
    gap: theme.spacing.xs,
    padding: theme.spacing.xs,
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
  tradeContextGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: theme.spacing.sm,
  },
  tradeContextTile: {
    borderColor: theme.colors.border,
    borderRadius: theme.radius.md,
    borderWidth: 1,
    minHeight: 80,
    padding: theme.spacing.md,
    width: '48%',
  },
  tradeContextValue: {
    fontSize: 18,
    fontWeight: '900',
    lineHeight: 22,
    marginTop: theme.spacing.sm,
  },
  tradeFab: {
    alignItems: 'center',
    backgroundColor: theme.colors.black,
    borderColor: theme.colors.borderStrong,
    borderRadius: theme.radius.pill,
    borderWidth: 1,
    bottom: 106,
    flexDirection: 'row',
    gap: theme.spacing.sm,
    minHeight: 58,
    paddingHorizontal: theme.spacing.md,
    position: 'absolute',
    right: theme.spacing.lg,
    ...theme.shadows.sheet,
  },
  tradeFabOrb: {
    color: theme.colors.white,
    fontSize: 15,
    fontWeight: '900',
  },
  tradeFabStatus: {
    backgroundColor: theme.colors.success,
    borderColor: theme.colors.black,
    borderRadius: theme.radius.pill,
    borderWidth: 2,
    height: 16,
    position: 'absolute',
    right: 2,
    top: 0,
    width: 16,
  },
  tradeFabText: {
    color: theme.colors.text,
    fontSize: theme.typography.small,
    fontWeight: '900',
    letterSpacing: 1.2,
    textTransform: 'uppercase',
  },
  tradeHero: {
    alignItems: 'center',
    borderBottomColor: theme.colors.border,
    borderBottomWidth: 1,
    flexDirection: 'row',
    gap: theme.spacing.md,
    paddingBottom: theme.spacing.lg,
  },
  tradeHeroCopy: {
    flex: 1,
  },
  tradeHeroMeta: {
    color: theme.colors.textDim,
    fontSize: theme.typography.label,
    fontWeight: '900',
    letterSpacing: 1.1,
    lineHeight: 16,
    marginTop: 6,
    textTransform: 'uppercase',
  },
  tradeHeroTitle: {
    color: theme.colors.text,
    fontSize: 18,
    fontWeight: '900',
    lineHeight: 22,
    marginTop: 5,
  },
  tradeIcon: {
    alignItems: 'center',
    backgroundColor: theme.colors.surfaceMuted,
    borderColor: theme.colors.border,
    borderRadius: theme.radius.lg,
    borderWidth: 1,
    height: 62,
    justifyContent: 'center',
    width: 62,
  },
  tradeIconText: {
    color: theme.colors.accent,
    fontSize: 18,
    fontWeight: '900',
  },
  tradeModeBody: {
    color: theme.colors.textDim,
    fontSize: 12,
    fontWeight: '800',
    lineHeight: 16,
    marginTop: theme.spacing.xs,
  },
  tradeModeGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: theme.spacing.sm,
  },
  tradeModeLabel: {
    color: theme.colors.textMuted,
    fontSize: theme.typography.small,
    fontWeight: '900',
    letterSpacing: 1.1,
    textTransform: 'uppercase',
  },
  tradeModeLabelActive: {
    color: theme.colors.accent,
  },
  tradeModeTile: {
    borderColor: theme.colors.border,
    borderRadius: theme.radius.md,
    borderWidth: 1,
    minHeight: 96,
    padding: theme.spacing.md,
    width: '48%',
  },
  tradeModeTileActive: {
    backgroundColor: theme.colors.accentSoft,
    borderColor: '#2563EB88',
  },
  tradeSheet: {
    gap: theme.spacing.lg,
  },
  tradeStep: {
    gap: theme.spacing.md,
  },
  tradeStepHeader: {
    alignItems: 'center',
    flexDirection: 'row',
    justifyContent: 'space-between',
  },
  tradeStepLabel: {
    color: theme.colors.accent,
    fontSize: theme.typography.label,
    fontWeight: '900',
    letterSpacing: 1.6,
    textTransform: 'uppercase',
  },
  tradeStepTitle: {
    color: theme.colors.text,
    fontSize: theme.typography.cardTitle,
    fontWeight: '900',
    marginTop: 4,
  },
  tradeWarning: {
    borderColor: theme.colors.border,
    borderRadius: theme.radius.md,
    borderWidth: 1,
    padding: theme.spacing.md,
  },
  tradeWarningBody: {
    color: theme.colors.textMuted,
    fontSize: theme.typography.small,
    fontWeight: '700',
    lineHeight: 20,
    marginTop: theme.spacing.xs,
  },
  tradeWarningStrong: {
    backgroundColor: theme.colors.warningSoft,
    borderColor: '#F59E0B55',
  },
  tradeWarningTitle: {
    color: theme.colors.text,
    fontSize: theme.typography.small,
    fontWeight: '900',
  },
  unitButton: {
    backgroundColor: theme.colors.surfaceMuted,
    paddingHorizontal: theme.spacing.md,
    paddingVertical: theme.spacing.xs,
  },
  unitButtonActive: {
    backgroundColor: theme.colors.accent,
  },
  unitButtonText: {
    color: theme.colors.textDim,
    fontSize: theme.typography.label,
    fontWeight: '900',
  },
  unitButtonTextActive: {
    color: theme.colors.white,
  },
  unitSwitch: {
    borderRadius: theme.radius.sm,
    flexDirection: 'row',
    overflow: 'hidden',
  },
});
