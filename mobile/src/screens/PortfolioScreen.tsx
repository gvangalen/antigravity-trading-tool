import { useCallback, useMemo, useState } from 'react';
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';

import { CardShell } from '../components/cards/CardShell';
import { InsightCard } from '../components/cards/InsightCard';
import { AssetContextHeader } from '../components/layout/AssetContextHeader';
import { LoadingSkeletonCard } from '../components/layout/LoadingSkeletonCard';
import { ScreenContainer } from '../components/layout/ScreenContainer';
import { SectionHeader } from '../components/layout/SectionHeader';
import { StatusChip } from '../components/layout/StatusChip';
import { StatusTone, theme } from '../constants/theme';
import { useApiResource } from '../hooks/useApiResource';
import { MobileOverviewResponse, intelligenceApi, mobileApi } from '../services/tradamindApi';
import { triggerHaptic } from '../utils/haptics';

type UnknownRecord = Record<string, unknown>;
type EnvFilter = 'all' | 'paper' | 'live';
type RangeKey = '1D' | '1W' | '1M' | '1Y' | 'ALL';
type MetricKey = 'equity' | 'cash' | 'btc_value' | 'btc_qty' | 'invested' | 'unrealized_pnl';

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
  const [envFilter, setEnvFilter] = useState<EnvFilter>('all');
  const [range, setRange] = useState<RangeKey>('1W');
  const [metric, setMetric] = useState<MetricKey>('equity');

  const rangeConfig = ranges.find((item) => item.key === range) ?? ranges[1];
  const isLiveFilter = envFilter === 'all' ? undefined : envFilter === 'live';

  const fetchOverview = useCallback(() => mobileApi.overview(), []);
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

  const fetchExchangeBalances = useCallback(async () => asArray(await intelligenceApi.exchangeBalances()), []);
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

  const bots = useMemo(
    () => mapBots(portfoliosResource.data, configsResource.data),
    [configsResource.data, portfoliosResource.data],
  );
  const filteredBots = useMemo(
    () => bots.filter((bot) => envFilter === 'all' || bot.isLive === (envFilter === 'live')),
    [bots, envFilter],
  );
  const aggregate = useMemo(() => aggregateBots(filteredBots), [filteredBots]);
  const exchangeSummary = useMemo(() => summarizeExchange(exchangeResource.data), [exchangeResource.data]);
  const history = useMemo(
    () => normalizeHistory(historyResource.data, aggregate, rangeConfig.limit),
    [aggregate, historyResource.data, rangeConfig.limit],
  );
  const performance = useMemo(() => getPerformance(history, metric, aggregate), [aggregate, history, metric]);
  const activeAsset = overviewResource.data?.watchlist[0]?.symbol ?? filteredBots[0]?.symbol ?? 'BTC';
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

  return (
    <ScreenContainer
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
      <AssetContextHeader asset={activeAsset} context="Portfolio command center" updatedAt={portfolioUpdatedAt([
        overviewResource.updatedAt,
        portfoliosResource.updatedAt,
        historyResource.updatedAt,
      ])} />
      <SectionHeader
        label="System control"
        title="Portfolio"
        description="Geaggregeerd overzicht van budget, posities en botstatus vanuit de backend."
      />

      {loading && bots.length === 0 ? (
        <LoadingSkeletonCard />
      ) : (
        <>
          <EnvironmentAnalytics overview={overviewResource.data} stale={isStale} />

          <PortfolioPerformanceCard
            delta={performance.delta}
            metric={metric}
            onMetricChange={changeMetric}
            onRangeChange={changeRange}
            points={history}
            range={range}
            total={performance.last}
          />

          <BotPortfolioOverviewCard
            aggregate={aggregate}
            bots={filteredBots}
            envFilter={envFilter}
            exchangeSummary={exchangeSummary}
            onEnvFilterChange={changeEnv}
          />

          <MyBotsSection bots={filteredBots} totalBots={bots.length} />
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
  );
}

function EnvironmentAnalytics({ overview, stale }: { overview?: MobileOverviewResponse; stale: boolean }) {
  const asset = overview?.watchlist[0];
  const scores = [
    { label: 'Macro index', value: asset?.macro_score },
    { label: 'Technical index', value: asset?.technical_score },
    { label: 'Market index', value: asset?.market_score },
    { label: 'Setup index', value: asset?.setup_score },
  ];

  return (
    <CardShell>
      <View style={styles.sectionTop}>
        <View>
          <Text style={styles.kicker}>Environment analytics</Text>
          <Text style={styles.cardTitle}>System health & market scopes</Text>
        </View>
        <StatusChip label={stale ? 'Stale' : 'Live'} tone={stale ? 'warning' : 'success'} />
      </View>
      <View style={styles.scoreGrid}>
        {scores.map((score) => {
          const value = clampScore(score.value);
          return (
            <View key={score.label} style={[styles.scoreTile, value >= 70 && styles.scoreTileStrong]}>
              <Text style={styles.scoreLabel}>{score.label}</Text>
              <Text style={[styles.scoreValue, { color: colorForScore(value) }]}>{value}</Text>
            </View>
          );
        })}
      </View>
    </CardShell>
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
  const isDown = delta.absolute < 0;
  const accentColor = metric === 'unrealized_pnl' ? (isDown ? theme.colors.danger : theme.colors.success) : theme.colors.accent;

  return (
    <CardShell emphasis="primary">
      <View style={styles.performanceHeader}>
        <View>
          <Text style={styles.kicker}>Portfolio overview</Text>
          <Text style={styles.performanceTitle}>Global equity performance</Text>
          <Text style={styles.performanceValue}>{formatMetric(total, metric)}</Text>
          <View style={styles.deltaRow}>
            <View style={[styles.deltaBadge, { borderColor: isDown ? theme.colors.danger : theme.colors.success }]}>
              <Text style={[styles.deltaText, { color: isDown ? theme.colors.danger : theme.colors.success }]}>
                {isDown ? 'Down' : 'Up'} {delta.percent === null ? 'n/a' : formatPercent(delta.percent)}
              </Text>
            </View>
            <Text style={styles.deltaAbsolute}>{formatMetric(delta.absolute, metric)}</Text>
          </View>
        </View>
        <StatusChip label={range} tone="accent" />
      </View>

      <SegmentedControl
        items={ranges.map((item) => ({ key: item.key, label: item.key }))}
        selected={range}
        onChange={(value) => onRangeChange(value as RangeKey)}
      />
      <ScrollView horizontal showsHorizontalScrollIndicator={false}>
        <SegmentedControl
          compact
          items={metrics.map((item) => ({ key: item.key, label: item.label }))}
          selected={metric}
          onChange={(value) => onMetricChange(value as MetricKey)}
        />
      </ScrollView>

      <SparkChart accentColor={accentColor} metric={metric} points={points} />
    </CardShell>
  );
}

function BotPortfolioOverviewCard({
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
  const usedPct = aggregate.totalBudget > 0 ? Math.min(100, (aggregate.invested / aggregate.totalBudget) * 100) : 0;

  return (
    <CardShell>
      <View style={styles.portfolioHero}>
        <View style={styles.leftRail} />
        <View style={styles.heroContent}>
          <Text style={styles.kicker}>Systeem overzicht</Text>
          <Text style={styles.heroTitle}>
            Portfolio <Text style={styles.heroDash}>-</Text> {envFilter === 'all' ? 'Alle bots' : envFilter === 'live' ? 'Live' : 'Paper'}
          </Text>
          <Text style={styles.heroBody}>Budget en posities over de geselecteerde omgeving.</Text>
        </View>
      </View>

      <SegmentedControl
        items={envFilters.map((item) => ({ key: item, label: item.toUpperCase() }))}
        selected={envFilter}
        onChange={(value) => onEnvFilterChange(value as EnvFilter)}
      />

      <View style={styles.activeBotTile}>
        <Text style={styles.metricLabel}>Actieve bots</Text>
        <Text style={styles.activeBotCount}>{bots.filter((bot) => bot.isActive).length}</Text>
      </View>

      {exchangeSummary.count > 0 && envFilter !== 'paper' ? (
        <View style={styles.exchangePanel}>
          <Text style={styles.kicker}>Exchange balances</Text>
          <Text style={styles.exchangeSubtitle}>Live wallet context vanuit de backend</Text>
          <View style={styles.exchangeGrid}>
            <SmallStat label="Exchanges" value={String(exchangeSummary.count)} />
            <SmallStat label="Totaal waarde" value={formatEUR(exchangeSummary.totalEur)} />
            <SmallStat label="Vrij EUR" value={formatEUR(exchangeSummary.freeEur)} />
          </View>
          {exchangeSummary.names.length > 0 ? (
            <Text style={styles.exchangeNames}>{exchangeSummary.names.join('  -  ')}</Text>
          ) : null}
        </View>
      ) : null}

      <View style={styles.budgetCard}>
        <Text style={styles.kicker}>Gebruik van totaal budget</Text>
        <Text style={styles.budgetSub}>Single source of truth: backend</Text>
        <View style={styles.budgetLine}>
          <Text style={styles.budgetLabel}>Alle bots gecombineerd</Text>
          <Text style={styles.budgetValue}>
            {formatEUR(aggregate.invested)} / {formatEUR(aggregate.totalBudget)}
          </Text>
        </View>
        <View style={styles.progressTrack}>
          <View style={[styles.progressFill, { width: `${usedPct}%` }]} />
        </View>
        <View style={styles.budgetLine}>
          <Text style={styles.budgetLabel}>Beschikbaar</Text>
          <Text style={styles.budgetValue}>{formatEUR(Math.max(aggregate.totalBudget - aggregate.invested, 0))}</Text>
        </View>
        <View style={styles.inlineStats}>
          <SmallStat label="Vandaag besteed" value={formatEUR(aggregate.todaySpent)} />
          <SmallStat label="Daglimiet" value={formatEUR(aggregate.dailyLimit)} />
          <SmallStat label="Som max/trade" value={formatEUR(aggregate.maxOrder)} />
        </View>
      </View>

      <View style={styles.bigStatsGrid}>
        <BigStat label="Posities" value={String(aggregate.assetRows.length)} />
        <BigStat label="Totale waarde" value={formatEUR(aggregate.positionValue)} />
        <BigStat label="Invested exec" value={formatEUR(aggregate.invested)} />
        <BigStat label="PNL totaal" value={`${formatEUR(aggregate.pnl)} ${formatPercent(aggregate.pnlPct)}`} tone={aggregate.pnl >= 0 ? 'success' : 'danger'} />
      </View>

      {aggregate.assetRows.length > 0 ? (
        <View style={styles.assetBreakdown}>
          <Text style={styles.kicker}>Breakdown per asset</Text>
          {aggregate.assetRows.map((row) => (
            <View key={row.symbol} style={styles.assetRow}>
              <View>
                <Text style={styles.assetSymbol}>{row.symbol}</Text>
                <Text style={styles.assetQty}>{row.netQty.toFixed(6)} {row.symbol}</Text>
              </View>
              <View style={styles.assetValueBlock}>
                <Text style={styles.assetValue}>{formatEUR(row.positionValue)}</Text>
                <Text style={[styles.assetPnl, { color: row.pnl >= 0 ? theme.colors.success : theme.colors.danger }]}>
                  {formatEUR(row.pnl)} {formatPercent(row.pnlPct)}
                </Text>
              </View>
            </View>
          ))}
        </View>
      ) : null}
    </CardShell>
  );
}

function MyBotsSection({ bots, totalBots }: { bots: PortfolioBot[]; totalBots: number }) {
  return (
    <View style={styles.myBots}>
      <View>
        <Text style={styles.myBotsTitle}>My Bots</Text>
        <Text style={styles.myBotsSubtitle}>Overzicht van actieve handelsstrategieen.</Text>
      </View>
      <View style={styles.filterPills}>
        <StatusChip label={`All ${totalBots}`} tone="accent" />
        <StatusChip label={`Active ${bots.filter((bot) => bot.isActive).length}`} tone="success" />
      </View>
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
  const pnl = bot.positionValue - bot.invested;
  const pnlPct = bot.invested > 0 ? (pnl / bot.invested) * 100 : 0;

  return (
    <CardShell>
      <View style={styles.botTop}>
        <View style={styles.botIcon}>
          <Text style={styles.botIconText}>BT</Text>
        </View>
        <View style={styles.botTitleBlock}>
          <View style={styles.botNameRow}>
            <Text style={styles.botName}>{bot.name}</Text>
            <View style={[styles.statusDot, { backgroundColor: bot.isActive ? theme.colors.warning : theme.colors.neutral }]} />
          </View>
          <Text style={styles.botMeta}>
            {bot.symbol}  -  {bot.timeframe}  -  {bot.strategy}
          </Text>
        </View>
      </View>
      <View style={styles.botChips}>
        <Tag label={bot.riskProfile || 'Strategy'} tone={bot.riskProfile.toLowerCase().includes('aggressive') ? 'danger' : 'warning'} />
        <Tag label={bot.isLive ? 'Live' : 'Paper'} tone={bot.isLive ? 'success' : 'accent'} />
        <Tag label={bot.mode || 'Manual-link'} tone="neutral" />
      </View>
      <View style={styles.botMetricGrid}>
        <BotMetric label="Status response" value={bot.isActive ? 'Paper waiting' : 'Paused'} tone={bot.isActive ? 'accent' : 'neutral'} />
        <BotMetric label="Market action" value={bot.positionValue > 0 ? 'Monitor' : 'Hold'} tone="accent" />
        <BotMetric label="Logic confidence" value={pnlPct >= 0 ? 'Stable' : 'Review'} tone={pnlPct >= 0 ? 'success' : 'warning'} />
        <BotMetric label="Telemetry sync" value="Backend" tone="neutral" />
      </View>
      <View style={styles.botFooter}>
        <Text style={styles.botFooterText}>Invested {formatEUR(bot.invested)}</Text>
        <Text style={[styles.botFooterText, { color: pnl >= 0 ? theme.colors.success : theme.colors.danger }]}>
          PnL {formatEUR(pnl)} {formatPercent(pnlPct)}
        </Text>
      </View>
    </CardShell>
  );
}

function SegmentedControl({
  compact = false,
  items,
  onChange,
  selected,
}: {
  compact?: boolean;
  items: Array<{ key: string; label: string }>;
  onChange: (value: string) => void;
  selected: string;
}) {
  return (
    <View style={[styles.segmented, compact && styles.segmentedCompact]}>
      {items.map((item) => {
        const active = selected === item.key;
        return (
          <Pressable
            accessibilityRole="button"
            key={item.key}
            onPress={() => onChange(item.key)}
            style={[styles.segment, compact && styles.segmentCompact, active && styles.segmentActive]}
          >
            <Text style={[styles.segmentText, active && styles.segmentTextActive]} numberOfLines={1}>
              {item.label}
            </Text>
          </Pressable>
        );
      })}
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
  const min = Math.min(...visible, 0);
  const span = Math.max(max - min, 1);

  return (
    <View style={styles.chartBox}>
      <View style={styles.chartGridLine} />
      {visible.length > 0 ? (
        <View style={styles.chartBars}>
          {visible.map((value, index) => {
            const heightPct = 14 + ((value - min) / span) * 78;
            return (
              <View key={`${index}-${value}`} style={styles.chartColumn}>
                <View
                  style={[
                    styles.chartBar,
                    {
                      backgroundColor: accentColor,
                      height: `${heightPct}%`,
                      opacity: 0.35 + (index / Math.max(visible.length - 1, 1)) * 0.55,
                    },
                  ]}
                />
              </View>
            );
          })}
        </View>
      ) : (
        <Text style={styles.emptyChartText}>Geen balance history beschikbaar</Text>
      )}
    </View>
  );
}

function SmallStat({ label, value }: { label: string; value: string }) {
  return (
    <View style={styles.smallStat}>
      <Text style={styles.metricLabel}>{label}</Text>
      <Text style={styles.smallStatValue}>{value}</Text>
    </View>
  );
}

function BigStat({ label, tone, value }: { label: string; tone?: StatusTone; value: string }) {
  return (
    <View style={styles.bigStat}>
      <Text style={styles.metricLabel}>{label}</Text>
      <Text style={[styles.bigStatValue, tone && { color: toneColor(tone) }]}>{value}</Text>
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
  return (
    <View style={styles.botMetric}>
      <Text style={styles.metricLabel}>{label}</Text>
      <Text style={[styles.botMetricValue, { color: toneColor(tone) }]}>{value}</Text>
    </View>
  );
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

function aggregateBots(bots: PortfolioBot[]) {
  const totalBudget = sum(bots, (bot) => bot.budgetTotal);
  const dailyLimit = sum(bots, (bot) => bot.budgetDailyLimit);
  const maxOrder = sum(bots, (bot) => bot.budgetMaxOrder);
  const invested = sum(bots, (bot) => bot.invested);
  const positionValue = sum(bots, (bot) => bot.positionValue);
  const todaySpent = sum(bots, (bot) => bot.todaySpent);
  const pnl = positionValue - invested;
  const pnlPct = invested > 0 ? (pnl / invested) * 100 : 0;

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

function normalizeHistory(history: UnknownRecord[], aggregate: ReturnType<typeof aggregateBots>, targetLength: number) {
  if (history.length > 0) return history;
  const count = Math.min(Math.max(targetLength, 8), 24);
  return Array.from({ length: count }, (_, index) => ({
    btc_qty: aggregate.assetRows[0]?.netQty ?? 0,
    btc_value: aggregate.positionValue,
    cash: Math.max(aggregate.totalBudget - aggregate.invested, 0),
    equity: aggregate.positionValue,
    invested: aggregate.invested,
    ts: new Date(Date.now() - (count - index) * 60 * 60 * 1000).toISOString(),
    unrealized_pnl: aggregate.pnl,
  }));
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
    backgroundColor: theme.colors.surfaceMuted,
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
    backgroundColor: theme.colors.backgroundSoft,
    borderRadius: theme.radius.md,
    flex: 1,
    minWidth: '45%',
    padding: theme.spacing.md,
  },
  botMetricGrid: {
    backgroundColor: theme.colors.surfaceMuted,
    borderRadius: theme.radius.lg,
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: theme.spacing.sm,
    marginTop: theme.spacing.lg,
    padding: theme.spacing.sm,
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
    fontSize: 24,
    fontWeight: '900',
    lineHeight: 28,
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
  cardTitle: {
    color: theme.colors.text,
    fontSize: theme.typography.cardTitle,
    fontWeight: '900',
    marginTop: 5,
  },
  chartBar: {
    borderRadius: theme.radius.pill,
    minHeight: 4,
    width: 4,
  },
  chartBars: {
    alignItems: 'flex-end',
    flexDirection: 'row',
    gap: 2,
    height: '100%',
    justifyContent: 'space-between',
    paddingHorizontal: theme.spacing.sm,
  },
  chartBox: {
    backgroundColor: theme.colors.backgroundSoft,
    borderColor: theme.colors.border,
    borderRadius: theme.radius.md,
    borderWidth: 1,
    height: 220,
    justifyContent: 'center',
    marginTop: theme.spacing.lg,
    overflow: 'hidden',
    paddingVertical: theme.spacing.md,
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
    backgroundColor: theme.colors.backgroundSoft,
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
    fontSize: 31,
    fontWeight: '900',
    letterSpacing: 0,
    lineHeight: 36,
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
    fontSize: 34,
    fontWeight: '900',
    lineHeight: 38,
  },
  performanceHeader: {
    alignItems: 'flex-start',
    flexDirection: 'row',
    justifyContent: 'space-between',
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
    fontSize: 41,
    fontWeight: '900',
    letterSpacing: 0,
    marginTop: theme.spacing.xs,
  },
  portfolioHero: {
    flexDirection: 'row',
    gap: theme.spacing.md,
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
    fontSize: 31,
    fontWeight: '900',
    marginTop: theme.spacing.sm,
  },
  sectionTop: {
    alignItems: 'flex-start',
    flexDirection: 'row',
    justifyContent: 'space-between',
  },
  segment: {
    alignItems: 'center',
    borderRadius: theme.radius.sm,
    flex: 1,
    justifyContent: 'center',
    minHeight: 38,
    paddingHorizontal: theme.spacing.sm,
  },
  segmentActive: {
    backgroundColor: theme.colors.surfaceElevated,
    borderColor: theme.colors.borderStrong,
    borderWidth: 1,
  },
  segmentCompact: {
    flex: 0,
    minWidth: 106,
  },
  segmentText: {
    color: theme.colors.textDim,
    fontSize: theme.typography.label,
    fontWeight: '900',
    letterSpacing: 1.2,
    textTransform: 'uppercase',
  },
  segmentTextActive: {
    color: theme.colors.accent,
  },
  segmented: {
    backgroundColor: theme.colors.backgroundSoft,
    borderColor: theme.colors.border,
    borderRadius: theme.radius.md,
    borderWidth: 1,
    flexDirection: 'row',
    gap: theme.spacing.xs,
    marginTop: theme.spacing.lg,
    padding: theme.spacing.xs,
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
  tag: {
    backgroundColor: theme.colors.backgroundSoft,
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
});
