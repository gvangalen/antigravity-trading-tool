import { useCallback, useMemo, useState } from 'react';
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';

import { CardShell } from '../components/cards/CardShell';
import { InsightCard } from '../components/cards/InsightCard';
import { AssetContextHeader } from '../components/layout/AssetContextHeader';
import { LoadingSkeletonCard } from '../components/layout/LoadingSkeletonCard';
import { ScreenContainer } from '../components/layout/ScreenContainer';
import { SectionHeader } from '../components/layout/SectionHeader';
import { StatusChip } from '../components/layout/StatusChip';
import { SegmentedControl } from '../components/layout/SegmentedControl';
import { StatusTone, theme } from '../constants/theme';
import { useApiResource } from '../hooks/useApiResource';
import { preferenceColors, useAppPreferences } from '../preferences/AppPreferencesProvider';
import {
  MarketChartPoint,
  MarketLatestResponse,
  MobileOverviewAsset,
  MobileOverviewResponse,
  assistantApi,
  intelligenceApi,
  mobileApi,
} from '../services/tradamindApi';
import { triggerHaptic } from '../utils/haptics';
import { useIntelligenceContext } from '../contexts/ActiveIntelligenceContext';

type Timeframe = '15m' | '1h' | '4h' | '1d';

const timeframes: Timeframe[] = ['15m', '1h', '4h', '1d'];

export function WatchlistScreen() {
  const { context, updateContext } = useIntelligenceContext();
  const selectedSymbol = context.asset;
  const [timeframe, setTimeframe] = useState<Timeframe>('1h');

  const fetchOverview = useCallback(() => mobileApi.overview(), []);
  const overviewResource = useApiResource<MobileOverviewResponse | undefined>({
    fallbackData: undefined,
    fetcher: fetchOverview,
  });

  const fetchLatest = useCallback(() => intelligenceApi.marketLatest(selectedSymbol), [selectedSymbol]);
  const latestResource = useApiResource<MarketLatestResponse | undefined>({
    fallbackData: undefined,
    fetcher: fetchLatest,
  });

  const fetchChart = useCallback(() => intelligenceApi.marketChart7d(selectedSymbol), [selectedSymbol]);
  const chartResource = useApiResource<MarketChartPoint[]>({
    fallbackData: [],
    fetcher: fetchChart,
  });

  const fetchInsight = useCallback(
    () =>
      assistantApi.insight({
        page_type: 'WATCHLIST',
        symbol: selectedSymbol,
        timeframe,
      }),
    [selectedSymbol, timeframe],
  );
  const insightResource = useApiResource({
    fallbackData: undefined,
    fetcher: fetchInsight,
  });

  const assets = useMemo(() => {
    const watchlist = overviewResource.data?.watchlist?.filter(Boolean) ?? [];
    return watchlist.length > 0 ? watchlist : fallbackAssets();
  }, [overviewResource.data]);
  const selectedAsset = assets.find((asset) => asset.symbol === selectedSymbol) ?? assets[0];
  const intelligence = buildAssetIntelligence(selectedAsset, latestResource.data, insightResource.data);
  const chartPoints = buildChartPoints(chartResource.data, selectedAsset, timeframe);
  const chartOverlays = buildChartOverlays(selectedAsset, intelligence);

  async function selectAsset(symbol: string) {
    await triggerHaptic('selection');
    updateContext({ asset: symbol, screen: 'Watchlist' });
  }

  return (
    <ScreenContainer
      edgeToEdge={true}
      refreshing={overviewResource.refreshing || latestResource.refreshing || chartResource.refreshing}
      onRefresh={() => {
        overviewResource.refresh();
        latestResource.refresh();
        chartResource.refresh();
        insightResource.refresh();
      }}
    >
      <AssetContextHeader asset={selectedSymbol} context="Watchlist market terminal" updatedAt={overviewResource.updatedAt} />
      <SectionHeader
        label="Watchlist"
        title="Market intelligence terminal"
        description="TradingView-lite scanning, compact charting and FINN-aware setup context."
      />

      <WatchlistIntelligenceTerminal
        assets={assets}
        selectedSymbol={selectedSymbol}
        stale={overviewResource.isStale}
        onSelect={selectAsset}
      />

      {overviewResource.loading ? (
        <LoadingSkeletonCard />
      ) : (
        <SelectedAssetIntelligence intelligence={intelligence} />
      )}

      <CompactLiveChart
        overlays={chartOverlays}
        points={chartPoints}
        symbol={selectedSymbol}
        timeframe={timeframe}
        onTimeframeChange={setTimeframe}
        loading={chartResource.loading}
      />

      {overviewResource.error ? (
        <InsightCard
          label="Watchlist error"
          title="Mobile overview kon niet live laden."
          body={overviewResource.error.message}
          cta="Retry"
          tone="danger"
          onPress={overviewResource.refresh}
        />
      ) : null}

      {chartResource.error ? (
        <InsightCard
          label="Chart fallback"
          title="Chartdata gebruikt tijdelijk een synthetische fallback."
          body={chartResource.error.message}
          cta="Retry chart"
          tone="warning"
          onPress={chartResource.refresh}
        />
      ) : null}
    </ScreenContainer>
  );
}

type AssetIntelligence = {
  symbol: string;
  price: string;
  change: string;
  changeTone: StatusTone;
  headline: string;
  setupScore: number;
  technicalScore: number;
  marketPosture: string;
  marketPostureTone: StatusTone;
  setupState: string;
  setupStateTone: StatusTone;
  riskState: string;
  riskStateTone: StatusTone;
  finnSummary: string;
};

function SelectedAssetIntelligence({ intelligence }: { intelligence: AssetIntelligence }) {
  const { appearance } = useAppPreferences();
  const colors = preferenceColors(appearance);

  return (
    <CardShell emphasis="primary" edgeToEdge={true}>
      <View style={styles.intelTop}>
        <View style={styles.assetIdentity}>
          <AssetIcon symbol={intelligence.symbol} />
          <View>
            <Text style={styles.intelLabel}>Selected asset</Text>
            <Text style={[styles.intelSymbol, { color: colors.text }]}>{intelligence.symbol}</Text>
          </View>
        </View>
        <StatusChip label={intelligence.change} tone={intelligence.changeTone} />
      </View>

      <Text style={[styles.price, { color: colors.text }]}>{intelligence.price}</Text>
      <Text style={[styles.intelHeadline, { color: colors.text }]}>{intelligence.headline}</Text>
      <Text style={[styles.finnSummary, { color: colors.textMuted }]}>{intelligence.finnSummary}</Text>

      <View style={styles.intelChips}>
        <StatusChip label={intelligence.marketPosture} tone={intelligence.marketPostureTone} />
        <StatusChip label={intelligence.setupState} tone={intelligence.setupStateTone} />
        <StatusChip label={intelligence.riskState} tone={intelligence.riskStateTone} />
      </View>

      <View style={styles.scoreStrip}>
        <MiniMetric label="Setup" value={String(intelligence.setupScore)} tone={toneForScore(intelligence.setupScore)} />
        <MiniMetric label="Technical" value={String(intelligence.technicalScore)} tone={toneForScore(intelligence.technicalScore)} />
        <MiniMetric label="Desk read" value={intelligence.marketPosture} tone={intelligence.marketPostureTone} />
      </View>
    </CardShell>
  );
}

function CompactLiveChart({
  loading,
  onTimeframeChange,
  overlays,
  points,
  symbol,
  timeframe,
}: {
  loading: boolean;
  onTimeframeChange: (timeframe: Timeframe) => void;
  overlays: ChartOverlay[];
  points: ChartPoint[];
  symbol: string;
  timeframe: Timeframe;
}) {
  const { appearance } = useAppPreferences();
  const colors = preferenceColors(appearance);

  return (
    <View style={{ borderBottomWidth: 0.5, borderColor: colors.border, paddingVertical: theme.spacing.md }}>
      <View style={styles.chartHeader}>
        <View>
          <Text style={styles.chartLabel}>Compact live chart</Text>
          <Text style={[styles.chartTitle, { color: colors.text }]}>{symbol}USD</Text>
        </View>
        <StatusChip label="RSI · MA200 · VOL" tone="accent" />
      </View>

      <SegmentedControl
        items={timeframes.map((item) => ({ key: item, label: item }))}
        selected={timeframe}
        onChange={(value) => onTimeframeChange(value as Timeframe)}
      />

      {loading ? <LoadingSkeletonCard /> : <NativeCandleChart overlays={overlays} points={points} />}
    </View>
  );
}

type ChartPoint = {
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  rsi: number;
};

type ChartOverlay = {
  id: string;
  label: string;
  price: number;
  tone: StatusTone;
  type: 'setup_zone' | 'entry' | 'stop' | 'target' | 'ai_level' | 'bot_marker';
};

function NativeCandleChart({ overlays, points }: { overlays: ChartOverlay[]; points: ChartPoint[] }) {
  const { appearance } = useAppPreferences();
  const colors = preferenceColors(appearance);
  const visible = points.slice(-28);
  const min = Math.min(...visible.map((point) => point.low));
  const max = Math.max(...visible.map((point) => point.high));
  const maxVolume = Math.max(...visible.map((point) => point.volume));

  return (
    <View style={[styles.chartCanvas, { backgroundColor: colors.backgroundSoft, borderColor: colors.border }]}>
      <View style={styles.priceGrid}>
        <Text style={[styles.axisText, { color: colors.textDim }]}>{formatCompact(max)}</Text>
        <Text style={[styles.axisText, { color: colors.textDim }]}>{formatCompact((max + min) / 2)}</Text>
        <Text style={[styles.axisText, { color: colors.textDim }]}>{formatCompact(min)}</Text>
      </View>
      <View style={[styles.candleRow, { borderBottomColor: colors.border }]}>
        <ChartOverlays overlays={overlays} min={min} max={max} />
        {visible.map((point, index) => {
          const bullish = point.close >= point.open;
          const highTop = scaleToChart(point.high, min, max);
          const lowTop = scaleToChart(point.low, min, max);
          const bodyTop = scaleToChart(Math.max(point.open, point.close), min, max);
          const bodyBottom = scaleToChart(Math.min(point.open, point.close), min, max);
          const volumeHeight = Math.max(8, (point.volume / maxVolume) * 44);

          return (
            <View style={styles.candleSlot} key={`${point.close}-${index}`}>
              <View
                style={[
                  styles.wick,
                  {
                    backgroundColor: bullish ? theme.colors.success : theme.colors.danger,
                    height: Math.max(8, lowTop - highTop),
                    top: highTop,
                  },
                ]}
              />
              <View
                style={[
                  styles.candle,
                  {
                    backgroundColor: bullish ? theme.colors.success : theme.colors.danger,
                    height: Math.max(10, bodyBottom - bodyTop),
                    top: bodyTop,
                  },
                ]}
              />
              <View
                style={[
                  styles.maDot,
                  {
                    top: scaleToChart((point.open + point.close + point.low) / 3, min, max),
                  },
                ]}
              />
              <View
                style={[
                  styles.volumeBar,
                  {
                    backgroundColor: bullish ? '#10B98166' : '#F43F5E66',
                    height: volumeHeight,
                  },
                ]}
              />
            </View>
          );
        })}
      </View>
      <View style={styles.rsiPanel}>
        <Text style={styles.rsiLabel}>RSI 14</Text>
        <View style={styles.rsiLine}>
          {visible.map((point, index) => (
            <View
              key={`rsi-${index}`}
              style={[
                styles.rsiDot,
                {
                  left: `${(index / Math.max(1, visible.length - 1)) * 100}%`,
                  top: `${100 - point.rsi}%`,
                },
              ]}
            />
          ))}
        </View>
      </View>
    </View>
  );
}

function ChartOverlays({ max, min, overlays }: { max: number; min: number; overlays: ChartOverlay[] }) {
  const { appearance } = useAppPreferences();
  const colors = preferenceColors(appearance);

  return (
    <View pointerEvents="none" style={styles.overlayLayer}>
      {overlays.map((overlay) => {
        const top = scaleToChart(overlay.price, min, max);
        const color = colorForTone(overlay.tone);
        return (
          <View key={overlay.id} style={[styles.overlayLine, { borderColor: color, top }]}>
            <Text style={[styles.overlayLabel, { backgroundColor: colors.backgroundSoft, color }]}>{overlay.label}</Text>
          </View>
        );
      })}
    </View>
  );
}

function ScannerRow({
  asset,
  onPress,
  selected,
}: {
  asset: MobileOverviewAsset;
  onPress: () => void;
  selected: boolean;
}) {
  const { appearance } = useAppPreferences();
  const colors = preferenceColors(appearance);
  const score = compositeScore(asset);
  const change = typeof asset.change_24h === 'number' ? asset.change_24h : 0;
  const tone = change >= 0 ? 'success' : 'danger';
  const state = stateForAsset(asset);

  return (
    <Pressable onPress={onPress} style={({ pressed }) => [styles.row, { borderBottomColor: colors.borderSubtle }, selected && [styles.rowSelected, { backgroundColor: colors.surfaceMuted, borderColor: colors.borderStrong }], pressed && styles.pressed]}>
      <View style={styles.rowAsset}>
        <AssetIcon symbol={asset.symbol} compact />
        <View style={styles.rowAssetText}>
          <Text style={[styles.rowSymbol, { color: colors.text }]}>{asset.symbol}</Text>
        </View>
      </View>
      <Text style={[styles.rowPrice, { color: colors.text }]}>{typeof asset.price === 'number' ? formatShortPrice(asset.price) : 'n/a'}</Text>
      <Text style={[styles.rowChange, { color: tone === 'success' ? theme.colors.success : theme.colors.danger }]}>
        {change >= 0 ? '+' : ''}
        {change.toFixed(2)}%
      </Text>
      <Text style={[styles.rowSetup, { color: colorForTone(toneForScore(asset.setup_score)) }]}>{Math.round(asset.setup_score)}</Text>
      <Text style={[styles.rowAiState, { color: colorForTone(toneForScore(score)) }]} numberOfLines={1}>
        {state}
      </Text>
    </Pressable>
  );
}

function WatchlistIntelligenceTerminal({
  assets,
  onSelect,
  selectedSymbol,
  stale,
}: {
  assets: MobileOverviewAsset[];
  onSelect: (symbol: string) => void;
  selectedSymbol: string;
  stale: boolean;
}) {
  const { appearance } = useAppPreferences();
  const colors = preferenceColors(appearance);

  return (
    <View style={styles.terminal}>
      <View style={styles.terminalHeader}>
        <View style={styles.terminalTitleRow}>
          <Text style={styles.terminalStar}>★</Text>
          <View>
            <Text style={styles.terminalLabel}>Intelligence Terminal</Text>
            <Text style={[styles.terminalSubtitle, { color: colors.textMuted }]}>Desktop watchlist logic</Text>
          </View>
        </View>
        <StatusChip label={stale ? 'Stale' : 'Live'} tone={stale ? 'warning' : 'success'} />
      </View>

      <View style={[styles.terminalList, { backgroundColor: colors.backgroundSoft, borderColor: colors.border }]}>
        {assets.filter(Boolean).map((asset) => (
          <TerminalAssetCard
            asset={asset}
            key={asset.symbol}
            selected={asset.symbol === selectedSymbol}
            onPress={() => onSelect(asset.symbol)}
          />
        ))}
      </View>
    </View>
  );
}

function TerminalAssetCard({
  asset,
  onPress,
  selected,
}: {
  asset: MobileOverviewAsset;
  onPress: () => void;
  selected: boolean;
}) {
  const { appearance } = useAppPreferences();
  const colors = preferenceColors(appearance);
  const intel = desktopLikeIntelligence(asset);
  const riskTone = riskToneForTerminal(intel.riskState);

  return (
    <Pressable
      accessibilityRole="button"
      onPress={onPress}
      style={({ pressed }) => [
        styles.terminalCard,
        { 
          borderBottomColor: colors.borderSubtle,
          backgroundColor: selected 
            ? (appearance === 'light' ? '#EFF6FF' : '#1E293B') 
            : (appearance === 'light' ? '#F8FAFC' : '#0F172A'),
        },
        selected && styles.terminalCardActive,
        pressed && styles.pressed,
      ]}
    >
      <View style={styles.terminalAssetTop}>
        <View style={styles.terminalAssetIdentity}>
          <View style={[styles.terminalDot, selected ? styles.terminalDotActive : [styles.terminalDotIdle, { backgroundColor: colors.borderStrong }]]} />
          <Text style={[styles.terminalAssetSymbol, { color: colors.text }]}>{asset.symbol}</Text>
        </View>
        <View style={styles.terminalPriceBlock}>
          <Text style={[styles.terminalPrice, { color: colors.text }]}>{typeof asset.price === 'number' ? formatShortPrice(asset.price) : 'n/a'}</Text>
          <Text style={[styles.terminalChange, { color: colorForTone(intel.changeTone) }]}>
            {intel.change}
          </Text>
        </View>
      </View>

      <View style={styles.terminalMetricsRow}>
        <Text style={[styles.terminalMetricText, { color: colors.textDim }]}>
          {intel.posture}  ·  {intel.structure}  ·  {intel.conviction}%  ·  <Text style={{ color: colorForTone(riskTone), fontWeight: '700' }}>{intel.riskState}</Text>
        </Text>
      </View>
    </Pressable>
  );
}



function AssetIcon({ compact = false, symbol }: { compact?: boolean; symbol: string }) {
  const background = symbol === 'BTC' ? '#F7931A' : symbol === 'ETH' ? '#627EEA' : symbol === 'SOL' ? '#111827' : theme.colors.accent;
  return (
    <View style={[styles.icon, compact && styles.iconCompact, { backgroundColor: background }]}>
      <Text style={[styles.iconText, compact && styles.iconTextCompact]}>{symbol.slice(0, 1)}</Text>
    </View>
  );
}

function MiniMetric({ label, tone, value }: { label: string; tone: StatusTone; value: string }) {
  const { appearance } = useAppPreferences();
  const colors = preferenceColors(appearance);
  const color =
    tone === 'success'
      ? theme.colors.success
      : tone === 'warning'
        ? theme.colors.warning
        : tone === 'danger'
          ? theme.colors.danger
      : theme.colors.accent;

  return (
    <View style={{ flex: 1, gap: 2 }}>
      <Text style={{ fontSize: 10, color: colors.textDim, fontWeight: '700', letterSpacing: 0.5 }}>{label.toUpperCase()}</Text>
      <Text style={{ fontSize: 13, color: color, fontWeight: '700' }}>{value}</Text>
    </View>
  );
}

function colorForTone(tone: StatusTone) {
  if (tone === 'success') return theme.colors.success;
  if (tone === 'warning') return theme.colors.warning;
  if (tone === 'danger') return theme.colors.danger;
  if (tone === 'neutral') return theme.colors.textDim;
  return theme.colors.accent;
}

function buildAssetIntelligence(
  asset: MobileOverviewAsset,
  latest?: MarketLatestResponse,
  insight?: { greeting?: string; market_insight?: Record<string, string> | null },
): AssetIntelligence {
  const latestPrice = readNumber(latest, ['price'], asset.price ?? 0);
  const latestChange = readNumber(latest, ['change_24h'], asset.change_24h ?? 0);
  const setupScore = Math.round(asset.setup_score);
  const technicalScore = Math.round(asset.technical_score);
  const posture = postureForAsset(asset, latestChange);
  const setupState = setupStateForAsset(asset);
  const riskState = riskStateForAsset(asset, latestChange);
  const headline = headlineForAsset(asset, latestChange);
  const aiCopy = conciseInsight(insightText(insight?.market_insight));
  const finnText =
    aiCopy ||
    `${headline}. Setup ${setupScore}. Technical ${technicalScore}.`;

  return {
    change: `${latestChange >= 0 ? '+' : ''}${latestChange.toFixed(2)}%`,
    changeTone: latestChange >= 0 ? 'success' : 'danger',
    finnSummary: finnText,
    headline,
    marketPosture: posture,
    marketPostureTone: latestChange >= 0 && technicalScore >= 60 ? 'success' : latestChange < -3 ? 'danger' : 'accent',
    price: latestPrice > 0 ? formatPrice(latestPrice) : 'n/a',
    riskState,
    riskStateTone: riskState === 'High risk' || riskState === 'Weak risk/reward' ? 'danger' : riskState === 'Wait' ? 'warning' : 'success',
    setupScore,
    setupState,
    setupStateTone: toneForScore(setupScore),
    symbol: asset.symbol,
    technicalScore,
  };
}

function buildChartOverlays(asset: MobileOverviewAsset, intelligence: AssetIntelligence): ChartOverlay[] {
  if (!asset.price) return [];
  const price = asset.price;

  return [
    {
      id: `${asset.symbol}-ai-level`,
      label: intelligence.setupState,
      price: price * (intelligence.setupScore >= 70 ? 1.012 : 0.988),
      tone: intelligence.setupStateTone,
      type: 'ai_level',
    },
  ];
}

function buildChartPoints(source: MarketChartPoint[], asset: MobileOverviewAsset, timeframe: Timeframe): ChartPoint[] {
  const realPoints = source
    .filter((point) => point.close || point.open)
    .map((point, index) => ({
      close: Number(point.close ?? point.open ?? asset.price ?? 1),
      high: Number(point.high ?? point.close ?? point.open ?? asset.price ?? 1),
      low: Number(point.low ?? point.close ?? point.open ?? asset.price ?? 1),
      open: Number(point.open ?? point.close ?? asset.price ?? 1),
      rsi: 38 + ((index * 9) % 38),
      volume: Number(point.volume ?? 1000 + index * 140),
    }));

  const base = realPoints.length > 3 ? realPoints : syntheticPoints(asset);
  const multiplier = timeframe === '15m' ? 4 : timeframe === '1h' ? 3 : timeframe === '4h' ? 2 : 1;

  if (base.length >= 24) return base;

  return Array.from({ length: 28 }, (_, index) => {
    const anchor = base[index % base.length];
    const wave = Math.sin(index / multiplier) * (anchor.close * 0.006);
    const close = anchor.close + wave;
    const open = index === 0 ? anchor.open : close - wave * 0.7;
    return {
      close,
      high: Math.max(open, close) + Math.abs(wave) + close * 0.004,
      low: Math.min(open, close) - Math.abs(wave) - close * 0.004,
      open,
      rsi: Math.max(22, Math.min(78, anchor.rsi + Math.sin(index / 2) * 12)),
      volume: anchor.volume * (0.7 + Math.abs(Math.sin(index / 3))),
    };
  });
}

function fallbackAssets(): MobileOverviewAsset[] {
  return [
    {
      symbol: 'BTC',
      price: 81040,
      change_24h: 2.35,
      macro_score: 64,
      market_score: 72,
      technical_score: 58,
      setup_score: 38,
      macro_label: 'Neutral',
      market_label: 'Risk-on',
      technical_label: 'Compression',
    },
    {
      symbol: 'ETH',
      price: 2278.2,
      change_24h: -2.62,
      macro_score: 58,
      market_score: 61,
      technical_score: 42,
      setup_score: 35,
      macro_label: 'Neutral',
      market_label: 'Mixed',
      technical_label: 'Weak Structure',
    },
    {
      symbol: 'SOL',
      price: 94.51,
      change_24h: -3.01,
      macro_score: 55,
      market_score: 59,
      technical_score: 44,
      setup_score: 39,
      macro_label: 'Neutral',
      market_label: 'Mixed',
      technical_label: 'Weak Structure',
    },
  ];
}

function syntheticPoints(asset: MobileOverviewAsset): ChartPoint[] {
  const base = asset.price ?? (asset.symbol === 'BTC' ? 80500 : asset.symbol === 'ETH' ? 2275 : 94);
  return Array.from({ length: 12 }, (_, index) => {
    const wave = Math.sin(index / 1.6) * base * 0.018;
    const close = base + wave + index * base * 0.001;
    const open = close - Math.cos(index) * base * 0.012;
    return {
      close,
      high: Math.max(open, close) + base * 0.014,
      low: Math.min(open, close) - base * 0.014,
      open,
      rsi: 42 + Math.sin(index / 1.4) * 18,
      volume: 1000 + Math.abs(Math.sin(index)) * 2200,
    };
  });
}

function stateForAsset(asset: MobileOverviewAsset) {
  if (asset.setup_score >= 80) return 'Near Trigger';
  if (asset.setup_score >= 65 && asset.technical_score >= 60) return 'Constructive';
  if (asset.setup_score < 45 || asset.technical_score < 45) return 'Weak Structure';
  return 'Neutral';
}

function desktopLikeIntelligence(asset: MobileOverviewAsset) {
  const conviction = asset.conviction ?? compositeScore(asset);
  const change = typeof asset.change_24h === 'number' ? asset.change_24h : 0;
  return {
    change: `${change >= 0 ? '+' : ''}${change.toFixed(2)}%`,
    changeTone: change >= 0 ? 'success' as StatusTone : 'danger' as StatusTone,
    conviction,
    posture: asset.posture ?? terminalPostureForAsset(asset, change),
    riskState: asset.risk_state ?? terminalRiskForAsset(asset, change),
    structure: asset.structure ?? terminalStructureForAsset(asset),
  };
}

function terminalPostureForAsset(asset: MobileOverviewAsset, change: number) {
  if (asset.setup_score >= 80 && asset.technical_score >= 65) return 'Momentum Rising';
  if (asset.technical_score >= 70 && change >= 0) return 'Compression';
  if (asset.technical_score < 45 || change < -3) return 'Expansion';
  if (asset.market_score >= 65) return 'Compression';
  return 'Rangebound';
}

function terminalStructureForAsset(asset: MobileOverviewAsset) {
  if (asset.setup_score >= 65 && asset.technical_score >= 60) return 'Bullish Structure';
  if (asset.setup_score < 45 || asset.technical_score < 45) return 'Weak Structure';
  return 'Neutral Structure';
}

function terminalRiskForAsset(asset: MobileOverviewAsset, change: number) {
  if (asset.setup_score < 45 || asset.technical_score < 45 || change <= -3) return 'Risk Elevated';
  if (asset.setup_score >= 70 && asset.technical_score >= 60) return 'Laag / Stabiel';
  return 'Gematigd';
}

function riskToneForTerminal(value: string): StatusTone {
  if (value.includes('Laag')) return 'success';
  if (value.includes('Risk')) return 'danger';
  return 'warning';
}

function postureForAsset(asset: MobileOverviewAsset, change: number) {
  if (asset.setup_score >= 80 && change > 0) return 'Near trigger';
  if (asset.technical_score >= 70 && change >= 0) return 'Momentum improving';
  if (asset.technical_score < 45 || change < -3) return 'Weak structure';
  if (asset.setup_score >= 65) return 'Risk-on selective';
  return 'Waiting confirmation';
}

function setupStateForAsset(asset: MobileOverviewAsset) {
  if (asset.setup_score >= 80) return 'Near trigger';
  if (asset.setup_score >= 65) return 'Setup valid';
  if (asset.setup_score < 40) return 'Setup weak';
  return 'Wait confirm';
}

function riskStateForAsset(asset: MobileOverviewAsset, change: number) {
  if (asset.setup_score < 40 || asset.technical_score < 40) return 'High risk';
  if (change < -3) return 'Weak risk/reward';
  if (asset.setup_score < 65) return 'Wait';
  return 'Controlled';
}

function headlineForAsset(asset: MobileOverviewAsset, change: number) {
  if (asset.setup_score >= 82 && asset.technical_score >= 65) return 'Near trigger';
  if (change >= 1.5 && asset.technical_score >= 60) return 'Constructive recovery';
  if (asset.technical_score < 45 || change <= -3) return 'Weak structure';
  if (asset.market_score >= 70 && asset.setup_score >= 65) return 'Risk-on, selective';
  if (asset.technical_score >= 65) return 'Momentum improving';
  return 'Waiting confirmation';
}

function conciseInsight(value: string) {
  if (!value) return '';
  return value
    .replace(/^Hello[^,.]*[,.]\s*/i, '')
    .split(/[.!?]/)
    .map((part) => part.trim())
    .filter(Boolean)
    .slice(0, 2)
    .join('. ');
}

function compositeScore(asset: MobileOverviewAsset) {
  return Math.round((asset.macro_score + asset.market_score + asset.technical_score + asset.setup_score) / 4);
}

function toneForScore(score: number): StatusTone {
  if (score >= 70) return 'success';
  if (score >= 55) return 'accent';
  if (score >= 40) return 'warning';
  return 'danger';
}

function scaleToChart(value: number, min: number, max: number) {
  const range = Math.max(1, max - min);
  return Math.max(4, Math.min(138, 138 - ((value - min) / range) * 132));
}

function readNumber(source: Record<string, unknown> | undefined, keys: string[], fallback: number) {
  for (const key of keys) {
    const value = source?.[key];
    if (typeof value === 'number' && Number.isFinite(value)) return value;
    if (typeof value === 'string' && Number.isFinite(Number(value))) return Number(value);
  }
  return fallback;
}

function insightText(value: Record<string, string> | null | undefined) {
  if (!value) return '';
  return value.conclusion || value.summary || value.insight || value.why || Object.values(value).find(Boolean) || '';
}

function formatPrice(value: number) {
  return new Intl.NumberFormat('en-US', {
    currency: 'USD',
    maximumFractionDigits: value > 1000 ? 0 : 2,
    style: 'currency',
  }).format(value);
}

function formatShortPrice(value: number) {
  if (value >= 1000) {
    return `$${new Intl.NumberFormat('en-US', {
      maximumFractionDigits: value >= 10000 ? 0 : 1,
      notation: 'compact',
    }).format(value)}`;
  }
  return `$${new Intl.NumberFormat('en-US', {
    maximumFractionDigits: value >= 100 ? 1 : 2,
  }).format(value)}`;
}

function formatCompact(value: number) {
  return new Intl.NumberFormat('en-US', {
    maximumFractionDigits: value > 1000 ? 0 : 2,
    notation: value > 100000 ? 'compact' : 'standard',
  }).format(value);
}

const styles = StyleSheet.create({
  assetIdentity: {
    alignItems: 'center',
    flexDirection: 'row',
    gap: theme.spacing.md,
  },
  axisText: {
    color: theme.colors.textDim,
    fontSize: 10,
    fontWeight: '800',
  },
  candle: {
    borderRadius: 3,
    position: 'absolute',
    width: 7,
  },
  candleRow: {
    borderBottomColor: theme.colors.border,
    borderBottomWidth: 1,
    flex: 1,
    flexDirection: 'row',
    gap: 4,
    height: 178,
    paddingRight: 54,
    position: 'relative',
  },
  candleSlot: {
    alignItems: 'center',
    flex: 1,
    minWidth: 7,
    position: 'relative',
  },
  columnAsset: {
    flex: 1.05,
    textAlign: 'left',
  },
  columnChange: {
    flex: 0.58,
    textAlign: 'right',
  },
  columnLabel: {
    color: theme.colors.textDim,
    fontSize: 10,
    fontWeight: '900',
    letterSpacing: 1,
    textTransform: 'uppercase',
  },
  columnPrice: {
    flex: 0.62,
    textAlign: 'right',
  },
  columnSetup: {
    flex: 0.48,
    textAlign: 'right',
  },
  columnState: {
    flex: 0.88,
    textAlign: 'right',
  },
  chartCanvas: {
    backgroundColor: theme.colors.backgroundSoft,
    borderColor: theme.colors.border,
    borderRadius: theme.radius.md,
    borderWidth: 1,
    height: 258,
    marginTop: theme.spacing.md,
    overflow: 'hidden',
    paddingLeft: theme.spacing.sm,
    paddingTop: theme.spacing.sm,
  },
  chartHeader: {
    alignItems: 'flex-start',
    flexDirection: 'row',
    gap: theme.spacing.md,
    justifyContent: 'space-between',
  },
  chartLabel: {
    color: theme.colors.textDim,
    fontSize: theme.typography.label,
    fontWeight: '900',
    letterSpacing: 1.5,
    textTransform: 'uppercase',
  },
  chartTitle: {
    color: theme.colors.text,
    fontSize: theme.typography.cardTitle,
    fontWeight: '900',
    marginTop: 4,
  },
  finnSummary: {
    color: theme.colors.textMuted,
    fontSize: 14,
    fontWeight: '700',
    lineHeight: 20,
    marginTop: theme.spacing.sm,
  },
  icon: {
    alignItems: 'center',
    borderRadius: theme.radius.lg,
    height: 48,
    justifyContent: 'center',
    width: 48,
  },
  iconCompact: {
    borderRadius: theme.radius.pill,
    height: 34,
    width: 34,
  },
  iconText: {
    color: theme.colors.white,
    fontSize: 22,
    fontWeight: '900',
  },
  iconTextCompact: {
    fontSize: 16,
  },
  intelLabel: {
    color: theme.colors.textDim,
    fontSize: theme.typography.label,
    fontWeight: '900',
    letterSpacing: 1.5,
    textTransform: 'uppercase',
  },
  intelChips: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: theme.spacing.sm,
    marginTop: theme.spacing.md,
  },
  intelHeadline: {
    color: theme.colors.text,
    fontSize: theme.typography.title,
    fontWeight: '900',
    lineHeight: 27,
    marginTop: theme.spacing.sm,
  },
  intelSymbol: {
    color: theme.colors.text,
    fontSize: 18,
    fontWeight: '900',
    marginTop: 2,
  },
  intelTop: {
    alignItems: 'flex-start',
    flexDirection: 'row',
    justifyContent: 'space-between',
  },
  maDot: {
    backgroundColor: '#60A5FA',
    borderRadius: 3,
    height: 4,
    opacity: 0.85,
    position: 'absolute',
    width: 4,
  },
  overlayLabel: {
    backgroundColor: theme.colors.backgroundSoft,
    fontSize: 9,
    fontWeight: '900',
    letterSpacing: 0.8,
    paddingHorizontal: 5,
    position: 'absolute',
    right: 0,
    textTransform: 'uppercase',
    top: -8,
  },
  overlayLayer: {
    bottom: 0,
    left: 0,
    position: 'absolute',
    right: 54,
    top: 0,
    zIndex: 4,
  },
  overlayLine: {
    borderTopWidth: 1,
    left: 0,
    opacity: 0.9,
    position: 'absolute',
    right: 0,
  },
  metric: {
    backgroundColor: theme.colors.backgroundSoft,
    borderColor: theme.colors.border,
    borderRadius: theme.radius.md,
    borderWidth: 1,
    flex: 1,
    padding: theme.spacing.sm,
  },
  metricLabel: {
    color: theme.colors.textDim,
    fontSize: 9,
    fontWeight: '900',
    letterSpacing: 1.1,
    textTransform: 'uppercase',
  },
  metricValue: {
    fontSize: 15,
    fontWeight: '900',
    marginTop: 5,
  },
  pressed: {
    opacity: 0.86,
  },
  price: {
    color: theme.colors.text,
    fontSize: 18,
    fontWeight: '900',
    letterSpacing: 0,
    marginTop: theme.spacing.lg,
  },
  priceGrid: {
    bottom: 76,
    justifyContent: 'space-between',
    position: 'absolute',
    right: theme.spacing.sm,
    top: theme.spacing.md,
    width: 48,
    zIndex: 3,
  },
  row: {
    alignItems: 'center',
    borderBottomColor: theme.colors.borderSubtle,
    borderBottomWidth: 1,
    flexDirection: 'row',
    gap: theme.spacing.xs,
    minHeight: 62,
    paddingHorizontal: theme.spacing.sm,
  },
  rowAsset: {
    alignItems: 'center',
    flex: 1.05,
    flexDirection: 'row',
    gap: theme.spacing.xs,
  },
  rowAssetText: {
    flex: 1,
  },
  rowChange: {
    flex: 0.58,
    fontSize: 12,
    fontWeight: '900',
    textAlign: 'right',
  },
  rowAiState: {
    flex: 0.88,
    fontSize: 12,
    fontWeight: '900',
    textAlign: 'right',
  },
  rowPrice: {
    color: theme.colors.text,
    flex: 0.62,
    fontSize: 12,
    fontWeight: '900',
    textAlign: 'right',
  },
  rowSelected: {
    backgroundColor: theme.colors.surfaceMuted,
    borderColor: theme.colors.borderStrong,
    borderRadius: theme.radius.sm,
    borderWidth: 1,
  },
  rowSetup: {
    flex: 0.48,
    fontSize: 14,
    fontWeight: '900',
    textAlign: 'right',
  },
  rowSymbol: {
    color: theme.colors.text,
    fontSize: 14,
    fontWeight: '900',
  },
  rsiDot: {
    backgroundColor: '#C084FC',
    borderRadius: 3,
    height: 4,
    position: 'absolute',
    width: 4,
  },
  rsiLabel: {
    color: theme.colors.textDim,
    fontSize: 10,
    fontWeight: '900',
    letterSpacing: 1.1,
    textTransform: 'uppercase',
  },
  rsiLine: {
    flex: 1,
    marginLeft: theme.spacing.sm,
    position: 'relative',
  },
  rsiPanel: {
    alignItems: 'center',
    backgroundColor: '#581C8733',
    borderTopColor: '#C084FC55',
    borderTopWidth: 1,
    bottom: 0,
    flexDirection: 'row',
    height: 68,
    left: 0,
    paddingHorizontal: theme.spacing.md,
    position: 'absolute',
    right: 0,
  },
  scanner: {
    backgroundColor: theme.colors.surface,
    borderColor: theme.colors.border,
    borderRadius: theme.radius.card,
    borderWidth: 1,
    overflow: 'hidden',
  },
  scannerColumns: {
    alignItems: 'center',
    backgroundColor: theme.colors.backgroundSoft,
    borderBottomColor: theme.colors.border,
    borderBottomWidth: 1,
    flexDirection: 'row',
    gap: theme.spacing.xs,
    paddingHorizontal: theme.spacing.sm,
    paddingVertical: theme.spacing.sm,
  },
  scannerHeader: {
    alignItems: 'center',
    flexDirection: 'row',
    justifyContent: 'space-between',
  },
  scannerLabel: {
    color: theme.colors.accent,
    fontSize: theme.typography.label,
    fontWeight: '900',
    letterSpacing: 1.6,
    textTransform: 'uppercase',
  },
  scannerTitle: {
    color: theme.colors.text,
    fontSize: theme.typography.title,
    fontWeight: '900',
    marginTop: 4,
  },
  scoreStrip: {
    flexDirection: 'row',
    gap: theme.spacing.sm,
    marginTop: theme.spacing.lg,
  },
  setupPill: {
    alignItems: 'center',
    backgroundColor: theme.colors.accentSoft,
    borderColor: '#1D4ED880',
    borderRadius: theme.radius.pill,
    borderWidth: 1,
    flex: 0.85,
    paddingHorizontal: theme.spacing.sm,
    paddingVertical: theme.spacing.xs,
  },
  setupPillText: {
    color: theme.colors.textSoft,
    fontSize: 11,
    fontWeight: '900',
  },
  terminal: {
    gap: theme.spacing.md,
  },
  terminalAssetIdentity: {
    alignItems: 'center',
    flexDirection: 'row',
    gap: theme.spacing.sm,
  },
  terminalAssetSymbol: {
    color: theme.colors.text,
    fontSize: 14,
    fontWeight: '700',
    letterSpacing: 0.5,
  },
  terminalAssetTop: {
    alignItems: 'center',
    flexDirection: 'row',
    justifyContent: 'space-between',
  },
  terminalCard: {
    backgroundColor: 'transparent',
    borderBottomWidth: 0.5,
    paddingVertical: 4,
    paddingHorizontal: theme.spacing.md,
    gap: 2,
  },
  terminalCardActive: {
    borderLeftWidth: 4,
    borderLeftColor: theme.colors.accent,
    paddingLeft: theme.spacing.md - 4,
  },
  terminalChange: {
    fontSize: theme.typography.small,
    fontWeight: '600',
    marginTop: 2,
    textAlign: 'right',
  },
  terminalDot: {
    borderRadius: theme.radius.pill,
    height: 11,
    width: 11,
  },
  terminalDotActive: {
    backgroundColor: theme.colors.accent,
  },
  terminalDotIdle: {
    backgroundColor: theme.colors.borderStrong,
  },
  terminalHeader: {
    alignItems: 'center',
    flexDirection: 'row',
    justifyContent: 'space-between',
  },
  terminalLabel: {
    color: theme.colors.textDim,
    fontSize: theme.typography.label,
    fontWeight: '900',
    letterSpacing: 3,
    lineHeight: 15,
    textTransform: 'uppercase',
  },
  terminalList: {
    gap: 0,
    padding: 0,
  },
  terminalMetric: {
    minWidth: '45%',
    flex: 1,
  },
  terminalMetricLabel: {
    color: theme.colors.textDim,
    fontSize: 9,
    fontWeight: '900',
    letterSpacing: 1.8,
    textTransform: 'uppercase',
  },
  terminalMetricStrong: {
    fontWeight: '900',
  },
  terminalMetricValue: {
    color: theme.colors.textMuted,
    fontSize: 13,
    fontWeight: '800',
    marginTop: 5,
  },
  terminalMetricsRow: {
    paddingTop: 0,
  },
  terminalMetricText: {
    fontSize: 13,
    fontWeight: '600',
    letterSpacing: 0.2,
  },
  terminalPrice: {
    color: theme.colors.text,
    fontSize: 14,
    fontWeight: '600',
    textAlign: 'right',
  },
  terminalPriceBlock: {
    alignItems: 'flex-end',
  },
  terminalStar: {
    color: theme.colors.warning,
    fontSize: 16,
    fontWeight: '900',
  },
  terminalSubtitle: {
    color: theme.colors.textMuted,
    fontSize: 12,
    fontWeight: '900',
    letterSpacing: 1.4,
    marginTop: 3,
    textTransform: 'uppercase',
  },
  terminalTitleRow: {
    alignItems: 'center',
    flexDirection: 'row',
    gap: theme.spacing.sm,
  },
  timeframeActive: {
    backgroundColor: theme.colors.accent,
    borderColor: theme.colors.accent,
    transform: [{ scale: 1.04 }],
  },
  timeframeButton: {
    alignItems: 'center',
    backgroundColor: theme.colors.backgroundSoft,
    borderColor: theme.colors.border,
    borderRadius: theme.radius.pill,
    borderWidth: 1,
    flexDirection: 'row',
    gap: theme.spacing.xs,
    paddingHorizontal: theme.spacing.md,
    paddingVertical: theme.spacing.xs,
  },
  timeframePulse: {
    backgroundColor: theme.colors.textDim,
    borderRadius: theme.radius.pill,
    height: 5,
    opacity: 0,
    width: 5,
  },
  timeframePulseActive: {
    backgroundColor: theme.colors.white,
    opacity: 1,
  },
  timeframeText: {
    color: theme.colors.textMuted,
    fontSize: 12,
    fontWeight: '900',
  },
  timeframeTextActive: {
    color: theme.colors.white,
  },
  timeframes: {
    gap: theme.spacing.sm,
    paddingTop: theme.spacing.md,
  },
  volumeBar: {
    borderRadius: 3,
    bottom: 2,
    position: 'absolute',
    width: 8,
  },
  wick: {
    borderRadius: 2,
    position: 'absolute',
    width: 2,
  },
});
