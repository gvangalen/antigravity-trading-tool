import { useCallback, useEffect, useMemo, useState } from 'react';
import { Feather } from '@expo/vector-icons';
import { useNavigation } from '@react-navigation/native';
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';

import { CardShell } from '../components/cards/CardShell';
import { InsightCard } from '../components/cards/InsightCard';
import { LoadingSkeletonCard } from '../components/layout/LoadingSkeletonCard';
import { ScreenContainer } from '../components/layout/ScreenContainer';
import { StatusChip } from '../components/layout/StatusChip';
import { SegmentedControl } from '../components/layout/SegmentedControl';
import { TodayWithFinnCard } from '../components/workspace/TodayWithFinnCard';
import { WorkspaceHeroSection } from '../components/workspace/WorkspaceHeroSection';
import { StatusTone, theme } from '../constants/theme';
import { useApiResource } from '../hooks/useApiResource';
import { localizedBackendText, translate, translateFinnTag } from '../i18n';
import type { MainTabParamList } from '../navigation/MainTabNavigator';
import { preferenceColors, useAppPreferences } from '../preferences/AppPreferencesProvider';
import {
  ForwardReturnChartResponse,
  MarketChartPoint,
  MarketLatestResponse,
  MobileOverviewAsset,
  MobileOverviewResponse,
  WorkspaceAssetResponse,
  assistantApi,
  intelligenceApi,
  mobileApi,
} from '../services/tradamindApi';
import { triggerHaptic } from '../utils/haptics';
import { useIntelligenceContext } from '../contexts/ActiveIntelligenceContext';
import { useFinnOverlay } from '../contexts/FinnOverlayContext';
import { trackAssistantEvent } from '../services/assistantAnalytics';

type Timeframe = '15m' | '1h' | '4h' | '1d';

const timeframes: Timeframe[] = ['15m', '1h', '4h', '1d'];

export function WatchlistScreen() {
  const navigation = useNavigation<any>();
  const { context, updateContext } = useIntelligenceContext();
  const { openFinn } = useFinnOverlay();
  const { language } = useAppPreferences();
  const selectedSymbol = context.asset;
  const [timeframe, setTimeframe] = useState<Timeframe>('1h');

  useEffect(() => {
    trackAssistantEvent({
      event_name: 'screen_view',
      page: 'analysis',
      flow_type: 'analysis',
      asset: selectedSymbol,
    });
  }, [selectedSymbol]);

  const fetchOverview = useCallback(() => mobileApi.overview(selectedSymbol), [selectedSymbol]);
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
  const fetchWorkspaceAsset = useCallback(
    () =>
      intelligenceApi.workspaceAsset(selectedSymbol, {
        market_period: 'day',
        macro_period: 'day',
        technical_period: 'day',
      }),
    [selectedSymbol],
  );
  const workspaceAssetResource = useApiResource<WorkspaceAssetResponse | undefined>({
    fallbackData: undefined,
    fetcher: fetchWorkspaceAsset,
  });
  const fetchTopSetups = useCallback(() => intelligenceApi.topSetups(), []);
  const topSetupsResource = useApiResource({
    fallbackData: undefined,
    fetcher: fetchTopSetups,
  });
  const fetchForwardReturnsMonth = useCallback(
    () => intelligenceApi.forwardReturnsMonth(selectedSymbol),
    [selectedSymbol],
  );
  const forwardReturnsMonthResource = useApiResource<ForwardReturnChartResponse[]>({
    fallbackData: [],
    fetcher: fetchForwardReturnsMonth,
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

  const assets = useMemo(
    () => {
      const liveAssets = (overviewResource.data?.watchlist?.filter(Boolean) ?? []).filter((asset) => asset?.symbol);
      if (liveAssets.length > 0) {
        return liveAssets;
      }

      const fallbackAsset = buildFallbackOverviewAsset(
        selectedSymbol,
        latestResource.data,
        workspaceAssetResource.data,
      );
      return fallbackAsset ? [fallbackAsset] : [];
    },
    [latestResource.data, overviewResource.data, selectedSymbol, workspaceAssetResource.data],
  );
  const selectedAsset = assets.find((asset) => asset.symbol === selectedSymbol) ?? assets[0];
  const intelligence = selectedAsset
    ? buildAssetIntelligence(selectedAsset, latestResource.data, insightResource.data)
    : null;
  const chartPoints = selectedAsset ? buildChartPoints(chartResource.data, selectedAsset, timeframe) : [];
  const chartOverlays = selectedAsset && intelligence ? buildChartOverlays(selectedAsset, intelligence) : [];
  const suggestedPlan = useMemo(() => deriveSuggestedPlan(topSetupsResource.data, selectedAsset), [selectedAsset, topSetupsResource.data]);
  const overview = overviewResource.data;
  const analysisBootstrapLoading =
    assets.length === 0 &&
    (overviewResource.loading || latestResource.loading || workspaceAssetResource.loading);

  async function selectAsset(symbol: string) {
    await triggerHaptic('selection');
    updateContext({ asset: symbol, screen: 'Analysis' });
  }

  return (
    <ScreenContainer
      edgeToEdge={true}
      contentInsetBottom={392}
      refreshing={overviewResource.refreshing || latestResource.refreshing || chartResource.refreshing}
      onRefresh={() => {
        overviewResource.refresh();
        latestResource.refresh();
        chartResource.refresh();
        workspaceAssetResource.refresh();
        insightResource.refresh();
        topSetupsResource.refresh();
        forwardReturnsMonthResource.refresh();
      }}
    >
      {analysisBootstrapLoading ? (
        <LoadingSkeletonCard />
      ) : !selectedAsset ? (
        <InsightCard
          label={
            language === 'nl'
              ? 'Analyse-data'
              : language === 'de'
                ? 'Analysedaten'
                : 'Analysis data'
          }
          title={
            language === 'nl'
              ? 'De backend gaf nog geen analyse-assets terug.'
              : language === 'de'
                ? 'Das Backend hat noch keine Analyse-Assets geliefert.'
                : 'The backend has not returned analysis assets yet.'
          }
          body={
            overviewResource.error?.message ||
            (language === 'nl'
              ? 'Zodra watchlist- en overview-data weer live terugkomen, verschijnt hier direct de echte analyse-workspace.'
              : language === 'de'
                ? 'Sobald Watchlist- und Overview-Daten wieder live ankommen, erscheint hier sofort der echte Analyse-Workspace.'
                : 'As soon as watchlist and overview data come back live, the real analysis workspace will appear here immediately.')
          }
          cta={language === 'nl' ? 'Ververs' : language === 'de' ? 'Aktualisieren' : 'Refresh'}
          tone="warning"
          onPress={() => {
            overviewResource.refresh();
            latestResource.refresh();
            chartResource.refresh();
            workspaceAssetResource.refresh();
            insightResource.refresh();
            topSetupsResource.refresh();
            forwardReturnsMonthResource.refresh();
          }}
        />
      ) : (
        <>
          <AnalysisWorkspaceMissionControl
            activeSymbol={selectedSymbol}
            assets={assets}
            briefing={overview?.finn_briefing}
            intelligence={intelligence!}
            onRefreshScores={() => {
              latestResource.refresh();
              chartResource.refresh();
              workspaceAssetResource.refresh();
              insightResource.refresh();
              topSetupsResource.refresh();
            }}
          />
          <AnalysisWorkspaceIntro
            asset={selectedAsset}
            assets={assets}
            intelligence={intelligence!}
            onAskFinn={() =>
              openFinn({
                prefill: `Help me work through the ${selectedSymbol} analysis workspace step by step: asset, evidence and conclusion.`,
                source: 'analysis-workspace-intro',
                symbol: selectedSymbol,
              })
            }
            onSelect={selectAsset}
            selectedSymbol={selectedSymbol}
            stale={overviewResource.isStale}
          />
          <CompactLiveChart
            overlays={chartOverlays}
            points={chartPoints}
            symbol={selectedSymbol}
            timeframe={timeframe}
            onTimeframeChange={setTimeframe}
            loading={chartResource.loading}
          />
          <AnalysisContextScores asset={selectedAsset} intelligence={intelligence!} workspaceAsset={workspaceAssetResource.data} />
          <AnalysisEvidenceSections asset={selectedAsset} workspaceAsset={workspaceAssetResource.data} />
          <AnalysisPlanBridge
            candidate={suggestedPlan}
            onOpenPlan={() =>
              navigation.navigate('Setup' satisfies keyof MainTabParamList, { symbol: selectedSymbol })
            }
          />
          <HistoricalForwardReturnsCard asset={selectedAsset} rows={forwardReturnsMonthResource.data} />
        </>
      )}

      {chartResource.error ? (
        <InsightCard
          label="Chart error"
          title="Chartdata kon niet live laden."
          body={chartResource.error.message}
          cta="Laad chart opnieuw"
          tone="warning"
          onPress={chartResource.refresh}
        />
      ) : null}
    </ScreenContainer>
  );
}

function AnalysisContextScores({
  asset,
  intelligence,
  workspaceAsset,
}: {
  asset: MobileOverviewAsset;
  intelligence: AssetIntelligence;
  workspaceAsset?: WorkspaceAssetResponse;
}) {
  const { appearance } = useAppPreferences();
  const colors = preferenceColors(appearance);
  const marketScore = readWorkspaceScore(workspaceAsset?.categories?.market?.score?.score) ?? Math.round(asset.market_score);
  const macroScore = readWorkspaceScore(workspaceAsset?.categories?.macro?.score?.score) ?? Math.round(asset.macro_score);
  const technicalScore = readWorkspaceScore(workspaceAsset?.categories?.technical?.score?.score) ?? Math.round(asset.technical_score);
  const combinedScore = readWorkspaceScore(workspaceAsset?.combined?.score) ?? compositeScore(asset);
  const items = [
    { label: 'Market', value: marketScore, tone: toneForScore(marketScore) },
    { label: 'Macro', value: macroScore, tone: toneForScore(macroScore) },
    { label: 'Technical', value: technicalScore, tone: toneForScore(technicalScore) },
    { label: 'Combined', value: combinedScore, tone: intelligence.marketPostureTone },
  ];

  return (
    <CardShell emphasis="standard" flat style={styles.workspaceBlendSurface}>
      <View
        style={[
          styles.contextScoresCard,
          { backgroundColor: colors.surfaceMuted, borderColor: colors.borderSubtle },
        ]}
      >
        <View style={styles.sectionTop}>
          <View style={styles.sectionLead}>
            <Text style={styles.kicker}>Context scores</Text>
            <Text style={[styles.cardTitle, { color: colors.text }]}>Desktop analysis engine</Text>
          </View>
          <View
            style={[
              styles.contextScoresBadge,
              { backgroundColor: `${colorForTone(intelligence.marketPostureTone)}12` },
            ]}
          >
            <Text style={[styles.contextScoresBadgeText, { color: colorForTone(intelligence.marketPostureTone) }]}>
              {intelligence.marketPosture}
            </Text>
          </View>
        </View>
        <View style={styles.scoreOverviewGrid}>
          {items.map((item) => (
            <View key={item.label} style={[styles.scoreOverviewCard, { borderColor: colors.borderSubtle }]}>
              <Text style={styles.scoreOverviewLabel}>{item.label}</Text>
              <Text style={[styles.scoreOverviewValue, { color: colorForTone(item.tone) }]}>{item.value}/100</Text>
            </View>
          ))}
        </View>
      </View>
    </CardShell>
  );
}

function AnalysisWorkspaceMissionControl({
  activeSymbol,
  assets,
  briefing,
  intelligence,
  onRefreshScores,
}: {
  activeSymbol: string;
  assets: MobileOverviewAsset[];
  briefing?: MobileOverviewResponse['finn_briefing'];
  intelligence: AssetIntelligence;
  onRefreshScores: () => void;
}) {
  const { language } = useAppPreferences();
  const reviewCount = assets.filter((asset) => asset.setup_score < 55).length;
  const riskCount = assets.filter((asset) => asset.setup_score < 40 || asset.technical_score < 40).length;
  const performanceCount = assets.filter((asset) => (asset.change_24h ?? 0) >= 0).length;
  const taskCount = assets.length;
  const summary = localizedBackendText(
    language,
    briefing?.summary?.trim(),
    translate(language, 'analysis.summaryUnavailable', { symbol: activeSymbol }),
  );
  const chips = [
    {
      label: reviewCount > 0 ? translate(language, 'tag.actionNeeded') : translate(language, 'tag.monitoring'),
      tone: reviewCount > 0 ? ('warning' as StatusTone) : ('success' as StatusTone),
    },
    { label: translateFinnTag(language, intelligence.marketPosture), tone: intelligence.marketPostureTone },
    {
      label: `${translate(language, 'queue.label.reviews')} ${reviewCount}`,
      tone: reviewCount > 0 ? ('accent' as StatusTone) : ('neutral' as StatusTone),
    },
    {
      label: `${translate(language, 'queue.label.risks')} ${riskCount}`,
      tone: riskCount > 0 ? ('danger' as StatusTone) : ('neutral' as StatusTone),
    },
  ];
  const queueItems = [
    { key: 'tasks', label: translate(language, 'queue.label.tasks'), value: taskCount, body: translate(language, 'queue.body.handleFirst') },
    { key: 'reviews', label: translate(language, 'queue.label.reviews'), value: reviewCount, body: translate(language, 'queue.body.needDecision') },
    { key: 'risks', label: translate(language, 'queue.label.risks'), value: riskCount, body: translate(language, 'queue.body.slowingYouDown') },
    { key: 'performance', label: translate(language, 'queue.label.performance'), value: performanceCount, body: translate(language, 'queue.body.howTodayBehaves') },
  ];

  return (
    <WorkspaceHeroSection>
      <TodayWithFinnCard
        headline={summary}
        support={translate(language, reviewCount === 1 ? 'finn.reviewNeedsAttention' : 'finn.reviewsNeedAttention', {
          count: reviewCount,
        })}
        tags={chips}
        primaryActionLabel={translate(language, 'finn.refreshDailyScores')}
        onPrimaryAction={onRefreshScores}
        queueItems={queueItems}
        queueStatusLabel={translate(language, 'common.itemsOpen', { count: taskCount })}
      />
    </WorkspaceHeroSection>
  );
}

function WorkspaceTonePill({ label, tone }: { label: string; tone: StatusTone }) {
  const { appearance } = useAppPreferences();
  const colors = preferenceColors(appearance);
  const baseColor = tone === 'neutral' ? colors.textDim : (colors[tone] || colors.accent);

  return (
    <View style={[styles.workspaceTonePill, { backgroundColor: appearance === 'light' ? `${baseColor}12` : `${baseColor}20` }]}>
      <View style={[styles.workspaceTonePillDot, { backgroundColor: baseColor }]} />
      <Text style={[styles.workspaceTonePillText, { color: baseColor }]} numberOfLines={1}>
        {label}
      </Text>
    </View>
  );
}

function AnalysisWorkspaceIntro({
  asset,
  assets,
  intelligence,
  onAskFinn,
  onSelect,
  selectedSymbol,
  stale,
}: {
  asset: MobileOverviewAsset;
  assets: MobileOverviewAsset[];
  intelligence: AssetIntelligence;
  onAskFinn: () => void;
  onSelect: (symbol: string) => void;
  selectedSymbol: string;
  stale: boolean;
}) {
  const { appearance } = useAppPreferences();
  const colors = preferenceColors(appearance);
  const combined = compositeScore(asset);
  const steps = [
    { id: '1', title: 'Asset', body: 'What am I analysing?', icon: 'search' as const },
    { id: '2', title: 'Evidence', body: 'What do Market, Macro and Technical show?', icon: 'bar-chart-2' as const },
    { id: '3', title: 'Conclusion', body: 'What does this mean for my plan?', icon: 'sun' as const },
  ];
  const summaryItems = [
    { label: 'Bias', value: intelligence.marketPosture },
    { label: 'Combined', value: `${combined}/100` },
    { label: 'Confidence', value: `${Math.max(35, Math.min(95, combined + 8))}%` },
  ];
  const assetLine = `${asset.symbol} · ${assetNameForSymbol(asset.symbol)}`;

  return (
    <CardShell emphasis="standard" flat style={styles.workspaceBlendSurface}>
      <View style={styles.sectionTop}>
        <View style={styles.sectionLead}>
          <Text style={styles.kicker}>Analysis workspace</Text>
          <Text style={[styles.workspaceTitle, { color: colors.text }]}>Analysis</Text>
          <Text style={[styles.workspaceSubtitle, { color: colors.textMuted }]}>
            Research one asset with market, macro and technical evidence.
          </Text>
        </View>
        <View style={[styles.sectionMetaPill, { backgroundColor: `${theme.colors.success}14` }]}>
          <Text style={[styles.inlineMetaLabel, styles.sectionMetaBadgeText, { color: theme.colors.success }]}>
            Active
          </Text>
        </View>
      </View>

      <ScrollView
        horizontal
        showsHorizontalScrollIndicator={false}
        contentContainerStyle={styles.workflowSteps}
        style={styles.workflowRail}
      >
        {steps.map((step, index) => (
          <View
            key={step.id}
            style={[
              styles.workflowStepCard,
              {
                backgroundColor: colors.surface,
                borderColor: colors.borderSubtle,
                marginRight: index === steps.length - 1 ? 0 : 12,
              },
            ]}
          >
            <View style={[styles.workflowIconTile, { backgroundColor: `${colors.accent}10` }]}>
              <Feather color={theme.colors.accent} name={step.icon} size={18} />
            </View>
            <View style={styles.workflowStepCopy}>
              <Text style={styles.workflowStepTitle}>{step.id} {step.title}</Text>
              <Text style={[styles.workflowStepBody, { color: colors.textMuted }]} numberOfLines={2}>
                {step.body}
              </Text>
            </View>
          </View>
        ))}
      </ScrollView>

      <View style={[styles.workspacePanelDivider, { backgroundColor: colors.borderSubtle }]} />

      <View
        style={[
          styles.activeAnalysisShell,
          { backgroundColor: colors.surfaceMuted, borderColor: colors.borderSubtle },
        ]}
      >
        <View style={styles.activeAnalysisTop}>
          <Text style={styles.kicker}>Active analysis</Text>
          <Text style={[styles.updatedMeta, { color: colors.textDim }]}>Updated offline</Text>
        </View>

        <Text style={[styles.activeAnalysisAssetLine, { color: colors.textDim }]}>{assetLine}</Text>

        <View style={styles.activeAnalysisRow}>
          <View style={styles.activeAnalysisLeft}>
            <Pressable style={[styles.assetPill, { borderColor: colors.borderSubtle, backgroundColor: colors.surface }]}>
              <Text style={[styles.assetPillText, { color: colors.text }]}>{asset.symbol}</Text>
            </Pressable>
            <Text style={[styles.activeAnalysisPrice, { color: colors.text }]}>{intelligence.price}</Text>
            <Text style={[styles.activeAnalysisChange, { color: colorForTone(intelligence.changeTone) }]}>{intelligence.change}</Text>
            <Text style={[styles.activeAnalysisTf, { color: colors.textDim }]}>1D</Text>
          </View>

          <View
            style={[
              styles.activeAnalysisSummary,
              { backgroundColor: colors.surface, borderColor: colors.borderSubtle },
            ]}
          >
            {summaryItems.map((item) => (
              <View key={item.label} style={styles.activeAnalysisSummaryItem}>
                <Text style={styles.activeAnalysisSummaryLabel} numberOfLines={1}>{item.label}</Text>
                <Text style={[styles.activeAnalysisSummaryValue, { color: colors.text }]} numberOfLines={2}>{item.value}</Text>
              </View>
            ))}
          </View>
        </View>
      </View>

      <View style={[styles.workspacePanelDivider, { backgroundColor: colors.borderSubtle }]} />

      <View style={styles.watchlistTop}>
        <View style={styles.watchlistTopLeft}>
          <Text style={styles.kicker}>Watchlist</Text>
          <View style={styles.watchlistGroupRow}>
            <View
              style={[
                styles.watchlistGroupChip,
                styles.watchlistGroupChipActive,
                { backgroundColor: `${colors.accent}10`, borderColor: `${colors.accent}24` },
              ]}
            >
              <Text style={styles.watchlistGroupChipActiveText}>Crypto</Text>
            </View>
            <View style={[styles.watchlistGroupChip, { backgroundColor: colors.surfaceMuted }]}>
              <Text style={[styles.watchlistGroupChipText, { color: colors.textDim }]}>Stocks</Text>
            </View>
            <View style={[styles.watchlistGroupChip, { backgroundColor: colors.surfaceMuted }]}>
              <Text style={[styles.watchlistGroupChipText, { color: colors.textDim }]}>ETF</Text>
            </View>
          </View>
        </View>
        <StatusChip label={stale ? 'Stale' : 'Live'} tone={stale ? 'warning' : 'success'} />
      </View>

      <View style={[styles.watchlistTable, { borderColor: colors.borderSubtle }]}>
        {assets.map((asset) => {
          const active = asset.symbol === selectedSymbol;
          const score = compositeScore(asset);
          const change = asset.change_24h ?? 0;
          return (
            <Pressable
              key={asset.symbol}
              onPress={() => onSelect(asset.symbol)}
              style={({ pressed }) => [
                styles.watchlistRow,
                {
                  borderBottomColor: colors.borderSubtle,
                  backgroundColor: active ? `${colors.accent}08` : 'transparent',
                },
                pressed && styles.pressed,
              ]}
            >
              <View style={styles.watchlistRowTop}>
                <View style={styles.watchlistAssetBlock}>
                  <View style={[styles.watchlistDot, { backgroundColor: active ? theme.colors.accent : colors.borderStrong }]} />
                  <View style={styles.watchlistAssetText}>
                    <Text style={[styles.watchlistSymbol, { color: colors.text }]}>{asset.symbol}</Text>
                    <Text style={[styles.watchlistName, { color: colors.textDim }]}>{assetNameForSymbol(asset.symbol)}</Text>
                  </View>
                </View>
                <View style={styles.watchlistPriceBlock}>
                  <Text style={[styles.watchlistPrice, { color: colors.text }]}>
                    {typeof asset.price === 'number' ? formatShortPrice(asset.price) : 'n/a'}
                  </Text>
                  <Text
                    style={[
                      styles.watchlistChange,
                      { color: change >= 0 ? theme.colors.success : theme.colors.danger },
                    ]}
                  >
                    {formatSignedPercent(change)}
                  </Text>
                </View>
              </View>

              <View style={styles.watchlistRowBottom}>
                <View style={styles.watchlistMetaLeft}>
                  <Text style={[styles.watchlistScore, { color: colors.textMuted }]}>Score: {score}</Text>
                  <StatusChip compact label={stateForAsset(asset)} tone={toneForScore(score)} />
                </View>
                {active ? <View style={[styles.watchlistActiveMarker, { backgroundColor: theme.colors.accent }]} /> : null}
              </View>
            </Pressable>
          );
        })}
      </View>
    </CardShell>
  );
}

function AnalysisPlanBridge({
  candidate,
  onOpenPlan,
}: {
  candidate: { action: string; name: string; score: number; summary: string } | null;
  onOpenPlan: () => void;
}) {
  const { appearance } = useAppPreferences();
  const colors = preferenceColors(appearance);

  if (!candidate) return null;

  return (
    <Pressable
      onPress={async () => {
        await triggerHaptic('selection');
        onOpenPlan();
      }}
      style={({ pressed }) => [styles.planBridge, { borderColor: colors.borderSubtle }, pressed && styles.pressed]}
    >
      <View style={styles.planBridgeContent}>
        <View style={styles.planBridgeCopy}>
          <Text style={styles.kicker}>Next step</Text>
          <Text style={[styles.cardTitle, { color: colors.text }]}>Open My Plan</Text>
          <Text style={[styles.bodyText, { color: colors.textMuted }]}>
            {candidate.name} is the best matching plan for current conditions. {candidate.summary}
          </Text>
        </View>
        <View style={styles.planBridgeSide}>
          <Text style={styles.planBridgeScore}>{candidate.score}/100</Text>
          <Pressable onPress={onOpenPlan} style={styles.planBridgeButton}>
            <Text style={styles.planBridgeButtonText}>{candidate.action}</Text>
          </Pressable>
        </View>
      </View>
    </Pressable>
  );
}

function AnalysisRegimeCard({
  change,
  finnSummary,
  posture,
  postureTone,
  riskState,
  riskTone,
  symbol,
}: {
  change: string;
  finnSummary: string;
  posture: string;
  postureTone: StatusTone;
  riskState: string;
  riskTone: StatusTone;
  symbol: string;
}) {
  const { appearance } = useAppPreferences();
  const colors = preferenceColors(appearance);

  return (
    <CardShell emphasis="standard" flat style={styles.workspaceBlendSurface}>
      <View style={styles.sectionTop}>
        <View>
          <Text style={styles.kicker}>Market regime</Text>
          <Text style={[styles.cardTitle, { color: colors.text }]}>{symbol} control plane</Text>
        </View>
        <StatusChip label={change} tone={change.startsWith('+') ? 'success' : 'danger'} />
      </View>
      <View style={styles.analysisMetaRow}>
        <View style={[styles.analysisMetaCard, { borderColor: colors.border, backgroundColor: colors.backgroundSoft }]}>
          <Text style={styles.analysisMetaLabel}>Posture</Text>
          <Text style={[styles.analysisMetaValue, { color: colorForTone(postureTone) }]}>{posture}</Text>
        </View>
        <View style={[styles.analysisMetaCard, { borderColor: colors.border, backgroundColor: colors.backgroundSoft }]}>
          <Text style={styles.analysisMetaLabel}>Risk</Text>
          <Text style={[styles.analysisMetaValue, { color: colorForTone(riskTone) }]}>{riskState}</Text>
        </View>
      </View>
      <Text style={[styles.bodyText, { color: colors.textMuted }]}>{finnSummary}</Text>
    </CardShell>
  );
}

function AnalysisFinnActions({
  onAskContext,
  onAskSetup,
}: {
  onAskContext: () => void;
  onAskSetup: () => void;
}) {
  const { appearance } = useAppPreferences();
  const colors = preferenceColors(appearance);

  return (
    <View style={styles.analysisActionWrap}>
      <Pressable onPress={onAskContext} style={[styles.analysisActionPrimary, { backgroundColor: theme.colors.accent }]}>
        <Text style={styles.analysisActionPrimaryText}>Ask FINN for context</Text>
      </Pressable>
      <Pressable onPress={onAskSetup} style={[styles.analysisActionSecondary, { borderColor: colors.borderStrong, backgroundColor: colors.surface }]}>
        <Text style={[styles.analysisActionSecondaryText, { color: colors.text }]}>Review setup evidence</Text>
      </Pressable>
    </View>
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
    <CardShell emphasis="primary">
      <View style={styles.intelTop}>
        <View style={styles.assetIdentity}>
          <AssetIcon symbol={intelligence.symbol} />
          <View>
            <Text style={styles.intelLabel}>Analysis briefing</Text>
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
        <MiniMetric label="Marktbeeld" value={intelligence.marketPosture} tone={intelligence.marketPostureTone} />
      </View>
    </CardShell>
  );
}

function AnalysisEvidenceGrid({ asset }: { asset: MobileOverviewAsset }) {
  const { appearance } = useAppPreferences();
  const colors = preferenceColors(appearance);
  const sections = [
    {
      key: 'macro',
      label: 'Macro',
      score: Math.round(asset.macro_score),
      summary: asset.macro_label || 'Macro context from the active workspace.',
      tone: toneForScore(asset.macro_score),
    },
    {
      key: 'market',
      label: 'Market',
      score: Math.round(asset.market_score),
      summary: asset.market_label || 'Market evidence and flow confirmation.',
      tone: toneForScore(asset.market_score),
    },
    {
      key: 'technical',
      label: 'Technical',
      score: Math.round(asset.technical_score),
      summary: asset.technical_label || 'Trend and momentum confirmation.',
      tone: toneForScore(asset.technical_score),
    },
    {
      key: 'setup',
      label: 'Setup',
      score: Math.round(asset.setup_score),
      summary: stateForAsset(asset),
      tone: toneForScore(asset.setup_score),
    },
  ];

  return (
    <View style={styles.evidenceGrid}>
      {sections.map((section) => (
        <View
          key={section.key}
          style={[
            styles.evidenceCard,
            { backgroundColor: colors.backgroundSoft, borderColor: colors.border },
          ]}
        >
          <View style={styles.evidenceTop}>
            <Text style={styles.evidenceLabel}>{section.label}</Text>
            <StatusChip compact label={String(section.score)} tone={section.tone} />
          </View>
          <Text style={[styles.evidenceText, { color: colors.textMuted }]}>{section.summary}</Text>
        </View>
      ))}
    </View>
  );
}

function AnalysisEvidenceSections({
  asset,
  workspaceAsset,
}: {
  asset: MobileOverviewAsset;
  workspaceAsset?: WorkspaceAssetResponse;
}) {
  const { language } = useAppPreferences();
  const sections = buildEvidenceSections(workspaceAsset);

  if (sections.length === 0) {
    return (
      <InsightCard
        label="Analysis"
        title={translate(language, 'analysis.evidenceUnavailableHeadline')}
        body={translate(language, 'analysis.evidenceUnavailableBody')}
        tone="warning"
      />
    );
  }

  return (
    <View style={styles.analysisSection}>
      {sections.map((section, index) => (
        <AnalysisEvidenceSectionCard
          key={section.key}
          section={section}
          isLastSection={index === sections.length - 1}
        />
      ))}
    </View>
  );
}

function AnalysisEvidenceSectionCard({
  isLastSection,
  section,
}: {
  isLastSection: boolean;
  section: {
    key: string;
    title: string;
    score: number;
    summary: string;
    rows: Array<{ label: string; value: string; development: string; assessment: string; tone: StatusTone }>;
  };
}) {
  const { appearance } = useAppPreferences();
  const colors = preferenceColors(appearance);

  return (
    <CardShell emphasis="standard" flat style={styles.workspaceBlendSurface}>
      <View style={styles.sectionTop}>
        <View>
          <Text style={styles.kicker}>{section.title} evidence</Text>
          <View style={styles.evidenceSectionTitleRow}>
            <Text style={[styles.workspaceTitle, { color: colors.text }]}>{section.title}</Text>
            <View
              style={[
                styles.evidenceScorePill,
                {
                  backgroundColor: `${colorForTone(toneForScore(section.score))}12`,
                },
              ]}
            >
              <Text style={[styles.evidenceScorePillText, { color: colorForTone(toneForScore(section.score)) }]}>
                {section.score}/100
              </Text>
            </View>
          </View>
          <Text style={[styles.workspaceSubtitle, { color: colors.textMuted }]}>{section.summary}</Text>
        </View>
      </View>

      <ScrollView
        horizontal
        showsHorizontalScrollIndicator={false}
        contentContainerStyle={styles.evidenceTimeframeRow}
        style={styles.evidenceTimeframeRail}
      >
          {['Day', 'Week', 'Month', 'Quarter'].map((item, index) => (
            <View
              key={item}
              style={[
                styles.evidenceTimeframeChip,
                index === 0
                  ? [
                      styles.evidenceTimeframeChipActive,
                      { backgroundColor: `${colors.accent}10`, borderColor: `${colors.accent}24` },
                    ]
                  : { borderColor: colors.borderSubtle, backgroundColor: 'transparent' },
              ]}
            >
              <Text style={index === 0 ? styles.evidenceTimeframeChipActiveText : [styles.evidenceTimeframeChipText, { color: colors.textDim }]}>{item}</Text>
            </View>
          ))}
      </ScrollView>

      <View style={[styles.evidenceTable, { borderColor: colors.borderSubtle }]}>
        {section.rows.map((row, index) => (
          <View
            key={`${section.key}-${row.label}`}
            style={[
              styles.evidenceMobileRow,
              index < section.rows.length - 1 && { borderBottomColor: colors.borderSubtle, borderBottomWidth: 1 },
              index === section.rows.length - 1 && isLastSection && styles.evidenceLastRow,
            ]}
          >
            <View style={styles.evidenceMobileTop}>
              <Text style={[styles.evidenceMobileLabel, { color: colors.text }]}>{row.label}</Text>
              <Text style={[styles.evidenceMobileValue, { color: colors.text }]}>{row.value}</Text>
            </View>
            <Text style={[styles.evidenceMobileAssessment, { color: colors.textMuted }]}>{row.assessment}</Text>
            <View style={styles.evidenceMobileBottom}>
              <StatusChip compact label={row.development} tone={row.tone} />
            </View>
          </View>
        ))}
      </View>
    </CardShell>
  );
}

function HistoricalForwardReturnsCard({
  asset,
  rows,
}: {
  asset: MobileOverviewAsset;
  rows: ForwardReturnChartResponse[];
}) {
  const { appearance } = useAppPreferences();
  const { language } = useAppPreferences();
  const colors = preferenceColors(appearance);
  const matrix = buildForwardReturnMatrix(rows);

  if (!matrix) {
    return (
      <InsightCard
        label={`${asset.symbol} · Market`}
        title={translate(language, 'analysis.forwardReturnsUnavailableHeadline')}
        body={translate(language, 'analysis.forwardReturnsUnavailableBody')}
        tone="warning"
      />
    );
  }

  return (
    <CardShell emphasis="standard" flat style={styles.workspaceBlendSurface}>
      <View>
        <Text style={styles.kicker}>{asset.symbol} · Market</Text>
        <Text style={[styles.workspaceTitle, { color: colors.text }]}>Historical forward returns</Text>
        <Text style={[styles.workspaceSubtitle, { color: colors.textMuted }]}>
          Compare recurring returns by week, month, quarter and year.
        </Text>
      </View>

      <View style={styles.forwardTabs}>
        {['Week', 'Month', 'Quarter', 'Year'].map((tab, index) => (
          <View
            key={tab}
            style={[
              styles.forwardTab,
              index === 1 ? styles.forwardTabActive : { borderColor: colors.border, backgroundColor: colors.surface },
            ]}
          >
            <Text style={index === 1 ? styles.forwardTabActiveText : [styles.forwardTabText, { color: colors.textDim }]}>{tab}</Text>
          </View>
        ))}
      </View>

      <View style={[styles.forwardMatrix, { borderColor: colors.borderSubtle }]}>
        <View style={[styles.forwardMatrixHeader, { borderBottomColor: colors.borderSubtle }]}>
          <Text style={[styles.forwardMatrixHeadCell, styles.forwardYearCell]}>Year</Text>
          {matrix.months.map((month) => (
            <Text key={month} style={styles.forwardMatrixHeadCell}>{month}</Text>
          ))}
          <Text style={styles.forwardMatrixHeadCell}>Avg.</Text>
        </View>
        {matrix.rows.map((row, rowIndex) => (
          <View key={row.label} style={[styles.forwardMatrixRow, rowIndex < matrix.rows.length - 1 && { borderBottomColor: colors.borderSubtle, borderBottomWidth: 1 }]}>
            <Text style={[styles.forwardMatrixYear, { color: colors.text }]}>{row.label}</Text>
            {row.values.map((value, index) => (
              <View
                key={`${row.label}-${index}`}
                style={[
                  styles.forwardMatrixValueCell,
                  value === null
                    ? { backgroundColor: colors.surfaceMuted }
                    : value >= 0
                      ? styles.forwardPositiveCell
                      : styles.forwardNegativeCell,
                ]}
              >
                <Text
                  style={[
                    styles.forwardMatrixValueText,
                    {
                      color:
                        value === null
                          ? colors.textDim
                          : value >= 0
                            ? '#166534'
                            : '#991B1B',
                    },
                  ]}
                >
                  {value === null ? '—' : formatSignedPercent(value)}
                </Text>
              </View>
            ))}
            <Text style={[styles.forwardMatrixAvg, { color: colors.text }]}>{formatSignedPercent(row.average)}</Text>
          </View>
        ))}
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
  const { language } = useAppPreferences();
  const colors = preferenceColors(appearance);

  return (
    <CardShell emphasis="standard" flat style={styles.workspaceBlendSurface}>
      <View style={styles.chartHeader}>
        <View>
          <Text style={styles.kicker}>Tradingview chart</Text>
          <Text style={[styles.chartTitle, { color: colors.text }]}>{symbol}USD</Text>
        </View>
        <Text style={[styles.inlineMetaLabel, { color: colors.textDim }]}>{timeframe.toUpperCase()}</Text>
      </View>

      <SegmentedControl
        compact
        items={timeframes.map((item) => ({ key: item, label: item }))}
        selected={timeframe}
        onChange={(value) => onTimeframeChange(value as Timeframe)}
      />

      {loading ? (
        <LoadingSkeletonCard />
      ) : points.length > 1 ? (
        <NativeCandleChart overlays={overlays} points={points} />
      ) : (
        <InsightCard
          label="Chart"
          title={
            language === 'nl'
              ? 'Er zijn nog geen live chartpunten beschikbaar.'
              : language === 'de'
                ? 'Es sind noch keine Live-Chartpunkte verfügbar.'
                : 'No live chart points are available yet.'
          }
          body={
            language === 'nl'
              ? 'De backend gaf nog niet genoeg markthistorie terug om de analysis chart te tekenen.'
              : language === 'de'
                ? 'Das Backend hat noch nicht genug Markthistorie zurückgegeben, um den Analyse-Chart zu zeichnen.'
                : 'The backend has not returned enough market history yet to draw the analysis chart.'
          }
          tone="warning"
        />
      )}
    </CardShell>
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
            <Text style={styles.terminalLabel}>Marktcontext</Text>
            <Text style={[styles.terminalSubtitle, { color: colors.textMuted }]}>Live watchlist</Text>
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
  const posture = String(asset.posture ?? '').trim() || postureForAsset(asset, latestChange);
  const setupState = setupStateForAsset(asset);
  const riskState = String(asset.risk_state ?? '').trim() || riskStateForAsset(asset, latestChange);
  const headline = String(asset.structure ?? '').trim() || headlineForAsset(asset, latestChange);
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

function buildFallbackOverviewAsset(
  symbol: string,
  latest?: MarketLatestResponse,
  workspaceAsset?: WorkspaceAssetResponse,
): MobileOverviewAsset | null {
  if (!latest && !workspaceAsset) {
    return null;
  }

  const quote = workspaceAsset?.quote;
  const marketScore = readWorkspaceScore(workspaceAsset?.categories?.market?.score?.score) ?? 50;
  const macroScore = readWorkspaceScore(workspaceAsset?.categories?.macro?.score?.score) ?? 50;
  const technicalScore = readWorkspaceScore(workspaceAsset?.categories?.technical?.score?.score) ?? 50;
  const combinedScore = readWorkspaceScore(workspaceAsset?.combined?.score) ?? Math.round((marketScore + macroScore + technicalScore) / 3);
  const latestRecord = latest && typeof latest === 'object' ? latest : undefined;
  const resolvedSymbol = String(workspaceAsset?.symbol || latestRecord?.symbol || symbol || 'BTC').toUpperCase();

  return {
    symbol: resolvedSymbol,
    price: readNumber(latestRecord, ['price'], typeof quote?.price === 'number' ? quote.price : 0) || null,
    change_24h:
      readNumber(latestRecord, ['change_24h'], typeof quote?.change_24h === 'number' ? quote.change_24h : 0) || 0,
    macro_score: macroScore,
    technical_score: technicalScore,
    market_score: marketScore,
    setup_score: combinedScore,
    macro_label: workspaceAsset?.categories?.macro?.score?.status ?? null,
    technical_label: workspaceAsset?.categories?.technical?.score?.status ?? null,
    market_label: workspaceAsset?.categories?.market?.score?.status ?? null,
    posture: workspaceAsset?.combined?.status ?? null,
    structure: null,
    conviction: combinedScore,
    risk_state: null,
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

function deriveSuggestedPlan(source: unknown, asset: MobileOverviewAsset) {
  const setups = Array.isArray((source as { active_setups?: unknown[] } | undefined)?.active_setups)
    ? ((source as { active_setups?: unknown[] }).active_setups ?? [])
    : Array.isArray((source as { data?: unknown[] } | undefined)?.data)
      ? ((source as { data?: unknown[] }).data ?? [])
      : [];

  const match = setups.find((item) => {
    if (!item || typeof item !== 'object') return false;
    const symbol = String((item as Record<string, unknown>).symbol ?? '').toUpperCase();
    return !symbol || symbol === asset.symbol;
  }) as Record<string, unknown> | undefined;

  if (!match) return null;

  const score = Math.round(Number(match.score ?? match.setup_score ?? asset.setup_score ?? 0));
  return {
    action: String(match.action ?? 'Review'),
    name: String(match.setup_name ?? match.name ?? 'Best matching plan'),
    score,
    summary: `Setup score ${score}. Review setup, strategy and bot readiness before execution.`,
  };
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
  return realPoints;
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

function buildEvidenceSections(workspaceAsset?: WorkspaceAssetResponse) {
  return buildWorkspaceEvidenceSections(workspaceAsset);
}

function buildWorkspaceEvidenceSections(workspaceAsset?: WorkspaceAssetResponse) {
  if (!workspaceAsset?.categories) return [];

  const categoryMap = [
    {
      key: 'market',
      title: 'Market',
      summaryFallback: 'The market picture remains mixed and needs confirmation.',
    },
    {
      key: 'macro',
      title: 'Macro',
      summaryFallback: 'Macro context remains mixed and needs confirmation.',
    },
    {
      key: 'technical',
      title: 'Technical',
      summaryFallback: 'Technical picture is workable but not fully confirmed yet.',
    },
  ] as const;

  return categoryMap.map((category) => {
    const payload = workspaceAsset.categories[category.key];

    return {
      key: category.key,
      title: category.title,
      score: readWorkspaceScore(payload?.score?.score) ?? 0,
      summary: deriveWorkspaceSummary(payload, category.summaryFallback),
      rows: (payload?.rows ?? []).map((row) => ({
        label: humanizeIndicatorName(row.name),
        value: formatWorkspaceValue(row.value),
        development: deriveWorkspaceDevelopment(row),
        assessment: deriveWorkspaceAssessment(row),
        tone: deriveWorkspaceTone(row),
      })),
    };
  });
}

function readWorkspaceScore(value: unknown) {
  return typeof value === 'number' && Number.isFinite(value) ? Math.round(value) : null;
}

function deriveWorkspaceSummary(payload: WorkspaceAssetResponse['categories']['market'] | undefined, fallback: string) {
  const firstMeaningfulInterpretation = payload?.rows?.find(
    (row) => typeof row.interpretation === 'string' && row.interpretation.trim(),
  )?.interpretation;
  return firstMeaningfulInterpretation?.trim() || fallback;
}

function deriveWorkspaceDevelopment(row: WorkspaceAssetResponse['categories']['market']['rows'][number]) {
  const trend = typeof row.trend === 'string' ? row.trend.trim() : '';
  if (trend) return humanizeTrend(trend);

  const score = typeof row.score === 'number' ? row.score : null;
  if (score === null) return 'Monitoring';
  if (score >= 70) return 'Improving';
  if (score >= 45) return 'Stable';
  return 'Weakening';
}

function deriveWorkspaceAssessment(row: WorkspaceAssetResponse['categories']['market']['rows'][number]) {
  const interpretation = typeof row.interpretation === 'string' ? row.interpretation.trim() : '';
  const action = typeof row.action === 'string' ? row.action.trim() : '';
  return interpretation || action || 'No assessment available yet.';
}

function deriveWorkspaceTone(row: WorkspaceAssetResponse['categories']['market']['rows'][number]): StatusTone {
  const score = typeof row.score === 'number' ? row.score : null;
  if (score === null) return 'neutral';
  return toneForScore(score);
}

function formatWorkspaceValue(value: unknown) {
  if (typeof value === 'number' && Number.isFinite(value)) {
    if (Math.abs(value) <= 100 && !Number.isInteger(value)) {
      return formatSignedPercent(value);
    }
    if (Math.abs(value) >= 1000) {
      return formatCompact(value);
    }
    return Number.isInteger(value) ? `${value}` : value.toFixed(2);
  }

  if (typeof value === 'string' && value.trim()) {
    return value.trim();
  }

  return 'n/a';
}

function humanizeTrend(trend: string) {
  const normalized = trend.toLowerCase();
  if (normalized.includes('verbeter') || normalized.includes('improv')) return 'Improving';
  if (normalized.includes('stab')) return 'Stable';
  if (normalized.includes('zwak') || normalized.includes('weak')) return 'Weakening';
  if (normalized.includes('neut')) return 'Neutral';
  if (normalized.includes('laag')) return 'Low';

  return trend
    .split(/[_\s-]+/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(' ');
}

function humanizeIndicatorName(name: string) {
  const dictionary: Record<string, string> = {
    btc_dominance: 'Bitcoin dominance',
    change_24h: '24-hour price change',
    fear_greed_index: 'Fear & greed',
    ma_200: '200-day moving average',
    rsi: 'RSI',
  };
  if (dictionary[name]) return dictionary[name];

  return name
    .split(/[_\s-]+/)
    .filter(Boolean)
    .map((part) => {
      if (part.toUpperCase() === 'RSI') return 'RSI';
      return part.charAt(0).toUpperCase() + part.slice(1);
    })
    .join(' ');
}

function buildForwardReturnMatrix(rows: ForwardReturnChartResponse[]) {
  if (!rows.length) return null;

  const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  const normalizedRows = rows
    .filter((row) => Array.isArray(row.values) && row.values.some((value: number | null) => typeof value === 'number'))
    .map((row) => {
      const values = months.map((_, index) => {
        const value = row.values[index];
        return typeof value === 'number' && Number.isFinite(value) ? Number(value.toFixed(1)) : null;
      });
      return {
        average: average(values),
        label: `${row.year}`,
        values,
      };
    });

  if (!normalizedRows.length) return null;

  const averageRow = months.map((_, index) =>
    average(normalizedRows.map((row) => row.values[index])),
  );

  return {
    months,
    rows: [
      ...normalizedRows,
      {
        average: average(averageRow),
        label: 'AVG.',
        values: averageRow,
      },
    ],
  };
}

function average(values: Array<number | null>) {
  const valid = values.filter((value): value is number => typeof value === 'number' && Number.isFinite(value));
  if (!valid.length) return 0;
  return Number((valid.reduce((sum, value) => sum + value, 0) / valid.length).toFixed(1));
}

function assetNameForSymbol(symbol: string) {
  if (symbol === 'BTC') return 'Bitcoin';
  if (symbol === 'ETH') return 'Ethereum';
  if (symbol === 'SOL') return 'Solana';
  return 'Asset context';
}

function formatSignedPercent(value: number) {
  return `${value >= 0 ? '+' : ''}${value.toFixed(1)}%`;
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
  analysisActionPrimary: {
    alignItems: 'center',
    borderRadius: theme.radius.button,
    justifyContent: 'center',
    minHeight: 52,
    paddingHorizontal: theme.spacing.lg,
  },
  analysisActionPrimaryText: {
    color: theme.colors.white,
    fontSize: 12,
    fontWeight: '900',
    letterSpacing: 1.2,
    textTransform: 'uppercase',
  },
  analysisActionSecondary: {
    alignItems: 'center',
    borderRadius: theme.radius.button,
    borderWidth: 1,
    justifyContent: 'center',
    minHeight: 48,
    paddingHorizontal: theme.spacing.lg,
  },
  analysisActionSecondaryText: {
    fontSize: 12,
    fontWeight: '800',
    letterSpacing: 0.4,
  },
  analysisActionWrap: {
    gap: theme.spacing.sm,
    paddingHorizontal: theme.spacing.lg,
  },
  analysisMetaCard: {
    borderRadius: theme.radius.md,
    borderWidth: 0.5,
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
    backgroundColor: theme.colors.white,
    borderTopColor: theme.colors.borderSubtle,
    borderTopWidth: 1,
    height: 204,
    marginTop: 10,
    overflow: 'hidden',
    paddingLeft: 6,
    paddingTop: 10,
  },
  chartHeader: {
    alignItems: 'center',
    flexDirection: 'row',
    gap: theme.spacing.md,
    justifyContent: 'space-between',
    marginBottom: 8,
  },
  bodyText: {
    fontSize: 14,
    fontWeight: '600',
    lineHeight: 21,
    marginTop: theme.spacing.md,
  },
  compactIntro: {
    fontSize: 12,
    fontWeight: '600',
    lineHeight: 17,
    marginTop: 3,
  },
  cardTitle: {
    fontSize: theme.typography.cardTitle,
    fontWeight: '900',
    marginTop: 4,
  },
  contextScoresBadge: {
    alignItems: 'center',
    borderRadius: theme.radius.pill,
    flexShrink: 0,
    justifyContent: 'center',
    paddingHorizontal: 10,
    paddingVertical: 6,
  },
  contextScoresBadgeText: {
    fontSize: 10,
    fontWeight: '900',
    letterSpacing: 0.8,
    textTransform: 'uppercase',
  },
  contextScoresCard: {
    borderRadius: 22,
    borderWidth: 1,
    paddingHorizontal: 16,
    paddingVertical: 16,
  },
  evidenceCard: {
    borderRadius: theme.radius.md,
    borderWidth: 0.5,
    flexBasis: '48%',
    gap: theme.spacing.sm,
    paddingHorizontal: theme.spacing.md,
    paddingVertical: theme.spacing.md,
  },
  evidenceGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: theme.spacing.sm,
    marginTop: theme.spacing.md,
    paddingHorizontal: theme.spacing.lg,
  },
  evidenceLabel: {
    color: theme.colors.textDim,
    fontSize: theme.typography.label,
    fontWeight: '900',
    letterSpacing: 1.2,
    textTransform: 'uppercase',
  },
  evidenceText: {
    fontSize: 12,
    fontWeight: '600',
    lineHeight: 18,
  },
  evidenceTop: {
    alignItems: 'center',
    flexDirection: 'row',
    gap: theme.spacing.sm,
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
    fontSize: 15,
    fontWeight: '900',
    marginTop: 2,
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
  inlineMetaLabel: {
    fontSize: 10,
    fontWeight: '900',
    letterSpacing: 0.9,
    textTransform: 'uppercase',
  },
  kicker: {
    color: theme.colors.textDim,
    fontSize: 9,
    fontWeight: '900',
    letterSpacing: 1.8,
    textTransform: 'uppercase',
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
  sectionTop: {
    alignItems: 'center',
    flexDirection: 'row',
    gap: 10,
    justifyContent: 'space-between',
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
  scoreOverviewCard: {
    borderRadius: 16,
    borderWidth: 1,
    flex: 1,
    gap: 4,
    minWidth: '47%',
    paddingHorizontal: 12,
    paddingVertical: 12,
  },
  scoreOverviewGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    columnGap: 10,
    marginTop: 12,
    rowGap: 10,
  },
  scoreOverviewLabel: {
    color: theme.colors.textDim,
    fontSize: 10,
    fontWeight: '900',
    letterSpacing: 1,
    textTransform: 'uppercase',
  },
  scoreOverviewValue: {
    fontSize: 15,
    fontWeight: '900',
  },
  scoreStrip: {
    flexDirection: 'row',
    gap: theme.spacing.sm,
    marginTop: theme.spacing.lg,
  },
  planBridge: {
    borderTopWidth: 1,
  },
  planBridgeButton: {
    alignItems: 'center',
    backgroundColor: theme.colors.accent,
    borderRadius: theme.radius.button,
    justifyContent: 'center',
    minHeight: 40,
    minWidth: 104,
    paddingHorizontal: 14,
  },
  planBridgeButtonText: {
    color: theme.colors.white,
    fontSize: 10,
    fontWeight: '900',
    letterSpacing: 0.9,
    textTransform: 'uppercase',
  },
  planBridgeContent: {
    flexDirection: 'row',
    gap: 12,
    paddingHorizontal: 0,
    paddingVertical: 16,
  },
  planBridgeCopy: {
    flex: 1,
    gap: 4,
  },
  planBridgeScore: {
    color: theme.colors.text,
    fontSize: 18,
    fontWeight: '900',
  },
  planBridgeSide: {
    alignItems: 'flex-end',
    gap: 4,
    justifyContent: 'center',
    minWidth: 74,
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
  panelDivider: {
    height: 1,
    marginBottom: 14,
    marginTop: 16,
  },
  volumeBar: {
    borderRadius: 3,
    bottom: 2,
    position: 'absolute',
    width: 8,
  },
  activeAnalysisChange: {
    fontSize: 16,
    fontWeight: '900',
  },
  activeAnalysisAssetLine: {
    fontSize: 11,
    fontWeight: '700',
    letterSpacing: 0.3,
    marginTop: 8,
    textTransform: 'uppercase',
  },
  activeAnalysisLeft: {
    alignItems: 'center',
    flexDirection: 'row',
    flexShrink: 1,
    flexWrap: 'wrap',
    gap: 6,
  },
  activeAnalysisPrice: {
    fontSize: 22,
    fontWeight: '900',
    letterSpacing: -0.4,
  },
  activeAnalysisShell: {
    borderRadius: 24,
    borderWidth: 1,
    marginTop: 2,
    paddingHorizontal: 14,
    paddingVertical: 14,
  },
  activeAnalysisRow: {
    gap: 10,
    marginTop: 10,
  },
  activeAnalysisSummary: {
    flexDirection: 'row',
    gap: 8,
    overflow: 'hidden',
    borderRadius: 18,
    borderWidth: 1,
    paddingHorizontal: 10,
    paddingVertical: 10,
  },
  activeAnalysisSummaryItem: {
    flex: 1,
    gap: 2,
    minHeight: 50,
    minWidth: 0,
    paddingHorizontal: 6,
    paddingVertical: 4,
  },
  activeAnalysisSummaryLabel: {
    color: theme.colors.textDim,
    fontSize: 7.5,
    fontWeight: '900',
    letterSpacing: 0.45,
    textTransform: 'uppercase',
  },
  activeAnalysisSummaryValue: {
    fontSize: 10.5,
    fontWeight: '900',
  },
  activeAnalysisTf: {
    fontSize: 12,
    fontWeight: '900',
    letterSpacing: 1,
    textTransform: 'uppercase',
  },
  activeAnalysisTop: {
    alignItems: 'center',
    flexDirection: 'row',
    justifyContent: 'space-between',
  },
  analysisSection: {
    gap: 8,
  },
  assetPill: {
    alignItems: 'center',
    borderRadius: theme.radius.pill,
    borderWidth: 1,
    flexDirection: 'row',
    gap: theme.spacing.xs,
    paddingHorizontal: 10,
    paddingVertical: 7,
  },
  assetPillText: {
    fontSize: 12,
    fontWeight: '900',
  },
  evidenceMobileAssessment: {
    fontSize: 11.5,
    fontWeight: '500',
    lineHeight: 17,
    marginTop: 2,
  },
  evidenceMobileBottom: {
    alignItems: 'flex-end',
    marginTop: 4,
  },
  evidenceMobileLabel: {
    flex: 1,
    fontSize: 13.5,
    fontWeight: '800',
    lineHeight: 18,
    paddingRight: 8,
  },
  evidenceMobileRow: {
    paddingHorizontal: 2,
    paddingVertical: 9,
  },
  evidenceLastRow: {
    paddingBottom: 176,
  },
  evidenceMobileTop: {
    alignItems: 'flex-start',
    flexDirection: 'row',
    justifyContent: 'space-between',
  },
  evidenceMobileValue: {
    fontSize: 13.5,
    fontWeight: '800',
    marginLeft: 8,
    textAlign: 'right',
  },
  evidenceScorePill: {
    alignItems: 'center',
    borderRadius: theme.radius.pill,
    justifyContent: 'center',
    paddingHorizontal: 10,
    paddingVertical: 5,
  },
  evidenceScorePillText: {
    fontSize: 10,
    fontWeight: '900',
    letterSpacing: 0.6,
  },
  evidenceSectionTitleRow: {
    alignItems: 'center',
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 10,
    marginTop: 4,
  },
  evidenceTable: {
    borderTopWidth: 1,
    marginTop: 8,
    overflow: 'hidden',
  },
  evidenceTimeframeRail: {
    marginTop: 6,
  },
  evidenceTimeframeChip: {
    borderRadius: theme.radius.pill,
    borderWidth: 1,
    paddingHorizontal: 10,
    paddingVertical: 5,
  },
  evidenceTimeframeChipActive: {
    backgroundColor: theme.colors.accentSoft,
    borderColor: '#1D4ED880',
  },
  evidenceTimeframeChipActiveText: {
    color: theme.colors.accent,
    fontSize: 10,
    fontWeight: '900',
    letterSpacing: 0.8,
    textTransform: 'uppercase',
  },
  evidenceTimeframeChipText: {
    fontSize: 10,
    fontWeight: '900',
    letterSpacing: 0.8,
    textTransform: 'uppercase',
  },
  evidenceTimeframeRow: {
    flexDirection: 'row',
    gap: 6,
    paddingRight: 36,
  },
  forwardMatrix: {
    borderTopWidth: 1,
    marginTop: 12,
    overflow: 'hidden',
  },
  forwardMatrixAvg: {
    flex: 0.8,
    fontSize: 11,
    fontWeight: '900',
    textAlign: 'right',
  },
  forwardMatrixHeadCell: {
    color: theme.colors.textDim,
    flex: 1,
    fontSize: 9,
    fontWeight: '900',
    letterSpacing: 0.8,
    textAlign: 'center',
    textTransform: 'uppercase',
  },
  forwardMatrixHeader: {
    flexDirection: 'row',
    gap: 4,
    paddingHorizontal: 10,
    paddingVertical: 9,
  },
  forwardMatrixRow: {
    alignItems: 'center',
    flexDirection: 'row',
    gap: 4,
    paddingHorizontal: 10,
    paddingVertical: 9,
  },
  forwardMatrixValueCell: {
    alignItems: 'center',
    borderRadius: theme.radius.sm,
    flex: 1,
    justifyContent: 'center',
    minHeight: 30,
  },
  forwardMatrixValueText: {
    fontSize: 10,
    fontWeight: '900',
  },
  forwardMatrixYear: {
    flex: 1.1,
    fontSize: 11,
    fontWeight: '900',
  },
  forwardNegativeCell: {
    backgroundColor: '#FEE2E2',
  },
  forwardPositiveCell: {
    backgroundColor: '#DCFCE7',
  },
  forwardTab: {
    borderRadius: theme.radius.pill,
    borderWidth: 1,
    minWidth: 76,
    paddingHorizontal: theme.spacing.md,
    paddingVertical: 10,
  },
  forwardTabActive: {
    backgroundColor: '#F8FAFC',
    borderColor: theme.colors.borderStrong,
  },
  forwardTabActiveText: {
    color: theme.colors.text,
    fontSize: 11,
    fontWeight: '900',
    letterSpacing: 1,
    textAlign: 'center',
    textTransform: 'uppercase',
  },
  forwardTabText: {
    fontSize: 11,
    fontWeight: '900',
    letterSpacing: 1,
    textAlign: 'center',
    textTransform: 'uppercase',
  },
  forwardTabs: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 10,
    marginTop: 12,
  },
  forwardYearCell: {
    flex: 1.1,
    textAlign: 'left',
  },
  missionCard: {
    borderRadius: 22,
    borderWidth: 1,
    paddingHorizontal: 16,
    paddingVertical: 15,
  },
  queueCard: {
    borderRadius: 18,
    borderWidth: 1,
    gap: 6,
    minHeight: 102,
    paddingHorizontal: 12,
    paddingVertical: 12,
    width: '48.3%',
  },
  queueCardBody: {
    fontSize: 12,
    fontWeight: '600',
    lineHeight: 17,
  },
  queueCardLabel: {
    fontSize: 14,
    fontWeight: '700',
  },
  queueCardTop: {
    alignItems: 'flex-start',
    gap: 4,
  },
  queueCardValue: {
    fontSize: 22,
    fontWeight: '900',
  },
  sectionLead: {
    flex: 1,
    minWidth: 0,
    paddingRight: 8,
  },
  sectionMetaBadge: {
    flexShrink: 0,
    marginTop: 0,
  },
  sectionMetaBadgeText: {
    marginTop: 0,
  },
  sectionMetaPill: {
    alignItems: 'center',
    borderRadius: theme.radius.pill,
    justifyContent: 'center',
    minHeight: 26,
    paddingHorizontal: 10,
    paddingVertical: 5,
  },
  queueGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 10,
    justifyContent: 'space-between',
    marginTop: 10,
  },
  queueSurface: {
    marginTop: 10,
  },
  updatedMeta: {
    fontSize: 11,
    fontWeight: '700',
  },
  watchlistAssetBlock: {
    alignItems: 'center',
    flexDirection: 'row',
    flexShrink: 1,
    gap: 10,
  },
  watchlistActiveMarker: {
    borderRadius: theme.radius.pill,
    height: 10,
    width: 10,
  },
  watchlistAssetText: {
    gap: 2,
  },
  watchlistChange: {
    fontSize: 12,
    fontWeight: '800',
    textAlign: 'right',
  },
  watchlistDot: {
    borderRadius: theme.radius.pill,
    height: 12,
    width: 12,
  },
  watchlistGroupChip: {
    borderRadius: theme.radius.pill,
    paddingHorizontal: theme.spacing.sm,
    paddingVertical: 6,
  },
  watchlistGroupChipActive: {
    backgroundColor: theme.colors.accentSoft,
    borderColor: '#1D4ED880',
  },
  watchlistGroupChipActiveText: {
    color: theme.colors.accent,
    fontSize: 10,
    fontWeight: '900',
    letterSpacing: 0.8,
    textTransform: 'uppercase',
  },
  watchlistGroupChipText: {
    fontSize: 10,
    fontWeight: '900',
    letterSpacing: 0.8,
    textTransform: 'uppercase',
  },
  watchlistGroupRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 6,
  },
  watchlistMetaLeft: {
    alignItems: 'center',
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
  },
  watchlistMetaRight: {
    fontSize: 11,
    fontWeight: '700',
  },
  watchlistName: {
    fontSize: 13,
    fontWeight: '600',
  },
  watchlistPrice: {
    fontSize: 16,
    fontWeight: '900',
    textAlign: 'right',
  },
  watchlistPriceBlock: {
    alignItems: 'flex-end',
    gap: 4,
    marginLeft: 12,
  },
  watchlistRow: {
    gap: 10,
    paddingHorizontal: 16,
    paddingVertical: 14,
  },
  watchlistRowBottom: {
    alignItems: 'center',
    flexDirection: 'row',
    justifyContent: 'space-between',
    paddingLeft: 16,
  },
  watchlistRowTop: {
    alignItems: 'center',
    flexDirection: 'row',
    justifyContent: 'space-between',
  },
  watchlistScore: {
    fontSize: 11,
    fontWeight: '700',
  },
  watchlistSymbol: {
    fontSize: 17,
    fontWeight: '900',
  },
  watchlistTable: {
    borderTopWidth: 1,
    marginHorizontal: 0,
    marginTop: 12,
    overflow: 'hidden',
  },
  watchlistTop: {
    alignItems: 'center',
    flexDirection: 'row',
    justifyContent: 'space-between',
  },
  watchlistTopLeft: {
    gap: 6,
  },
  workflowRail: {
    marginTop: 10,
  },
  workflowStepBody: {
    fontSize: 10.5,
    fontWeight: '600',
    lineHeight: 15,
  },
  workflowIconTile: {
    alignItems: 'center',
    borderRadius: 12,
    height: 34,
    justifyContent: 'center',
    width: 34,
  },
  workflowSteps: {
    paddingRight: 34,
  },
  workflowStepCard: {
    borderRadius: 18,
    borderWidth: 1,
    flexDirection: 'row',
    gap: 10,
    minHeight: 74,
    paddingHorizontal: 11,
    paddingVertical: 11,
    width: 224,
  },
  workflowStepCopy: {
    flex: 1,
    gap: 3,
    justifyContent: 'center',
  },
  workflowStepTitle: {
    color: theme.colors.accent,
    fontSize: 12,
    fontWeight: '900',
  },
  workspaceChipRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
    marginTop: 12,
  },
  workspaceGreeting: {
    fontSize: 14,
    fontWeight: '600',
    marginTop: 8,
  },
  workspaceHeadline: {
    fontSize: 15,
    fontWeight: '900',
    lineHeight: 22,
    marginTop: 6,
  },
  workspacePrimaryAction: {
    alignItems: 'center',
    backgroundColor: theme.colors.accent,
    borderRadius: theme.radius.button,
    marginTop: 12,
    paddingHorizontal: 15,
    paddingVertical: 12,
  },
  workspacePrimaryActionWide: {
    alignSelf: 'stretch',
  },
  workspacePrimaryActionText: {
    color: theme.colors.white,
    fontSize: 11,
    fontWeight: '900',
    letterSpacing: 0.9,
    textTransform: 'uppercase',
  },
  workspacePanelDivider: {
    height: 1,
    marginBottom: 14,
    marginTop: 14,
  },
  workspaceBlendSurface: {
    marginHorizontal: 0,
    paddingHorizontal: 8,
    paddingVertical: 6,
  },
  workspaceSurface: {
    borderRadius: 26,
    marginHorizontal: 0,
    paddingHorizontal: 8,
    paddingVertical: 14,
  },
  workspaceSecondaryAction: {
    alignItems: 'center',
    alignSelf: 'flex-start',
    borderRadius: theme.radius.button,
    borderWidth: 1,
    marginTop: 12,
    paddingHorizontal: theme.spacing.lg,
    paddingVertical: 11,
  },
  workspaceSecondaryActionText: {
    fontSize: 12,
    fontWeight: '900',
    letterSpacing: 0.8,
    textTransform: 'uppercase',
  },
  workspaceSubtitle: {
    fontSize: 14,
    fontWeight: '600',
    lineHeight: 19,
    marginTop: 6,
  },
  workspaceSupport: {
    fontSize: 13,
    fontWeight: '600',
    marginTop: 10,
  },
  workspaceTonePill: {
    alignItems: 'center',
    alignSelf: 'flex-start',
    borderRadius: theme.radius.pill,
    flexDirection: 'row',
    gap: 6,
    maxWidth: '100%',
    paddingHorizontal: 10,
    paddingVertical: 7,
  },
  workspaceTonePillDot: {
    borderRadius: theme.radius.pill,
    height: 5,
    width: 5,
  },
  workspaceTonePillText: {
    fontSize: 8.5,
    fontWeight: '900',
    letterSpacing: 0.8,
    textTransform: 'uppercase',
  },
  workspaceTitle: {
    fontSize: 15,
    fontWeight: '900',
    marginTop: 3,
  },
  wick: {
    borderRadius: 2,
    position: 'absolute',
    width: 2,
  },
});
