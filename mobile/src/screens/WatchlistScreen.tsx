import { useCallback, useEffect, useMemo, useState } from 'react';
import { Feather } from '@expo/vector-icons';
import { useNavigation } from '@react-navigation/native';
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';

import { AssetIcon } from '../components/assets/AssetIcon';
import { CardShell } from '../components/cards/CardShell';
import { InsightCard } from '../components/cards/InsightCard';
import { LoadingSkeletonCard } from '../components/layout/LoadingSkeletonCard';
import { ScreenContainer } from '../components/layout/ScreenContainer';
import { StatusChip } from '../components/layout/StatusChip';
import { SwipeActionRow } from '../components/rows/SwipeActionRow';
import { BottomSheet } from '../components/sheets/BottomSheet';
import { ConfirmDestructiveSheetContent, RowActionSheetContent } from '../components/sheets/RowActionSheetContent';
import { TradingViewWidget } from '../components/charts/TradingViewWidget';
import { TodayWithFinnCard } from '../components/workspace/TodayWithFinnCard';
import { WorkflowStepsRail } from '../components/workspace/WorkflowStepsRail';
import { WorkspaceHeroSection } from '../components/workspace/WorkspaceHeroSection';
import { listRowStandards } from '../constants/listRows';
import { StatusTone, theme } from '../constants/theme';
import { typography } from '../constants/typography';
import { useApiResource } from '../hooks/useApiResource';
import { localizedBackendText, translate } from '../i18n';
import type { MainTabParamList } from '../navigation/MainTabNavigator';
import { preferenceColors, useAppPreferences } from '../preferences/AppPreferencesProvider';
import {
  IntelligenceWeightsPayload,
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
import {
  ANALYSIS_CHART_INTERVAL_KEY,
  DEFAULT_TRADINGVIEW_INTERVAL,
  normalizeTradingViewInterval,
  type TradingViewInterval,
} from '../lib/tradingView';
const ANALYSIS_HIDDEN_INDICATORS_KEY = 'analysis_hidden_indicators';

type IntelligenceWeightKey = 'market' | 'macro' | 'technical';

const DEFAULT_INTELLIGENCE_WEIGHTS: IntelligenceWeightsPayload = {
  market: 1 / 3,
  macro: 1 / 3,
  technical: 1 / 3,
};

export function WatchlistScreen() {
  const navigation = useNavigation<any>();
  const { context, updateContext } = useIntelligenceContext();
  const { openFinn } = useFinnOverlay();
  const { language } = useAppPreferences();
  const selectedSymbol = context.asset;
  const [chartInterval, setChartInterval] = useState<TradingViewInterval>(DEFAULT_TRADINGVIEW_INTERVAL);
  const [chartPreferenceLoaded, setChartPreferenceLoaded] = useState(false);
  const [watchlistActionAsset, setWatchlistActionAsset] = useState<MobileOverviewAsset | null>(null);
  const [watchlistRemoveAsset, setWatchlistRemoveAsset] = useState<MobileOverviewAsset | null>(null);
  const [indicatorActionRow, setIndicatorActionRow] = useState<{
    sectionKey: string;
    sectionTitle: string;
    row: { label: string; value: string; development: string; assessment: string; tone: StatusTone };
  } | null>(null);
  const [indicatorDetailRow, setIndicatorDetailRow] = useState<{
    sectionKey: string;
    sectionTitle: string;
    row: { label: string; value: string; development: string; assessment: string; tone: StatusTone };
  } | null>(null);
  const [indicatorRemoveRow, setIndicatorRemoveRow] = useState<{
    sectionKey: string;
    sectionTitle: string;
    row: { label: string; value: string; development: string; assessment: string; tone: StatusTone };
  } | null>(null);
  const [hiddenIndicatorKeys, setHiddenIndicatorKeys] = useState<string[]>([]);

  useEffect(() => {
    trackAssistantEvent({
      event_name: 'screen_view',
      page: 'analysis',
      flow_type: 'analysis',
      asset: selectedSymbol,
    });
  }, [selectedSymbol]);

  useEffect(() => {
    let cancelled = false;

    async function loadHiddenIndicators() {
      try {
        const response = await assistantApi.preferences();
        if (cancelled) return;
        setHiddenIndicatorKeys(normalizeHiddenIndicatorKeys(response?.preferences?.[ANALYSIS_HIDDEN_INDICATORS_KEY]));
        setChartInterval(normalizeTradingViewInterval(response?.preferences?.[ANALYSIS_CHART_INTERVAL_KEY]));
      } catch (error) {
        if (!cancelled) {
          console.warn('Failed to load analysis hidden indicators', error);
        }
      } finally {
        if (!cancelled) {
          setChartPreferenceLoaded(true);
        }
      }
    }

    loadHiddenIndicators();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!chartPreferenceLoaded) return;
    let cancelled = false;

    async function persistChartInterval() {
      try {
        await assistantApi.updatePreferences({
          [ANALYSIS_CHART_INTERVAL_KEY]: chartInterval,
        });
      } catch (error) {
        if (!cancelled) {
          console.warn('Failed to persist analysis chart interval', error);
        }
      }
    }

    void persistChartInterval();
    return () => {
      cancelled = true;
    };
  }, [chartInterval, chartPreferenceLoaded]);

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

  const assets = useMemo(
    () => (overviewResource.data?.watchlist?.filter(Boolean) ?? []).filter((asset) => asset?.symbol),
    [overviewResource.data],
  );
  const derivedAsset = useMemo(
    () => buildFallbackAnalysisAsset(selectedSymbol, latestResource.data, workspaceAssetResource.data),
    [latestResource.data, selectedSymbol, workspaceAssetResource.data],
  );
  const workspaceAssets = useMemo(
    () => (assets.length > 0 ? assets : derivedAsset ? [derivedAsset] : []),
    [assets, derivedAsset],
  );
  const selectedAsset = workspaceAssets.find((asset) => asset.symbol === selectedSymbol) ?? workspaceAssets[0];
  const hasAnalysisBootstrap =
    workspaceAssets.length > 0 ||
    Boolean(overviewResource.data?.watchlist?.length) ||
    Boolean(workspaceAssetResource.data) ||
    Boolean(latestResource.data);

  const fetchChart = useCallback(() => intelligenceApi.marketChart7d(selectedSymbol), [selectedSymbol]);
  const chartResource = useApiResource<MarketChartPoint[]>({
    enabled: hasAnalysisBootstrap,
    fallbackData: [],
    fetcher: fetchChart,
  });
  const fetchTopSetups = useCallback(() => intelligenceApi.topSetups(), []);
  const topSetupsResource = useApiResource({
    enabled: hasAnalysisBootstrap,
    fallbackData: undefined,
    fetcher: fetchTopSetups,
  });
  const fetchForwardReturnsMonth = useCallback(
    () => intelligenceApi.forwardReturnsMonth(selectedSymbol),
    [selectedSymbol],
  );
  const forwardReturnsMonthResource = useApiResource<ForwardReturnChartResponse[]>({
    enabled: hasAnalysisBootstrap,
    fallbackData: [],
    fetcher: fetchForwardReturnsMonth,
  });

  const fetchInsight = useCallback(
    () =>
      assistantApi.insight({
        page_type: 'WATCHLIST',
        symbol: selectedSymbol,
        timeframe: chartInterval,
      }),
    [chartInterval, selectedSymbol],
  );
  const insightResource = useApiResource({
    enabled: hasAnalysisBootstrap,
    fallbackData: undefined,
    fetcher: fetchInsight,
  });

  const intelligence = selectedAsset
    ? buildAssetIntelligence(selectedAsset, latestResource.data, insightResource.data)
    : null;
  const overview = overviewResource.data;
  const hasRenderableAnalysisCore =
    hasAnalysisBootstrap ||
    Boolean(insightResource.data);
  const analysisBootstrapLoading =
    !hasRenderableAnalysisCore &&
    (overviewResource.loading || latestResource.loading || workspaceAssetResource.loading);
  const analysisFallbackError =
    overviewResource.error?.message ||
    latestResource.error?.message ||
    workspaceAssetResource.error?.message ||
    chartResource.error?.message;

  async function selectAsset(symbol: string) {
    await triggerHaptic('selection');
    updateContext({ asset: symbol, screen: 'Analysis' });
  }

  async function openAssetActions(asset: MobileOverviewAsset) {
    await triggerHaptic('selection');
    setWatchlistActionAsset(asset);
  }

  async function openAnalysisAsset(asset: MobileOverviewAsset) {
    setWatchlistActionAsset(null);
    await selectAsset(asset.symbol);
  }

  async function promptRemoveAsset(asset: MobileOverviewAsset) {
    setWatchlistActionAsset(null);
    setWatchlistRemoveAsset(asset);
  }

  async function confirmRemoveAsset() {
    if (!watchlistRemoveAsset) return;

    const symbol = watchlistRemoveAsset.symbol;
    const nextSymbol = workspaceAssets.find((asset) => asset.symbol !== symbol)?.symbol ?? selectedSymbol;

    await intelligenceApi.removeFromWatchlist(symbol);
    setWatchlistRemoveAsset(null);

    if (symbol === selectedSymbol && nextSymbol && nextSymbol !== selectedSymbol) {
      updateContext({ asset: nextSymbol, screen: 'Analysis' });
    }

    overviewResource.refresh();
    latestResource.refresh();
    chartResource.refresh();
    workspaceAssetResource.refresh();
    insightResource.refresh();
    topSetupsResource.refresh();
    forwardReturnsMonthResource.refresh();
  }

  async function openIndicatorDetail(item: {
    sectionKey: string;
    sectionTitle: string;
    row: { label: string; value: string; development: string; assessment: string; tone: StatusTone };
  }) {
    setIndicatorActionRow(null);
    await triggerHaptic('selection');
    setIndicatorDetailRow(item);
  }

  async function openIndicatorActions(item: {
    sectionKey: string;
    sectionTitle: string;
    row: { label: string; value: string; development: string; assessment: string; tone: StatusTone };
  }) {
    await triggerHaptic('selection');
    setIndicatorActionRow(item);
  }

  async function askFinnAboutIndicator(item: {
    sectionKey: string;
    sectionTitle: string;
    row: { label: string; value: string; development: string; assessment: string; tone: StatusTone };
  }) {
    setIndicatorActionRow(null);
    setIndicatorDetailRow(null);
    await triggerHaptic('selection');
    openFinn({
      prefill: `Explain the ${item.row.label} indicator for ${selectedSymbol} in the ${item.sectionTitle} section. Summarize what ${item.row.value} means, why the current state is ${item.row.development}, and what I should monitor next.`,
      source: 'analysis-indicator-row',
      symbol: selectedSymbol,
    });
  }

  function promptHideIndicator(item: {
    sectionKey: string;
    sectionTitle: string;
    row: { label: string; value: string; development: string; assessment: string; tone: StatusTone };
  }) {
    setIndicatorActionRow(null);
    setIndicatorDetailRow(null);
    setIndicatorRemoveRow(item);
  }

  async function confirmHideIndicator() {
    if (!indicatorRemoveRow) return;

    const nextKey = buildIndicatorKey(selectedSymbol, indicatorRemoveRow.sectionKey, indicatorRemoveRow.row.label);
    const nextHiddenKeys = hiddenIndicatorKeys.includes(nextKey) ? hiddenIndicatorKeys : [...hiddenIndicatorKeys, nextKey];

    setHiddenIndicatorKeys(nextHiddenKeys);
    setIndicatorRemoveRow(null);
    await triggerHaptic('warning');

    try {
      await assistantApi.updatePreferences({
        [ANALYSIS_HIDDEN_INDICATORS_KEY]: nextHiddenKeys,
      });
    } catch (error) {
      console.warn('Failed to persist hidden analysis indicators', error);
    }
  }

  return (
    <>
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
          <>
            <AnalysisWorkspaceFallback
              activeSymbol={selectedSymbol}
              onRefreshScores={() => {
                overviewResource.refresh();
                latestResource.refresh();
                chartResource.refresh();
                workspaceAssetResource.refresh();
                insightResource.refresh();
                topSetupsResource.refresh();
                forwardReturnsMonthResource.refresh();
              }}
            />
            <WorkflowStepsRail
              steps={[
                {
                  body: translate(language, 'analysis.workflowStepMarketBody'),
                  icon: 'trending-up',
                  step: 1,
                  title: translate(language, 'analysis.workflowStepMarketTitle'),
                },
                {
                  body: translate(language, 'analysis.workflowStepMacroBody'),
                  icon: 'globe',
                  step: 2,
                  title: translate(language, 'analysis.workflowStepMacroTitle'),
                },
                {
                  body: translate(language, 'analysis.workflowStepTechnicalBody'),
                  icon: 'activity',
                  step: 3,
                  title: translate(language, 'analysis.workflowStepTechnicalTitle'),
                },
              ]}
            />
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
                analysisFallbackError ||
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
          </>
        ) : (
          <>
            <AnalysisWorkspaceMissionControl
              activeSymbol={selectedSymbol}
              assets={workspaceAssets}
              briefing={overview?.finn_briefing}
              intelligence={intelligence!}
              onRefreshScores={() => {
                overviewResource.refresh();
                latestResource.refresh();
                chartResource.refresh();
                workspaceAssetResource.refresh();
                insightResource.refresh();
                topSetupsResource.refresh();
              }}
            />
            <WorkflowStepsRail
              steps={[
                {
                  body: translate(language, 'analysis.workflowStepMarketBody'),
                  icon: 'trending-up',
                  step: 1,
                  title: translate(language, 'analysis.workflowStepMarketTitle'),
                },
                {
                  body: translate(language, 'analysis.workflowStepMacroBody'),
                  icon: 'globe',
                  step: 2,
                  title: translate(language, 'analysis.workflowStepMacroTitle'),
                },
                {
                  body: translate(language, 'analysis.workflowStepTechnicalBody'),
                  icon: 'activity',
                  step: 3,
                  title: translate(language, 'analysis.workflowStepTechnicalTitle'),
                },
              ]}
            />
            <AnalysisWatchlistCard
              assets={workspaceAssets}
              onOpenActions={openAssetActions}
              onOpenAsset={openAnalysisAsset}
              onRemoveAsset={promptRemoveAsset}
              onSelect={selectAsset}
              selectedSymbol={selectedSymbol}
            />
            <CompactLiveChart
              errorMessage={chartResource.error?.message}
              interval={chartInterval}
              symbol={selectedSymbol}
              loading={chartResource.loading}
              onIntervalChange={setChartInterval}
            />
            <AnalysisContextScores
              asset={selectedAsset}
              hiddenIndicatorKeys={hiddenIndicatorKeys}
              intelligence={intelligence!}
              onRefreshScores={() => {
                overviewResource.refresh();
                workspaceAssetResource.refresh();
              }}
              workspaceAsset={workspaceAssetResource.data}
            />
            <AnalysisEvidenceSections
              asset={selectedAsset}
              hiddenIndicatorKeys={hiddenIndicatorKeys}
              onHideIndicator={promptHideIndicator}
              workspaceAsset={workspaceAssetResource.data}
              onAskFinnIndicator={askFinnAboutIndicator}
              onOpenIndicatorActions={openIndicatorActions}
              onOpenIndicatorDetail={openIndicatorDetail}
            />
            <HistoricalForwardReturnsCard asset={selectedAsset} rows={forwardReturnsMonthResource.data} />
          </>
        )}
      </ScreenContainer>

      <BottomSheet
        visible={Boolean(watchlistActionAsset)}
        title={translate(language, 'common.actions')}
        onClose={() => setWatchlistActionAsset(null)}
      >
        <RowActionSheetContent
          actions={
            watchlistActionAsset
              ? [
                  {
                    key: 'open',
                    label: translate(language, 'analysis.assetOpen'),
                    description: translate(language, 'analysis.assetOpenDetail', { symbol: watchlistActionAsset.symbol }),
                    icon: 'arrow-up-right',
                    onPress: () => openAnalysisAsset(watchlistActionAsset),
                  },
                  {
                    key: 'remove',
                    label: translate(language, 'analysis.assetRemove'),
                    description: translate(language, 'analysis.assetRemoveDetail', { symbol: watchlistActionAsset.symbol }),
                    icon: 'trash-2',
                    tone: 'danger',
                    onPress: () => promptRemoveAsset(watchlistActionAsset),
                  },
                ]
              : []
          }
        />
      </BottomSheet>

      <BottomSheet
        visible={Boolean(watchlistRemoveAsset)}
        title={translate(language, 'analysis.assetRemoveConfirmTitle')}
        onClose={() => setWatchlistRemoveAsset(null)}
      >
        {watchlistRemoveAsset ? (
          <ConfirmDestructiveSheetContent
            body={translate(language, 'analysis.assetRemoveConfirmBody', { symbol: watchlistRemoveAsset.symbol })}
            confirmLabel={translate(language, 'common.delete')}
            onConfirm={confirmRemoveAsset}
            title={translate(language, 'analysis.assetRemoveConfirmTitle')}
          />
        ) : null}
      </BottomSheet>

      <BottomSheet
        visible={Boolean(indicatorActionRow)}
        title={translate(language, 'common.actions')}
        onClose={() => setIndicatorActionRow(null)}
      >
        <RowActionSheetContent
          actions={
            indicatorActionRow
              ? [
                  {
                    key: 'open',
                    label: 'Meer info',
                    description: `${indicatorActionRow.row.label} · ${indicatorActionRow.sectionTitle}`,
                    icon: 'arrow-up-right',
                    onPress: () => openIndicatorDetail(indicatorActionRow),
                  },
                  {
                    key: 'finn',
                    label: 'Vraag FINN',
                    description: `Laat FINN ${indicatorActionRow.row.label} kort uitleggen.`,
                    icon: 'message-circle',
                    tone: 'accent',
                    onPress: () => askFinnAboutIndicator(indicatorActionRow),
                  },
                  {
                    key: 'hide',
                    label: 'Verbergen',
                    description: `Verberg ${indicatorActionRow.row.label} uit dit overzicht.`,
                    icon: 'trash-2',
                    tone: 'danger',
                    onPress: () => promptHideIndicator(indicatorActionRow),
                  },
                ]
              : []
          }
        />
      </BottomSheet>

      <BottomSheet
        visible={Boolean(indicatorDetailRow)}
        title={indicatorDetailRow?.row.label ?? 'Indicator'}
        onClose={() => setIndicatorDetailRow(null)}
      >
        {indicatorDetailRow ? (
          <IndicatorDetailSheet
            item={indicatorDetailRow}
            onHide={() => promptHideIndicator(indicatorDetailRow)}
            onAskFinn={() => askFinnAboutIndicator(indicatorDetailRow)}
          />
        ) : null}
      </BottomSheet>

      <BottomSheet
        visible={Boolean(indicatorRemoveRow)}
        title="Indicator verbergen?"
        onClose={() => setIndicatorRemoveRow(null)}
      >
        {indicatorRemoveRow ? (
          <ConfirmDestructiveSheetContent
            body={`Verberg ${indicatorRemoveRow.row.label} uit ${indicatorRemoveRow.sectionTitle}. De externe data blijft bestaan; je haalt hem alleen uit dit mobiele overzicht weg.`}
            confirmLabel={translate(language, 'common.delete')}
            onConfirm={confirmHideIndicator}
            title="Indicator verbergen?"
          />
        ) : null}
      </BottomSheet>
    </>
  );
}

function AnalysisContextScores({
  asset,
  hiddenIndicatorKeys,
  intelligence,
  onRefreshScores,
  workspaceAsset,
}: {
  asset: MobileOverviewAsset;
  hiddenIndicatorKeys: string[];
  intelligence: AssetIntelligence;
  onRefreshScores: () => void;
  workspaceAsset?: WorkspaceAssetResponse;
}) {
  const { appearance, language } = useAppPreferences();
  const colors = preferenceColors(appearance);
  const [tuningVisible, setTuningVisible] = useState(false);
  const [savingWeights, setSavingWeights] = useState(false);
  const visibleScores = buildVisibleWorkspaceScores(asset.symbol, workspaceAsset, hiddenIndicatorKeys);
  const marketScore = visibleScores.market ?? Math.round(asset.market_score);
  const macroScore = visibleScores.macro ?? Math.round(asset.macro_score);
  const technicalScore = visibleScores.technical ?? Math.round(asset.technical_score);
  const combinedScore = visibleScores.combined ?? compositeScore(asset);
  const serverWeights = useMemo(
    () => normalizeIntelligenceWeights(workspaceAsset?.master),
    [workspaceAsset?.master],
  );
  const [localWeights, setLocalWeights] = useState<IntelligenceWeightsPayload>(serverWeights);

  useEffect(() => {
    if (!tuningVisible) {
      setLocalWeights((current) => (
        areIntelligenceWeightsEqual(current, serverWeights) ? current : serverWeights
      ));
    }
  }, [serverWeights, tuningVisible]);

  const items = [
    { label: 'Market', value: marketScore, tone: toneForScore(marketScore) },
    { label: 'Macro', value: macroScore, tone: toneForScore(macroScore) },
    { label: 'Technical', value: technicalScore, tone: toneForScore(technicalScore) },
    { label: 'Combined', value: combinedScore, tone: intelligence.marketPostureTone },
  ];
  const weightItems: Array<{ key: IntelligenceWeightKey; label: string; score: number }> = [
    { key: 'market', label: 'Market', score: marketScore },
    { key: 'macro', label: 'Macro', score: macroScore },
    { key: 'technical', label: 'Technical', score: technicalScore },
  ];
  const totalWeight = Object.values(localWeights).reduce((sum, value) => sum + value, 0);
  const isBalanced = Math.abs(totalWeight - 1) < 0.01;

  const handleWeightChange = (key: IntelligenceWeightKey, nextValue: number) => {
    setLocalWeights((current) => rebalanceIntelligenceWeights(current, key, nextValue));
  };

  const handleOpenTuning = async () => {
    await triggerHaptic('selection');
    setTuningVisible(true);
  };

  const handleSaveWeights = async () => {
    if (savingWeights || !isBalanced) return;
    setSavingWeights(true);
    try {
      await assistantApi.updateIntelligenceWeights(localWeights);
      await onRefreshScores();
      await triggerHaptic('success');
      setTuningVisible(false);
    } catch (error) {
      console.warn('Failed to update intelligence weights', error);
      await triggerHaptic('warning');
    } finally {
      setSavingWeights(false);
    }
  };

  return (
    <>
      <CardShell emphasis="standard" flat style={styles.workspaceBlendSurface}>
        <View style={styles.contextScoresHeader}>
          <Text style={[styles.contextScoresTitle, { color: colors.text }]}>Context scores</Text>
        </View>
        <Pressable
          onPress={handleOpenTuning}
          style={({ pressed }) => [
            styles.contextScoresCard,
            { backgroundColor: colors.surface, borderColor: colors.borderSubtle },
            pressed && styles.contextScoresCardPressed,
          ]}
        >
          <View style={styles.scoreOverviewGrid}>
            {items.map((item, index) => (
              <View
                key={item.label}
                style={[
                  styles.scoreOverviewCard,
                  { borderColor: colors.borderSubtle },
                  index === items.length - 1 && styles.scoreOverviewCardLast,
                ]}
              >
                <Text style={styles.scoreOverviewLabel}>{item.label}</Text>
                <Text style={[styles.scoreOverviewValue, { color: colorForTone(item.tone) }]}>{item.value}/100</Text>
              </View>
            ))}
          </View>
        </Pressable>
      </CardShell>

      <BottomSheet
        visible={tuningVisible}
        title="Score tuning"
        onClose={() => setTuningVisible(false)}
      >
        <View style={[styles.contextTuningPanel, { borderColor: colors.borderSubtle, backgroundColor: colors.surfaceMuted }]}>
          <View style={styles.contextTuningSummaryGrid}>
            {items.map((item) => (
              <View
                key={item.label}
                style={[styles.contextTuningSummaryCard, { borderColor: colors.borderSubtle, backgroundColor: colors.surface }]}
              >
                <Text style={styles.contextTuningSummaryLabel}>{item.label}</Text>
                <Text style={[styles.contextTuningSummaryValue, { color: colorForTone(item.tone) }]}>{item.value}</Text>
              </View>
            ))}
          </View>

          <View style={styles.contextTuningHeaderRow}>
            <View style={styles.contextTuningCopy}>
              <Text style={styles.contextTuningEyebrow}>Influence on combined score</Text>
              <Text style={[styles.contextTuningHint, { color: isBalanced ? theme.colors.success : theme.colors.warning }]}>
                {isBalanced ? 'De wegingen komen samen uit op 100%.' : 'De wegingen moeten samen op 100% uitkomen.'}
              </Text>
            </View>
            <View style={[styles.contextTuningTotalBadge, { borderColor: colors.borderSubtle, backgroundColor: colors.surface }]}>
              <Text style={[styles.contextTuningTotalBadgeText, { color: colors.text }]}>
                {Math.round(totalWeight * 100)}%
              </Text>
            </View>
          </View>

          {weightItems.map((item) => {
            const weight = localWeights[item.key];
            return (
              <View
                key={item.key}
                style={[styles.contextWeightCard, { borderColor: colors.borderSubtle, backgroundColor: colors.surface }]}
              >
                <View style={styles.contextWeightCardHeader}>
                  <View>
                    <Text style={styles.contextWeightLabel}>{item.label}</Text>
                    <Text style={[styles.contextWeightMeta, { color: colors.textDim }]}>
                      Weight · {item.score}/100
                    </Text>
                  </View>
                  <Text style={[styles.contextWeightPercent, { color: colors.text }]}>
                    {Math.round(weight * 100)}%
                  </Text>
                </View>

                <View style={styles.contextWeightControls}>
                  <Pressable
                    onPress={() => handleWeightChange(item.key, weight - 0.05)}
                    style={({ pressed }) => [
                      styles.contextWeightStepButton,
                      { borderColor: colors.borderSubtle, backgroundColor: colors.surfaceMuted },
                      pressed && styles.contextWeightStepButtonPressed,
                    ]}
                  >
                    <Text style={[styles.contextWeightStepButtonText, { color: colors.text }]}>-5%</Text>
                  </Pressable>

                  <View style={[styles.contextWeightTrack, { backgroundColor: colors.borderSubtle }]}>
                    <View
                      style={[
                        styles.contextWeightTrackFill,
                        { width: `${Math.max(0, Math.min(100, weight * 100))}%`, backgroundColor: theme.colors.accent },
                      ]}
                    />
                  </View>

                  <Pressable
                    onPress={() => handleWeightChange(item.key, weight + 0.05)}
                    style={({ pressed }) => [
                      styles.contextWeightStepButton,
                      { borderColor: colors.borderSubtle, backgroundColor: colors.surfaceMuted },
                      pressed && styles.contextWeightStepButtonPressed,
                    ]}
                  >
                    <Text style={[styles.contextWeightStepButtonText, { color: colors.text }]}>+5%</Text>
                  </Pressable>
                </View>
              </View>
            );
          })}

          <Pressable
            disabled={savingWeights || !isBalanced}
            onPress={handleSaveWeights}
            style={({ pressed }) => [
              styles.contextWeightsSaveButton,
              (savingWeights || !isBalanced) && styles.contextWeightsSaveButtonDisabled,
              pressed && !savingWeights && isBalanced && styles.contextWeightsSaveButtonPressed,
            ]}
          >
            <Text style={styles.contextWeightsSaveButtonText}>
              {savingWeights ? 'Opslaan...' : 'Wegingen toepassen'}
            </Text>
          </Pressable>
        </View>
      </BottomSheet>
    </>
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
  const summary = localizedBackendText(
    language,
    briefing?.summary?.trim(),
    translate(language, 'analysis.summaryUnavailable', { symbol: activeSymbol }),
  );
  const metaItems = [
    translate(language, 'analysis.available'),
    `${translate(language, 'queue.label.reviews')} ${reviewCount}`,
    `${translate(language, 'queue.label.risks')} ${riskCount}`,
  ];
  const queueItems = [
    {
      key: 'tasks',
      label: translate(language, 'queue.label.tasks'),
      value: reviewCount,
      body: translate(language, 'analysis.reviewBotDecision'),
      detail: translate(language, 'analysis.reviewBotDecisionDetail', { symbol: activeSymbol }),
    },
    { key: 'reviews', label: translate(language, 'queue.label.reviews'), value: reviewCount, body: translate(language, 'queue.body.needDecision') },
    { key: 'risks', label: translate(language, 'queue.label.risks'), value: riskCount, body: translate(language, 'queue.body.slowingYouDown') },
    { key: 'performance', label: translate(language, 'queue.label.performance'), value: performanceCount, body: translate(language, 'queue.body.howTodayBehaves') },
  ];

  return (
    <WorkspaceHeroSection>
      <TodayWithFinnCard
        headline={summary}
        metaItems={metaItems}
        support={translate(language, reviewCount === 1 ? 'finn.reviewNeedsAttention' : 'finn.reviewsNeedAttention', {
          count: reviewCount,
        })}
        queueItems={queueItems}
        queueStatusLabel={translate(language, 'common.itemsOpen', { count: reviewCount })}
      />
    </WorkspaceHeroSection>
  );
}

function AnalysisWatchlistCard({
  assets,
  onOpenActions,
  onOpenAsset,
  onRemoveAsset,
  onSelect,
  selectedSymbol,
}: {
  assets: MobileOverviewAsset[];
  onOpenActions: (asset: MobileOverviewAsset) => void | Promise<void>;
  onOpenAsset: (asset: MobileOverviewAsset) => void | Promise<void>;
  onRemoveAsset: (asset: MobileOverviewAsset) => void | Promise<void>;
  onSelect: (symbol: string) => void;
  selectedSymbol: string;
}) {
  const { appearance, language } = useAppPreferences();
  const colors = preferenceColors(appearance);
  const visibleAssets = assets.slice(0, 1);

  return (
    <CardShell emphasis="standard" flat style={styles.workspaceBlendSurface}>
      <Text style={[styles.watchlistSectionTitle, { color: colors.text }]}>{translate(language, 'analysis.watchlist')}</Text>
      <View style={styles.watchlistTabs}>
        <Text style={[styles.watchlistTabActive, { color: colors.accent }]}>{translate(language, 'analysis.tabCrypto')}</Text>
        <Text style={[styles.watchlistTab, { color: colors.textDim }]}>{translate(language, 'analysis.tabStocks')}</Text>
        <Text style={[styles.watchlistTab, { color: colors.textDim }]}>{translate(language, 'analysis.tabEtf')}</Text>
      </View>

      <View style={[styles.watchlistTable, { borderColor: colors.borderSubtle }]}>
        {visibleAssets.map((asset, index) => {
          const selected = asset.symbol === selectedSymbol;
          const score = compositeScore(asset);
          const price = typeof asset.price === 'number' ? formatPrice(asset.price) : '—';
          const change = typeof asset.change_24h === 'number' ? asset.change_24h : 0;
          const chipTone = toneForScore(score);

          return (
            <SwipeActionRow
              key={asset.symbol}
              actions={[
                {
                  key: 'open',
                  label: translate(language, 'common.open'),
                  icon: 'arrow-up-right',
                  onPress: () => onOpenAsset(asset),
                },
                {
                  key: 'remove',
                  label: translate(language, 'common.delete'),
                  icon: 'trash-2',
                  tone: 'danger',
                  onPress: () => onRemoveAsset(asset),
                },
              ]}
            >
              <Pressable
                onPress={() => onSelect(asset.symbol)}
                style={({ pressed }) => [
                  styles.watchlistRow,
                  {
                    borderBottomColor: colors.borderSubtle,
                    backgroundColor: selected ? `${colors.accent}05` : colors.surface,
                  },
                  index === visibleAssets.length - 1 && styles.watchlistRowLast,
                  pressed && styles.pressed,
                ]}
              >
                <View style={styles.watchlistAssetBlock}>
                  <View style={[styles.watchlistSelectionDot, { backgroundColor: selected ? colors.accent : colors.borderSubtle }]} />
                  <AssetIcon compact logoUrl={asset.logo_url} size={24} symbol={asset.symbol} />
                  <View style={styles.watchlistAssetText}>
                    <Text style={[styles.watchlistSymbol, { color: colors.text }]}>{asset.symbol}</Text>
                    <Text style={[styles.watchlistName, { color: colors.textDim }]}>{asset.display_name || assetNameForSymbol(asset.symbol)}</Text>
                  </View>
                </View>

                <View style={styles.watchlistMetricBlock}>
                  <Text style={[styles.watchlistPrice, { color: colors.text }]}>{price}</Text>
                  <Text style={[styles.watchlistChange, { color: change >= 0 ? theme.colors.success : theme.colors.danger }]}>
                    {formatSignedPercent(change)}
                  </Text>
                </View>

                <View style={styles.watchlistScoreBlock}>
                  <Text style={styles.watchlistScoreLabel}>{translate(language, 'analysis.score')}</Text>
                  <Text style={[styles.watchlistScoreValue, { color: colors.text }]}>{score}</Text>
                </View>

                <View style={styles.watchlistStateBlock}>
                  <StatusChip compact label={stateForAsset(asset)} tone={chipTone} />
                </View>

                <Pressable
                  hitSlop={10}
                  onPress={(event) => {
                    event.stopPropagation();
                    onOpenActions(asset);
                  }}
                  style={[styles.watchlistOverflowButton, { borderColor: colors.borderSubtle, backgroundColor: colors.surfaceMuted }]}
                >
                  <Feather color={colors.textDim} name="more-horizontal" size={15} />
                </Pressable>
              </Pressable>
            </SwipeActionRow>
          );
        })}
      </View>
    </CardShell>
  );
}

function AnalysisWorkspaceFallback({
  activeSymbol,
  onRefreshScores,
}: {
  activeSymbol: string;
  onRefreshScores: () => void;
}) {
  const { language } = useAppPreferences();
  const metaItems = [
    translate(language, 'tag.monitoring'),
    translate(language, 'tag.staleSync'),
    `${translate(language, 'queue.label.reviews')} 0`,
  ];
  const queueItems = [
    {
      key: 'tasks',
      label: translate(language, 'queue.label.tasks'),
      value: 0,
      body: translate(language, 'queue.body.staleSyncMissingBackendContext'),
    },
    {
      key: 'reviews',
      label: translate(language, 'queue.label.reviews'),
      value: 0,
      body: translate(language, 'queue.body.needDecision'),
    },
    {
      key: 'risks',
      label: translate(language, 'queue.label.risks'),
      value: 0,
      body: translate(language, 'queue.body.slowingYouDown'),
    },
    {
      key: 'performance',
      label: translate(language, 'queue.label.performance'),
      value: '--',
      body: translate(language, 'queue.body.howTodayBehaves'),
    },
  ];

  return (
    <WorkspaceHeroSection>
      <TodayWithFinnCard
        headline={translate(language, 'analysis.summaryUnavailable', { symbol: activeSymbol })}
        metaItems={metaItems}
        support={translate(language, 'finn.noBriefingReady')}
        queueItems={queueItems}
        queueStatusLabel={translate(language, 'common.itemsOpen', { count: 0 })}
      />
    </WorkspaceHeroSection>
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
  const { appearance, language } = useAppPreferences();
  const colors = preferenceColors(appearance);

  return (
    <CardShell emphasis="standard" flat style={styles.workspaceBlendSurface}>
      <View style={styles.sectionTop}>
        <View>
          <Text style={styles.kicker}>{translate(language, 'analysis.marketRegime')}</Text>
          <Text style={[styles.cardTitle, { color: colors.text }]}>{translate(language, 'analysis.controlPlane', { symbol })}</Text>
        </View>
        <StatusChip compact label={change} tone={change.startsWith('+') ? 'success' : 'danger'} />
      </View>
      <View style={styles.analysisMetaRow}>
        <View style={[styles.analysisMetaCard, { borderColor: colors.border, backgroundColor: colors.backgroundSoft }]}>
          <Text style={styles.analysisMetaLabel}>{translate(language, 'analysis.posture')}</Text>
          <Text style={[styles.analysisMetaValue, { color: colorForTone(postureTone) }]}>{posture}</Text>
        </View>
        <View style={[styles.analysisMetaCard, { borderColor: colors.border, backgroundColor: colors.backgroundSoft }]}>
          <Text style={styles.analysisMetaLabel}>{translate(language, 'analysis.risk')}</Text>
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
  const { appearance, language } = useAppPreferences();
  const colors = preferenceColors(appearance);

  return (
    <View style={styles.analysisActionWrap}>
      <Pressable onPress={onAskContext} style={[styles.analysisActionPrimary, { backgroundColor: theme.colors.accent }]}>
        <Text style={styles.analysisActionPrimaryText}>{translate(language, 'analysis.askFinnContext')}</Text>
      </Pressable>
      <Pressable onPress={onAskSetup} style={[styles.analysisActionSecondary, { borderColor: colors.borderStrong, backgroundColor: colors.surface }]}>
        <Text style={[styles.analysisActionSecondaryText, { color: colors.text }]}>{translate(language, 'analysis.reviewSetupEvidence')}</Text>
      </Pressable>
    </View>
  );
}

type AssetIntelligence = {
  symbol: string;
  logoUrl?: string | null;
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
  const { appearance, language } = useAppPreferences();
  const colors = preferenceColors(appearance);

  return (
    <CardShell emphasis="primary">
      <View style={styles.intelTop}>
        <View style={styles.assetIdentity}>
          <AssetIcon logoUrl={intelligence.logoUrl} symbol={intelligence.symbol} />
          <View>
            <Text style={styles.intelLabel}>{translate(language, 'analysis.analysisBriefing')}</Text>
            <Text style={[styles.intelSymbol, { color: colors.text }]}>{intelligence.symbol}</Text>
          </View>
        </View>
        <StatusChip compact label={intelligence.change} tone={intelligence.changeTone} />
      </View>

      <Text style={[styles.price, { color: colors.text }]}>{intelligence.price}</Text>
      <Text style={[styles.intelHeadline, { color: colors.text }]}>{intelligence.headline}</Text>
      <Text style={[styles.finnSummary, { color: colors.textMuted }]}>{intelligence.finnSummary}</Text>

      <View style={styles.intelChips}>
        <StatusChip compact label={intelligence.marketPosture} tone={intelligence.marketPostureTone} />
        <StatusChip compact label={intelligence.setupState} tone={intelligence.setupStateTone} />
        <StatusChip compact label={intelligence.riskState} tone={intelligence.riskStateTone} />
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
  const { appearance, language } = useAppPreferences();
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
  hiddenIndicatorKeys,
  onHideIndicator,
  workspaceAsset,
  onAskFinnIndicator,
  onOpenIndicatorActions,
  onOpenIndicatorDetail,
}: {
  asset: MobileOverviewAsset;
  hiddenIndicatorKeys: string[];
  onHideIndicator: (item: {
    sectionKey: string;
    sectionTitle: string;
    row: { label: string; value: string; development: string; assessment: string; tone: StatusTone };
  }) => void;
  workspaceAsset?: WorkspaceAssetResponse;
  onAskFinnIndicator: (item: {
    sectionKey: string;
    sectionTitle: string;
    row: { label: string; value: string; development: string; assessment: string; tone: StatusTone };
  }) => void | Promise<void>;
  onOpenIndicatorActions: (item: {
    sectionKey: string;
    sectionTitle: string;
    row: { label: string; value: string; development: string; assessment: string; tone: StatusTone };
  }) => void | Promise<void>;
  onOpenIndicatorDetail: (item: {
    sectionKey: string;
    sectionTitle: string;
    row: { label: string; value: string; development: string; assessment: string; tone: StatusTone };
  }) => void | Promise<void>;
}) {
  const { language } = useAppPreferences();
  const sections = buildEvidenceSections(asset.symbol, workspaceAsset, hiddenIndicatorKeys);

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
          activeSymbol={asset.symbol}
          hiddenIndicatorKeys={hiddenIndicatorKeys}
          key={section.key}
          onHideIndicator={onHideIndicator}
          section={section}
          isLastSection={index === sections.length - 1}
          onAskFinnIndicator={onAskFinnIndicator}
          onOpenIndicatorActions={onOpenIndicatorActions}
          onOpenIndicatorDetail={onOpenIndicatorDetail}
        />
      ))}
    </View>
  );
}

function AnalysisEvidenceSectionCard({
  activeSymbol,
  hiddenIndicatorKeys,
  isLastSection,
  onHideIndicator,
  onAskFinnIndicator,
  onOpenIndicatorActions,
  onOpenIndicatorDetail,
  section,
}: {
  activeSymbol: string;
  hiddenIndicatorKeys: string[];
  isLastSection: boolean;
  onHideIndicator: (item: {
    sectionKey: string;
    sectionTitle: string;
    row: { label: string; value: string; development: string; assessment: string; tone: StatusTone };
  }) => void;
  onAskFinnIndicator: (item: {
    sectionKey: string;
    sectionTitle: string;
    row: { label: string; value: string; development: string; assessment: string; tone: StatusTone };
  }) => void | Promise<void>;
  onOpenIndicatorActions: (item: {
    sectionKey: string;
    sectionTitle: string;
    row: { label: string; value: string; development: string; assessment: string; tone: StatusTone };
  }) => void | Promise<void>;
  onOpenIndicatorDetail: (item: {
    sectionKey: string;
    sectionTitle: string;
    row: { label: string; value: string; development: string; assessment: string; tone: StatusTone };
  }) => void | Promise<void>;
  section: {
    key: string;
    title: string;
    score: number;
    summary: string;
    rows: Array<{ label: string; value: string; development: string; assessment: string; tone: StatusTone }>;
  };
}) {
  const { appearance, language } = useAppPreferences();
  const colors = preferenceColors(appearance);
  const visibleRows = section.rows.filter(
    (row) => !hiddenIndicatorKeys.includes(buildIndicatorKey(activeSymbol, section.key, row.label)),
  );

  return (
    <CardShell
      emphasis="standard"
      flat
      style={[
        styles.workspaceBlendSurface,
        styles.evidenceSectionBlock,
        { borderBottomColor: colors.borderSubtle },
        isLastSection && styles.analysisSectionBlockLast,
      ]}
    >
      <View style={styles.evidenceSectionHeader}>
        <View style={styles.evidenceSectionTitleWrap}>
          <Text style={[styles.evidenceSectionTitle, { color: colors.text }]}>{section.title}</Text>
          <Text style={styles.evidenceSectionScore}>{section.score}/100</Text>
        </View>
        <Feather color={colors.textDim} name="chevron-down" size={16} />
      </View>

      <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.evidenceTimeframeRow}>
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

      <Text style={[styles.evidenceSectionSummary, { color: colors.textMuted }]}>{section.summary}</Text>

      <View style={[styles.evidenceTable, { borderColor: colors.borderSubtle }]}>
        {visibleRows.length === 0 ? (
          <Text style={[styles.evidenceEmptyText, { color: colors.textMuted }]}>
            Geen indicatoren zichtbaar in deze sectie.
          </Text>
        ) : visibleRows.map((row, index) => (
          <SwipeActionRow
            key={`${section.key}-${row.label}`}
            actions={[
              {
                key: 'remove',
                label: translate(language, 'common.delete'),
                icon: 'trash-2',
                tone: 'danger',
                onPress: () => onHideIndicator({ sectionKey: section.key, sectionTitle: section.title, row }),
              },
            ]}
          >
            <Pressable
              onPress={() => onOpenIndicatorDetail({ sectionKey: section.key, sectionTitle: section.title, row })}
              style={({ pressed }) => [
                styles.evidenceMobileRow,
                index < visibleRows.length - 1 && { borderBottomColor: colors.borderSubtle, borderBottomWidth: 1 },
                index === visibleRows.length - 1 && isLastSection && styles.evidenceLastRow,
                pressed && styles.pressed,
              ]}
            >
              <View style={styles.evidenceMobileTop}>
                <View style={styles.evidenceMobileLabelWrap}>
                  <View style={[styles.evidenceMobileIcon, { backgroundColor: colors.surfaceMuted }]}>
                    <Feather
                      color={colors.accent}
                      name={evidenceSectionIcon(section.key)}
                      size={listRowStandards.iconGlyphSize - 2}
                    />
                  </View>
                  <Text style={[styles.evidenceMobileLabel, { color: colors.text }]}>{row.label}</Text>
                </View>
                <View style={styles.evidenceMobileValueWrap}>
                  <Text style={[styles.evidenceMobileValue, { color: colors.text }]}>{row.value}</Text>
                  <Pressable
                    hitSlop={10}
                    onPress={(event) => {
                      event.stopPropagation();
                      onOpenIndicatorActions({ sectionKey: section.key, sectionTitle: section.title, row });
                    }}
                    style={[styles.evidenceOverflowButton, { borderColor: colors.borderSubtle, backgroundColor: colors.surfaceMuted }]}
                  >
                    <Feather color={colors.textDim} name="more-horizontal" size={15} />
                  </Pressable>
                </View>
              </View>
              <View style={styles.evidenceMobileBottom}>
                <Text
                  numberOfLines={1}
                  style={[styles.evidenceMobileAssessment, { color: colors.textMuted }]}
                >
                  {row.assessment}
                </Text>
                <StatusChip compact label={row.development} tone={row.tone} />
              </View>
            </Pressable>
          </SwipeActionRow>
        ))}
      </View>
    </CardShell>
  );
}

function IndicatorDetailSheet({
  item,
  onHide,
  onAskFinn,
}: {
  item: {
    sectionKey: string;
    sectionTitle: string;
    row: { label: string; value: string; development: string; assessment: string; tone: StatusTone };
  };
  onHide: () => void;
  onAskFinn: () => void | Promise<void>;
}) {
  const { appearance } = useAppPreferences();
  const colors = preferenceColors(appearance);
  const nowMeaning = indicatorMeaningNow(item.row);
  const monitorHint = indicatorMonitorHint(item.row);

  return (
    <View style={styles.indicatorDetailStack}>
      <View style={[styles.indicatorDetailHero, { borderColor: colors.borderSubtle, backgroundColor: colors.surfaceMuted }]}>
        <View style={styles.sectionTop}>
          <View style={styles.flexText}>
            <Text style={styles.kicker}>{item.sectionTitle} indicator</Text>
            <Text style={[styles.indicatorDetailTitle, { color: colors.text }]}>{item.row.label}</Text>
            <Text style={[styles.indicatorDetailMeta, { color: colors.textDim }]}>
              {item.sectionTitle} · {item.row.development}
            </Text>
          </View>
          <StatusChip compact label={item.row.development} tone={item.row.tone} />
        </View>
        <Text style={[styles.indicatorHeroSummary, { color: colors.textMuted }]}>
          {nowMeaning}
        </Text>
      </View>

      <View style={styles.indicatorMetricGrid}>
        <View style={[styles.indicatorMetricCard, { borderColor: colors.borderSubtle, backgroundColor: colors.surfaceMuted }]}>
          <Text style={[styles.indicatorMetricLabel, { color: colors.textDim }]}>Waarde</Text>
          <Text style={[styles.indicatorMetricValue, { color: colors.text }]}>{item.row.value}</Text>
        </View>
        <View style={[styles.indicatorMetricCard, { borderColor: colors.borderSubtle, backgroundColor: colors.surfaceMuted }]}>
          <Text style={[styles.indicatorMetricLabel, { color: colors.textDim }]}>Ontwikkeling</Text>
          <Text style={[styles.indicatorMetricValue, { color: colorForTone(item.row.tone) }]}>{item.row.development}</Text>
        </View>
      </View>

      <View style={[styles.indicatorAssessmentCard, { borderColor: colors.borderSubtle }]}>
        <Text style={[styles.indicatorAssessmentTitle, { color: colors.text }]}>Interpretatie</Text>
        <Text style={[styles.indicatorAssessmentBody, { color: colors.textMuted }]}>{item.row.assessment}</Text>
      </View>

      <View style={[styles.indicatorNowCard, { borderColor: colors.borderSubtle, backgroundColor: colors.surfaceMuted }]}>
        <Text style={[styles.indicatorNowTitle, { color: colors.text }]}>Wat betekent dit nu?</Text>
        <Text style={[styles.indicatorNowBody, { color: colors.textMuted }]}>{nowMeaning}</Text>
        <Text style={[styles.indicatorMonitorLabel, { color: colors.textDim }]}>Let nu vooral op</Text>
        <Text style={[styles.indicatorMonitorBody, { color: colors.text }]}>{monitorHint}</Text>
      </View>

      <Pressable
        onPress={async () => {
          await triggerHaptic('warning');
          onHide();
        }}
        style={[styles.indicatorHideButton, { borderColor: colors.borderSubtle, backgroundColor: colors.surfaceMuted }]}
      >
        <Text style={[styles.indicatorHideButtonText, { color: colors.danger }]}>Verberg indicator</Text>
      </Pressable>

      <Pressable
        onPress={async () => {
          await triggerHaptic('selection');
          await onAskFinn();
        }}
        style={[styles.indicatorFinnButton, { backgroundColor: colors.accent }]}
      >
        <Text style={styles.indicatorFinnButtonText}>Vraag FINN om extra uitleg</Text>
      </Pressable>
    </View>
  );
}

function buildIndicatorKey(symbol: string, sectionKey: string, label: string) {
  return `${symbol}:${sectionKey}:${label}`.toLowerCase();
}

function normalizeHiddenIndicatorKeys(value: unknown): string[] {
  if (!Array.isArray(value)) return [];

  return value
    .map((item) => (typeof item === 'string' ? item.trim().toLowerCase() : ''))
    .filter(Boolean);
}

function indicatorMeaningNow(row: {
  label: string;
  value: string;
  development: string;
  assessment: string;
  tone: StatusTone;
}) {
  if (row.tone === 'success') {
    return `${row.label} ondersteunt het beeld nu redelijk goed. De huidige waarde (${row.value}) wijst op bevestiging, maar alleen zolang dit signaal stabiel blijft.`;
  }
  if (row.tone === 'danger') {
    return `${row.label} zet nu duidelijke frictie op het beeld. De huidige waarde (${row.value}) vraagt om extra terughoudendheid tot de bevestiging verbetert.`;
  }
  if (row.tone === 'warning') {
    return `${row.label} is nu gemengd. De waarde (${row.value}) geeft nog geen schoon signaal, dus dit is eerder monitoren dan vertrouwen.`;
  }
  return `${row.label} geeft nu vooral context. De waarde (${row.value}) helpt om het totaalbeeld te lezen, maar is op zichzelf nog niet beslissend.`;
}

function indicatorMonitorHint(row: {
  label: string;
  value: string;
  development: string;
  assessment: string;
  tone: StatusTone;
}) {
  if (row.tone === 'success') {
    return `Kijk of ${row.label} de huidige verbetering vasthoudt en of andere indicatoren in dezelfde sectie mee bevestigen.`;
  }
  if (row.tone === 'danger') {
    return `Wacht op stabilisatie in ${row.label} of op sterkere bevestiging uit de rest van de sectie voordat je meer vertrouwen geeft.`;
  }
  if (row.tone === 'warning') {
    return `Controleer of ${row.label} doorschuift naar verbetering of juist verder verzwakt bij de volgende update.`;
  }
  return `Gebruik ${row.label} samen met de andere indicatoren uit ${row.assessment ? 'deze sectie' : 'het totaalbeeld'} voor context.`;
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
        <Text style={[styles.forwardTitle, { color: colors.text }]}>Historical forward returns</Text>
        <Text style={[styles.forwardSubtitle, { color: colors.textMuted }]}>
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
  errorMessage,
  interval,
  loading,
  onIntervalChange,
  symbol,
}: {
  errorMessage?: string;
  interval: TradingViewInterval;
  loading: boolean;
  onIntervalChange: (interval: TradingViewInterval) => void;
  symbol: string;
}) {
  const { language } = useAppPreferences();
  const chartFallbackBody =
    errorMessage ??
    (language === 'nl'
      ? 'De TradingView-widget gaf nog geen bruikbare output terug. Controleer of de WebView extern scriptverkeer mag laden.'
      : language === 'de'
        ? 'Das TradingView-Widget hat noch keine brauchbare Ausgabe geliefert. Prüfe, ob die WebView externe Skripte laden darf.'
        : 'The TradingView widget did not return usable output yet. Check whether the WebView may load external scripts.');

  return (
    <CardShell emphasis="standard" flat style={styles.workspaceBlendSurface}>
      <Text style={styles.kicker}>Tradingview chart</Text>

      {loading ? (
        <LoadingSkeletonCard />
      ) : (
        <>
          <TradingViewWidget interval={interval} onIntervalChange={onIntervalChange} symbol={symbol} />
          {errorMessage ? (
            <View style={styles.chartNotice}>
              <InsightCard
                label="Chart"
                title={
                  language === 'nl'
                    ? 'TradingView-chart geladen met fallback-configuratie.'
                    : language === 'de'
                      ? 'TradingView-Chart mit Fallback-Konfiguration geladen.'
                      : 'TradingView chart loaded with fallback configuration.'
                }
                body={chartFallbackBody}
                tone="warning"
              />
            </View>
          ) : null}
        </>
      )}
    </CardShell>
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
      <Text style={[styles.rowPrice, { color: colors.text }]}>{typeof asset.price === 'number' ? formatShortPrice(asset.price) : '—'}</Text>
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
  const { appearance, language } = useAppPreferences();
  const colors = preferenceColors(appearance);

  return (
    <View style={styles.terminal}>
      <View style={styles.terminalHeader}>
        <View style={styles.terminalTitleRow}>
          <Text style={styles.terminalStar}>★</Text>
          <View>
            <Text style={styles.terminalLabel}>{translate(language, 'analysis.marketContext')}</Text>
            <Text style={[styles.terminalSubtitle, { color: colors.textMuted }]}>
              {translate(language, 'analysis.liveWatchlist')}
            </Text>
          </View>
        </View>
        <StatusChip
          compact
          label={translate(language, stale ? 'common.stale' : 'tag.live')}
          tone={stale ? 'warning' : 'success'}
        />
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
          <Text style={[styles.terminalPrice, { color: colors.text }]}>{typeof asset.price === 'number' ? formatShortPrice(asset.price) : '—'}</Text>
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

function normalizeIntelligenceWeights(source: unknown): IntelligenceWeightsPayload {
  const raw = (source && typeof source === 'object' ? (source as Record<string, unknown>).weights : source) as
    | Record<string, unknown>
    | undefined;
  const next = {
    market: normalizeWeightValue(raw?.market, DEFAULT_INTELLIGENCE_WEIGHTS.market),
    macro: normalizeWeightValue(raw?.macro, DEFAULT_INTELLIGENCE_WEIGHTS.macro),
    technical: normalizeWeightValue(raw?.technical, DEFAULT_INTELLIGENCE_WEIGHTS.technical),
  };
  const total = Object.values(next).reduce((sum, value) => sum + value, 0);
  if (!total) return { ...DEFAULT_INTELLIGENCE_WEIGHTS };

  return {
    market: next.market / total,
    macro: next.macro / total,
    technical: next.technical / total,
  };
}

function normalizeWeightValue(value: unknown, fallback: number) {
  const parsed = Number(value);
  if (!Number.isFinite(parsed) || parsed < 0) return fallback;
  return parsed > 1 ? parsed / 100 : parsed;
}

function rebalanceIntelligenceWeights(
  current: IntelligenceWeightsPayload,
  key: IntelligenceWeightKey,
  nextValue: number,
): IntelligenceWeightsPayload {
  const value = Math.max(0, Math.min(1, Number(nextValue)));
  const otherKeys = (Object.keys(current) as IntelligenceWeightKey[]).filter((itemKey) => itemKey !== key);
  const otherTotal = otherKeys.reduce((sum, itemKey) => sum + current[itemKey], 0);
  const remaining = 1 - value;
  const next = { ...current, [key]: value };

  otherKeys.forEach((itemKey) => {
    next[itemKey] = otherTotal > 0 ? remaining * (current[itemKey] / otherTotal) : remaining / otherKeys.length;
  });

  return next;
}

function areIntelligenceWeightsEqual(
  left: IntelligenceWeightsPayload,
  right: IntelligenceWeightsPayload,
) {
  return (
    Math.abs(left.market - right.market) < 0.0001 &&
    Math.abs(left.macro - right.macro) < 0.0001 &&
    Math.abs(left.technical - right.technical) < 0.0001
  );
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
    logoUrl: asset.logo_url,
    marketPosture: posture,
    marketPostureTone: latestChange >= 0 && technicalScore >= 60 ? 'success' : latestChange < -3 ? 'danger' : 'accent',
    price: latestPrice > 0 ? formatPrice(latestPrice) : '—',
    riskState,
    riskStateTone: riskState === 'High risk' || riskState === 'Weak risk/reward' ? 'danger' : riskState === 'Wait' ? 'warning' : 'success',
    setupScore,
    setupState,
    setupStateTone: toneForScore(setupScore),
    symbol: asset.symbol,
    technicalScore,
  };
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

function buildFallbackAnalysisAsset(
  symbol: string,
  latest?: MarketLatestResponse,
  workspaceAsset?: WorkspaceAssetResponse,
): MobileOverviewAsset | null {
  const marketScore = readWorkspaceScore(workspaceAsset?.categories?.market?.score?.score);
  const macroScore = readWorkspaceScore(workspaceAsset?.categories?.macro?.score?.score);
  const technicalScore = readWorkspaceScore(workspaceAsset?.categories?.technical?.score?.score);
  const combinedScore = readWorkspaceScore(workspaceAsset?.combined?.score);
  const latestPrice = readNumber(latest, ['price'], NaN);
  const latestChange = readNumber(latest, ['change_24h'], NaN);

  const hasAnyBackendSignal = [
    marketScore,
    macroScore,
    technicalScore,
    combinedScore,
    Number.isFinite(latestPrice) ? latestPrice : null,
    Number.isFinite(latestChange) ? latestChange : null,
  ].some((value) => typeof value === 'number' && Number.isFinite(value));

  if (!hasAnyBackendSignal) return null;

  const safeMarket = marketScore ?? combinedScore ?? 50;
  const safeMacro = macroScore ?? combinedScore ?? 50;
  const safeTechnical = technicalScore ?? combinedScore ?? 50;
  const safeSetup = combinedScore ?? Math.round((safeMarket + safeMacro + safeTechnical) / 3);

  return {
    symbol,
    price: Number.isFinite(latestPrice) ? latestPrice : null,
    change_24h: Number.isFinite(latestChange) ? latestChange : null,
    macro_score: safeMacro,
    technical_score: safeTechnical,
    market_score: safeMarket,
    setup_score: safeSetup,
    macro_label: workspaceAsset?.categories?.macro?.score?.status ?? null,
    technical_label: workspaceAsset?.categories?.technical?.score?.status ?? null,
    market_label: workspaceAsset?.categories?.market?.score?.status ?? null,
    posture: workspaceAsset?.combined?.status ?? null,
    structure: deriveWorkspaceSummary(
      workspaceAsset?.categories?.technical,
      'Technical picture is workable but not fully confirmed yet.',
    ),
    conviction: combinedScore ?? null,
    risk_state: deriveWorkspaceSummary(
      workspaceAsset?.categories?.market,
      'Monitoring',
    ),
  };
}

function buildEvidenceSections(
  symbol: string,
  workspaceAsset?: WorkspaceAssetResponse,
  hiddenIndicatorKeys: string[] = [],
) {
  return buildWorkspaceEvidenceSections(symbol, workspaceAsset, hiddenIndicatorKeys);
}

function buildWorkspaceEvidenceSections(
  symbol: string,
  workspaceAsset?: WorkspaceAssetResponse,
  hiddenIndicatorKeys: string[] = [],
) {
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
    const visibleRows = (payload?.rows ?? []).filter(
      (row) => !hiddenIndicatorKeys.includes(buildIndicatorKey(symbol, category.key, humanizeIndicatorName(row.name))),
    );
    const visibleScore = averageVisibleIndicatorScore(visibleRows);

    return {
      key: category.key,
      title: category.title,
      score: visibleScore ?? readWorkspaceScore(payload?.score?.score) ?? 0,
      summary: deriveWorkspaceSummary(payload, category.summaryFallback),
      rows: visibleRows.map((row) => ({
        label: humanizeIndicatorName(row.name),
        value: formatWorkspaceValue(row.value),
        development: deriveWorkspaceDevelopment(row),
        assessment: deriveWorkspaceAssessment(row),
        rawScore: typeof row.score === 'number' && Number.isFinite(row.score) ? row.score : null,
        tone: deriveWorkspaceTone(row),
      })),
    };
  });
}

function buildVisibleWorkspaceScores(
  symbol: string,
  workspaceAsset?: WorkspaceAssetResponse,
  hiddenIndicatorKeys: string[] = [],
) {
  const sections = buildWorkspaceEvidenceSections(symbol, workspaceAsset, hiddenIndicatorKeys);
  const market = sections.find((section) => section.key === 'market')?.score ?? null;
  const macro = sections.find((section) => section.key === 'macro')?.score ?? null;
  const technical = sections.find((section) => section.key === 'technical')?.score ?? null;
  const visibleSectionScores = [market, macro, technical].filter(
    (value): value is number => typeof value === 'number' && Number.isFinite(value),
  );

  return {
    market,
    macro,
    technical,
    combined: visibleSectionScores.length
      ? Math.round(visibleSectionScores.reduce((sum, value) => sum + value, 0) / visibleSectionScores.length)
      : null,
  };
}

function averageVisibleIndicatorScore(
  rows: Array<{ score?: number | null }>,
) {
  const scores = rows
    .map((row) => row.score)
    .filter((value): value is number => typeof value === 'number' && Number.isFinite(value));
  if (!scores.length) return null;
  return Math.round(scores.reduce((sum, value) => sum + value, 0) / scores.length);
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

  return '—';
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

function evidenceSectionIcon(sectionKey: string): keyof typeof Feather.glyphMap {
  if (sectionKey === 'macro') {
    return 'globe';
  }
  if (sectionKey === 'technical') {
    return 'activity';
  }
  return 'trending-up';
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
    marginTop: 8,
    overflow: 'hidden',
    paddingLeft: 6,
    paddingTop: 10,
  },
  chartHeader: {
    alignItems: 'center',
    flexDirection: 'row',
    gap: theme.spacing.md,
    justifyContent: 'space-between',
    marginBottom: 2,
  },
  chartNotice: {
    marginTop: 12,
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
    fontWeight: '800',
    marginTop: 2,
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
  contextScoresHeader: {
    marginBottom: 8,
  },
  contextScoresCard: {
    borderRadius: 16,
    borderWidth: 1,
    paddingHorizontal: 0,
    paddingVertical: 0,
  },
  contextScoresCardPressed: {
    opacity: 0.92,
    transform: [{ scale: 0.995 }],
  },
  contextScoresTitle: {
    fontSize: 14,
    fontWeight: '900',
  },
  contextTuningCopy: {
    flex: 1,
    gap: 3,
  },
  contextTuningEyebrow: {
    color: theme.colors.textDim,
    fontSize: 10,
    fontWeight: '900',
    letterSpacing: 1,
    textTransform: 'uppercase',
  },
  contextTuningHeaderRow: {
    alignItems: 'center',
    flexDirection: 'row',
    gap: theme.spacing.md,
    justifyContent: 'space-between',
  },
  contextTuningHint: {
    fontSize: 13,
    fontWeight: '700',
    lineHeight: 18,
  },
  contextTuningPanel: {
    borderRadius: theme.radius.card,
    borderWidth: 1,
    gap: theme.spacing.md,
    padding: theme.spacing.md,
  },
  contextTuningSummaryCard: {
    borderRadius: theme.radius.md,
    borderWidth: 1,
    flexBasis: '48%',
    gap: 2,
    minWidth: '48%',
    paddingHorizontal: theme.spacing.md,
    paddingVertical: theme.spacing.sm,
  },
  contextTuningSummaryGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: theme.spacing.sm,
  },
  contextTuningSummaryLabel: {
    color: theme.colors.textDim,
    fontSize: 9,
    fontWeight: '900',
    letterSpacing: 0.9,
    textTransform: 'uppercase',
  },
  contextTuningSummaryValue: {
    fontSize: 24,
    fontWeight: '900',
    lineHeight: 28,
  },
  contextTuningTotalBadge: {
    borderRadius: theme.radius.pill,
    borderWidth: 1,
    minWidth: 72,
    paddingHorizontal: theme.spacing.md,
    paddingVertical: theme.spacing.sm,
  },
  contextTuningTotalBadgeText: {
    fontSize: 18,
    fontWeight: '900',
    textAlign: 'center',
  },
  contextWeightCard: {
    borderRadius: theme.radius.card,
    borderWidth: 1,
    gap: theme.spacing.md,
    padding: theme.spacing.md,
  },
  contextWeightCardHeader: {
    alignItems: 'center',
    flexDirection: 'row',
    gap: theme.spacing.md,
    justifyContent: 'space-between',
  },
  contextWeightControls: {
    alignItems: 'center',
    flexDirection: 'row',
    gap: theme.spacing.sm,
  },
  contextWeightLabel: {
    color: theme.colors.textDim,
    fontSize: 10,
    fontWeight: '900',
    letterSpacing: 1,
    textTransform: 'uppercase',
  },
  contextWeightMeta: {
    fontSize: 12,
    fontWeight: '700',
    marginTop: 4,
  },
  contextWeightPercent: {
    fontSize: 28,
    fontWeight: '900',
    lineHeight: 30,
  },
  contextWeightStepButton: {
    alignItems: 'center',
    borderRadius: theme.radius.button,
    borderWidth: 1,
    justifyContent: 'center',
    minHeight: 42,
    minWidth: 62,
    paddingHorizontal: theme.spacing.md,
  },
  contextWeightStepButtonPressed: {
    opacity: 0.85,
  },
  contextWeightStepButtonText: {
    fontSize: 12,
    fontWeight: '900',
    letterSpacing: 0.4,
  },
  contextWeightTrack: {
    borderRadius: theme.radius.pill,
    flex: 1,
    height: 10,
    overflow: 'hidden',
  },
  contextWeightTrackFill: {
    borderRadius: theme.radius.pill,
    height: '100%',
  },
  contextWeightsSaveButton: {
    alignItems: 'center',
    alignSelf: 'flex-end',
    backgroundColor: theme.colors.accent,
    borderRadius: theme.radius.button,
    justifyContent: 'center',
    minHeight: 44,
    minWidth: 168,
    paddingHorizontal: theme.spacing.lg,
  },
  contextWeightsSaveButtonDisabled: {
    opacity: 0.45,
  },
  contextWeightsSaveButtonPressed: {
    opacity: 0.9,
  },
  contextWeightsSaveButtonText: {
    color: theme.colors.white,
    fontSize: 12,
    fontWeight: '900',
    letterSpacing: 0.7,
    textTransform: 'uppercase',
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
  indicatorAssessmentBody: {
    ...typography.body,
    marginTop: theme.spacing.xs,
  },
  indicatorAssessmentCard: {
    borderRadius: theme.radius.card,
    borderWidth: 1,
    padding: theme.spacing.md,
  },
  indicatorAssessmentTitle: {
    ...typography.sectionTitle,
  },
  indicatorDetailHero: {
    borderRadius: theme.radius.card,
    borderWidth: 1,
    padding: theme.spacing.md,
  },
  indicatorDetailMeta: {
    ...typography.body,
  },
  indicatorHeroSummary: {
    ...typography.body,
    marginTop: theme.spacing.sm,
  },
  indicatorMonitorBody: {
    ...typography.bodyStrong,
    marginTop: 4,
  },
  indicatorMonitorLabel: {
    ...typography.metricLabel,
    marginTop: theme.spacing.sm,
  },
  indicatorNowBody: {
    ...typography.body,
    marginTop: theme.spacing.xs,
  },
  indicatorNowCard: {
    borderRadius: theme.radius.card,
    borderWidth: 1,
    padding: theme.spacing.md,
  },
  indicatorNowTitle: {
    ...typography.sectionTitle,
  },
  indicatorDetailStack: {
    gap: theme.spacing.md,
  },
  indicatorDetailTitle: {
    fontSize: theme.typography.title,
    fontWeight: '900',
    lineHeight: 28,
  },
  indicatorHideButton: {
    alignItems: 'center',
    borderRadius: theme.radius.button,
    borderWidth: 1,
    paddingHorizontal: theme.spacing.md,
    paddingVertical: theme.spacing.sm,
  },
  indicatorHideButtonText: {
    fontSize: 13,
    fontWeight: '800',
    letterSpacing: 0.3,
  },
  indicatorFinnButton: {
    alignItems: 'center',
    borderRadius: theme.radius.button,
    paddingHorizontal: theme.spacing.md,
    paddingVertical: theme.spacing.sm,
  },
  indicatorFinnButtonText: {
    color: theme.colors.white,
    fontSize: 13,
    fontWeight: '800',
    letterSpacing: 0.3,
  },
  indicatorMetricCard: {
    borderRadius: theme.radius.card,
    borderWidth: 1,
    flex: 1,
    gap: 4,
    padding: theme.spacing.sm,
  },
  indicatorMetricGrid: {
    flexDirection: 'row',
    gap: theme.spacing.sm,
  },
  indicatorMetricLabel: {
    ...typography.metricLabel,
  },
  indicatorMetricValue: {
    ...typography.bodyStrong,
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
    marginBottom: 10,
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
    gap: 8,
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
    fontSize: 15,
    fontWeight: '900',
    lineHeight: 18,
    marginTop: 3,
  },
  scoreOverviewCard: {
    borderRightWidth: 0.5,
    flex: 1,
    gap: 2,
    minWidth: 0,
    paddingHorizontal: 8,
    paddingVertical: 8,
  },
  scoreOverviewCardLast: {
    borderRightWidth: 0,
  },
  scoreOverviewGrid: {
    flexDirection: 'row',
    flexWrap: 'nowrap',
  },
  scoreOverviewLabel: {
    color: theme.colors.textDim,
    fontSize: 7.5,
    fontWeight: '900',
    letterSpacing: 0.6,
    textTransform: 'uppercase',
  },
  scoreOverviewValue: {
    fontSize: 9.75,
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
    fontSize: 14,
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
    fontSize: 18,
    fontWeight: '900',
    letterSpacing: -0.25,
  },
  activeAnalysisShell: {
    borderRadius: 20,
    borderWidth: 1,
    marginTop: 2,
    paddingHorizontal: 12,
    paddingVertical: 12,
  },
  activeAnalysisRow: {
    gap: 8,
    marginTop: 8,
  },
  activeAnalysisSummary: {
    flexDirection: 'row',
    gap: 6,
    overflow: 'hidden',
    borderRadius: 16,
    borderWidth: 1,
    paddingHorizontal: 8,
    paddingVertical: 8,
  },
  activeAnalysisSummaryItem: {
    flex: 1,
    gap: 2,
    minHeight: 44,
    minWidth: 0,
    paddingHorizontal: 4,
    paddingVertical: 3,
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
    fontSize: 11,
    fontWeight: '900',
    letterSpacing: 0.85,
    textTransform: 'uppercase',
  },
  activeAnalysisTop: {
    alignItems: 'center',
    flexDirection: 'row',
    justifyContent: 'space-between',
  },
  analysisSection: {
    gap: 2,
  },
  assetPill: {
    alignItems: 'center',
    borderRadius: theme.radius.pill,
    borderWidth: 1,
    flexDirection: 'row',
    gap: theme.spacing.xs,
    paddingHorizontal: 8,
    paddingVertical: 6,
  },
  assetPillText: {
    fontSize: 11,
    fontWeight: '900',
  },
  evidenceMobileAssessment: {
    flex: 1,
    ...typography.listRowMeta,
    marginRight: 6,
  },
  evidenceMobileBottom: {
    alignItems: 'center',
    flexDirection: 'row',
    gap: 6,
    justifyContent: 'space-between',
    marginTop: 2,
  },
  evidenceMobileIcon: {
    alignItems: 'center',
    borderColor: listRowStandards.iconBorderColor,
    borderRadius: 10,
    borderWidth: 1,
    height: 22,
    justifyContent: 'center',
    width: 22,
  },
  evidenceMobileLabel: {
    ...typography.listRowTitle,
    flex: 1,
    paddingRight: 4,
  },
  evidenceMobileLabelWrap: {
    alignItems: 'center',
    flex: 1,
    flexDirection: 'row',
    gap: 8,
    minWidth: 0,
  },
  evidenceMobileValueWrap: {
    alignItems: 'center',
    flexDirection: 'row',
    gap: 6,
    marginLeft: theme.spacing.xs,
  },
  evidenceMobileRow: {
    gap: 1,
    paddingHorizontal: 2,
    paddingVertical: 7,
  },
  evidenceLastRow: {
    paddingBottom: 12,
  },
  evidenceMobileTop: {
    alignItems: 'flex-start',
    flexDirection: 'row',
    gap: 6,
    justifyContent: 'space-between',
  },
  evidenceMobileValue: {
    ...typography.listRowTitle,
    marginLeft: 4,
    textAlign: 'right',
  },
  evidenceOverflowButton: {
    alignItems: 'center',
    borderRadius: 14,
    borderWidth: 1,
    height: 30,
    justifyContent: 'center',
    width: 30,
  },
  evidenceSectionBlock: {
    borderBottomWidth: 0.5,
    paddingBottom: 1,
    paddingTop: 1,
  },
  evidenceSectionHeader: {
    alignItems: 'center',
    flexDirection: 'row',
    justifyContent: 'space-between',
  },
  evidenceSectionScore: {
    color: theme.colors.textDim,
    ...typography.metaStrong,
  },
  evidenceEmptyText: {
    ...typography.body,
    paddingHorizontal: theme.spacing.sm,
    paddingVertical: theme.spacing.md,
  },
  evidenceSectionSummary: {
    ...typography.meta,
    marginTop: 2,
  },
  evidenceSectionTitle: {
    ...typography.cardTitle,
  },
  evidenceSectionTitleWrap: {
    alignItems: 'baseline',
    flexDirection: 'row',
    gap: 10,
  },
  analysisSectionBlockLast: {
    borderBottomWidth: 0,
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
    gap: 8,
    marginTop: 2,
  },
  evidenceTable: {
    borderTopWidth: 1,
    marginTop: 3,
    overflow: 'hidden',
  },
  evidenceTimeframeChip: {
    borderRadius: theme.radius.pill,
    borderWidth: 1,
    paddingHorizontal: 8,
    paddingVertical: 2,
  },
  evidenceTimeframeChipActive: {
    backgroundColor: theme.colors.accentSoft,
    borderColor: '#1D4ED880',
  },
  evidenceTimeframeChipActiveText: {
    color: theme.colors.accent,
    ...typography.chipLabelCompact,
  },
  evidenceTimeframeChipText: {
    ...typography.chipLabelCompact,
  },
  evidenceTimeframeRow: {
    flexDirection: 'row',
    gap: 6,
    paddingRight: 12,
    marginTop: 8,
  },
  forwardMatrix: {
    borderTopWidth: 1,
    marginTop: 8,
    overflow: 'hidden',
  },
  forwardMatrixAvg: {
    flex: 0.8,
    fontSize: 10,
    fontWeight: '900',
    textAlign: 'right',
  },
  forwardMatrixHeadCell: {
    color: theme.colors.textDim,
    flex: 1,
    fontSize: 8,
    fontWeight: '900',
    letterSpacing: 0.8,
    textAlign: 'center',
    textTransform: 'uppercase',
  },
  forwardMatrixHeader: {
    flexDirection: 'row',
    gap: 4,
    paddingHorizontal: 8,
    paddingVertical: 6,
  },
  forwardMatrixRow: {
    alignItems: 'center',
    flexDirection: 'row',
    gap: 4,
    paddingHorizontal: 8,
    paddingVertical: 6,
  },
  forwardMatrixValueCell: {
    alignItems: 'center',
    borderRadius: theme.radius.sm,
    flex: 1,
    justifyContent: 'center',
    minHeight: 24,
  },
  forwardMatrixValueText: {
    fontSize: 9,
    fontWeight: '900',
  },
  forwardMatrixYear: {
    flex: 1.1,
    fontSize: 10,
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
    minWidth: 58,
    paddingHorizontal: 10,
    paddingVertical: 4,
  },
  forwardTabActive: {
    backgroundColor: '#F8FAFC',
    borderColor: theme.colors.borderStrong,
  },
  forwardTabActiveText: {
    color: theme.colors.text,
    fontSize: 9,
    fontWeight: '900',
    letterSpacing: 0.8,
    textAlign: 'center',
    textTransform: 'uppercase',
  },
  forwardTabText: {
    fontSize: 9,
    fontWeight: '900',
    letterSpacing: 0.8,
    textAlign: 'center',
    textTransform: 'uppercase',
  },
  forwardSubtitle: {
    fontSize: 11,
    fontWeight: '500',
    lineHeight: 16,
    marginTop: 3,
  },
  forwardTabs: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 6,
    marginTop: 8,
  },
  forwardTitle: {
    fontSize: 15,
    fontWeight: '900',
    marginTop: 2,
  },
  flexText: {
    flex: 1,
    minWidth: 0,
  },
  conclusionActions: {
    alignItems: 'center',
    flexDirection: 'row',
    gap: 12,
    justifyContent: 'space-between',
    marginTop: 10,
  },
  conclusionBody: {
    fontSize: 12.5,
    fontWeight: '500',
    lineHeight: 19,
    marginTop: 6,
  },
  conclusionHeader: {
    alignItems: 'flex-start',
    flexDirection: 'row',
    gap: 12,
  },
  conclusionLink: {
    paddingVertical: 4,
  },
  conclusionLinkText: {
    color: theme.colors.accent,
    fontSize: 12,
    fontWeight: '800',
  },
  conclusionScore: {
    fontSize: 13,
    fontWeight: '900',
    marginTop: 2,
  },
  conclusionSecondaryAction: {
    alignItems: 'center',
    borderRadius: theme.radius.pill,
    borderWidth: 1,
    minHeight: 32,
    paddingHorizontal: 12,
  },
  conclusionSecondaryActionText: {
    fontSize: 11,
    fontWeight: '800',
  },
  conclusionTitle: {
    fontSize: 15,
    fontWeight: '900',
    marginTop: 4,
  },
  conclusionSurface: {
    paddingBottom: 10,
    paddingTop: 6,
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
    fontSize: 18,
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
    minWidth: 0,
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
    ...typography.metaStrong,
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
    ...typography.metaStrong,
  },
  watchlistName: {
    ...typography.listRowMeta,
  },
  watchlistOverflowButton: {
    alignItems: 'center',
    borderRadius: theme.radius.pill,
    borderWidth: 1,
    height: 30,
    justifyContent: 'center',
    width: 30,
  },
  watchlistMetricBlock: {
    alignItems: 'flex-end',
    minWidth: 72,
  },
  watchlistPrice: {
    ...typography.cardTitle,
    textAlign: 'right',
  },
  watchlistPriceBlock: {
    alignItems: 'flex-end',
    gap: 4,
    marginLeft: 12,
  },
  watchlistRow: {
    alignItems: 'center',
    borderBottomWidth: 1,
    flexDirection: 'row',
    gap: 6,
    paddingHorizontal: 10,
    paddingVertical: 8,
  },
  watchlistRowLast: {
    borderBottomWidth: 0,
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
  watchlistScoreBlock: {
    alignItems: 'flex-start',
    gap: 1,
    minWidth: 36,
  },
  watchlistScoreLabel: {
    color: theme.colors.textDim,
    ...typography.chipLabelCompact,
  },
  watchlistScoreValue: {
    ...typography.cardTitle,
  },
  watchlistSectionTitle: {
    ...typography.actionStrong,
  },
  watchlistSelectionDot: {
    borderRadius: theme.radius.pill,
    height: 8,
    width: 8,
  },
  watchlistStateBlock: {
    alignItems: 'flex-start',
    flex: 1,
    minWidth: 0,
  },
  watchlistSymbol: {
    ...typography.listRowTitle,
  },
  watchlistTab: {
    ...typography.metaStrong,
  },
  watchlistTabActive: {
    borderBottomColor: theme.colors.accent,
    borderBottomWidth: 2,
    ...typography.metaStrong,
    fontWeight: '900',
    paddingBottom: 7,
  },
  watchlistTable: {
    borderBottomWidth: 1,
    borderTopWidth: 1,
    marginHorizontal: 0,
    marginTop: 8,
    overflow: 'hidden',
  },
  watchlistTabs: {
    alignItems: 'flex-start',
    flexDirection: 'row',
    gap: 16,
    marginTop: 8,
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
    marginTop: 8,
  },
  workflowIconTile: {
    alignItems: 'center',
    borderRadius: 10,
    height: 28,
    justifyContent: 'center',
    width: 28,
  },
  workflowSteps: {
    paddingRight: 16,
  },
  workflowStepCard: {
    borderRadius: 14,
    borderWidth: 1,
    flexDirection: 'row',
    gap: 8,
    minHeight: 44,
    paddingHorizontal: 9,
    paddingVertical: 8,
    width: 132,
  },
  workflowStepCopy: {
    flex: 1,
    gap: 3,
    justifyContent: 'center',
  },
  workflowStepTitle: {
    color: theme.colors.accent,
    fontSize: 11,
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
    paddingHorizontal: 4,
    paddingVertical: 4,
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
    ...typography.cardTitle,
    marginTop: 3,
  },
  wick: {
    borderRadius: 2,
    position: 'absolute',
    width: 2,
  },
});
