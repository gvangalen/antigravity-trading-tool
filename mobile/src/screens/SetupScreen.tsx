import { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigation, useRoute } from '@react-navigation/native';
import type { NavigationProp, RouteProp } from '@react-navigation/native';
import { Pressable, StyleSheet, Text, View, TouchableOpacity } from 'react-native';

import { BotDecisionCard } from '../components/cards/BotDecisionCard';
import { CardShell } from '../components/cards/CardShell';
import { InsightCard } from '../components/cards/InsightCard';
import { RiskWarningCard } from '../components/cards/RiskWarningCard';
import { StrategyStatusCard } from '../components/cards/StrategyStatusCard';
import { AssetContextHeader } from '../components/layout/AssetContextHeader';
import { SegmentedControl } from '../components/layout/SegmentedControl';
import { LoadingSkeletonCard } from '../components/layout/LoadingSkeletonCard';
import { ScreenContainer } from '../components/layout/ScreenContainer';
import { SectionHeader } from '../components/layout/SectionHeader';
import { StatusChip } from '../components/layout/StatusChip';
import { BottomSheet } from '../components/sheets/BottomSheet';
import { StrategyCard } from '../components/StrategyCard';
import { StatusTone, statusTones, theme } from '../constants/theme';

import { useApiResource } from '../hooks/useApiResource';
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

type UnknownRecord = Record<string, unknown>;
type SheetKey = 'setup' | 'strategy' | 'risk' | 'confirm' | null;

type SetupSummary = {
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

export function SetupScreen() {
  const route = useRoute<RouteProp<MainTabParamList, 'Setup'>>();
  const navigation = useNavigation<any>();
  const { openFinn } = useFinnOverlay();
  const [sheet, setSheet] = useState<SheetKey>(null);
  const [handledNotification, setHandledNotification] = useState<string | null>(null);
  const [actionStatus, setActionStatus] = useState<string>('');
  const [actionLoading, setActionLoading] = useState(false);
  const [activeTab, setActiveTab] = useState<'briefing' | 'actief' | 'setups' | 'strategies'>('briefing');

  const fetchStrategies = useCallback(() => intelligenceApi.queryStrategies({}), []);
  const strategiesResource = useApiResource<any | undefined>({
    fallbackData: undefined,
    fetcher: fetchStrategies,
    enabled: activeTab === 'strategies',
  });

  const [setupsFilter, setSetupsFilter] = useState<'alle' | 'actief' | 'inactief'>('actief');
  const [strategiesFilter, setStrategiesFilter] = useState<'alle' | 'actief' | 'inactief'>('actief');

  const fetchOverview = useCallback(() => mobileApi.overview(), []);
  const overviewResource = useApiResource<MobileOverviewResponse | undefined>({
    fallbackData: undefined,
    fetcher: fetchOverview,
  });

  const notificationType = route.params?.notificationType;
  const { context, updateContext } = useIntelligenceContext();
  const activeAsset = route.params?.symbol ?? context.asset;

  useEffect(() => {
    if (route.params?.symbol && route.params.symbol !== context.asset) {
      updateContext({ asset: route.params.symbol, screen: 'Setup' });
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

  const activeSetup = useMemo(() => extractActiveSetup(activeSetupResource.data), [activeSetupResource.data]);
  const setupId = (activeSetup as any)?.id;

  const fetchStrategy = useCallback(() => {
    if (setupId) {
      return intelligenceApi.getStrategyBySetup(setupId);
    }
    return intelligenceApi.activeStrategyToday();
  }, [setupId]);

  const strategyResource = useApiResource<StrategyResponse | undefined>({
    fallbackData: undefined,
    fetcher: fetchStrategy,
    enabled: !!setupId,
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
  const strategy = useMemo(
    () => mapStrategy(strategySource, activeSetupResource.data),
    [activeSetupResource.data, strategySource],
  );
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
    topSetupsResource.loading;
  const isStale =
    overviewResource.isStale ||
    activeSetupResource.isStale ||
    strategyResource.isStale ||
    botResource.isStale ||
    topSetupsResource.isStale;

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
      setActionStatus('Botactie is overgeslagen. De backend-status is bijgewerkt.');
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
      setActionStatus('Botactie is gemarkeerd als uitgevoerd.');
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
      edgeToEdge={true}
      refreshing={
        overviewResource.refreshing ||
        activeSetupResource.refreshing ||
        topSetupsResource.refreshing ||
        strategyResource.refreshing ||
        botResource.refreshing
      }
      onRefresh={async () => {
        await Promise.all([
          overviewResource.refresh(),
          activeSetupResource.refresh(),
          topSetupsResource.refresh(),
          strategyResource.refresh(),
          botResource.refresh(),
        ]);
      }}
    >
      <AssetContextHeader
        asset={activeAsset}
        context="FINN setup guidance"
        updatedAt={latestLabel([
          overviewResource.updatedAt,
          activeSetupResource.updatedAt,
          strategyResource.updatedAt,
          botResource.updatedAt,
        ])}
      />
      <SectionHeader
        label="Setup"
        title="FINN setup matcher"
        description="De beste setup eerst. Details pas wanneer ze je beslissing helpen."
      />

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
          <SetupTabBar activeTab={activeTab} onSelect={setActiveTab} />
          
          {activeTab === 'briefing' && (
            <FinnSetupBriefingCard
              decisionState={decisionState}
              isStale={isStale}
              onAskFinn={() =>
                openFinn({
                  prefill: `Leg uit waarom ${setup.name} nu de beste setup is voor ${activeAsset}. Benoem confidence, risico en de veilige volgende stap.`,
                  source: 'setup-briefing',
                  symbol: activeAsset,
                })
              }
              setup={setup}
            />
          )}
          
          {activeTab === 'actief' && (
            <>
              {/* 1. Actieve Setup */}
              <BestMatchingSetupCard onPress={() => setSheet('setup')} setup={setup} />
              
              {/* 2. Actieve Strategie */}
              {strategy && strategy.symbol && strategy.entryZone !== 'n/a' ? (
                <View style={{ paddingHorizontal: theme.spacing.lg, marginTop: theme.spacing.md }}>
                  <SectionHeader
                    label="Strategy"
                    title="Actieve strategie"
                    description="Het execution plan dat nu actief is voor dit asset."
                  />
                  <StrategyCard strategy={{
                    symbol: strategy.symbol,
                    bias: strategy.bias,
                    entryZone: strategy.entryZone,
                    targets: strategy.targets,
                    stopLoss: strategy.invalidation,
                    confidenceScore: strategy.confidence,
                    aiExplanation: strategy.explanation
                  }} />
                </View>
              ) : (
                <View style={{ paddingHorizontal: theme.spacing.lg, marginTop: theme.spacing.md }}>
                  <InsightCard
                    label="Strategy"
                    title="Geen actieve strategie"
                    body="Er is nog geen actieve strategie gekoppeld aan deze setup voor dit asset."
                    tone="neutral"
                  />
                </View>
              )}
            </>
          )}
          
          {activeTab === 'setups' && (
            <View style={{ paddingHorizontal: theme.spacing.lg }}>
              <SectionHeader
                label="Other Setups"
                title="Andere setups"
                description="Blader door alle setups of filter op status."
              />
              
              <View style={{ marginBottom: theme.spacing.md }}>
                <SegmentedControl
                  items={[
                    { key: 'alle', label: 'ALLE' },
                    { key: 'actief', label: 'ACTIEF' },
                    { key: 'inactief', label: 'INACTIEF' },
                  ]}
                  selected={setupsFilter}
                  onChange={(value) => setSetupsFilter(value as 'alle' | 'actief' | 'inactief')}
                />
              </View>

              <NextBestMatchesCard setups={topSetups.filter((item) => {
                const matchesTab = item.name !== setup.name;
                if (setupsFilter === 'alle') return matchesTab;
                if (setupsFilter === 'actief') return matchesTab && item.status === 'active';
                if (setupsFilter === 'inactief') return matchesTab && item.status !== 'active';
                return matchesTab;
              })} />
            </View>
          )}
          
          {activeTab === 'strategies' && (
            <View style={{ paddingHorizontal: theme.spacing.lg }}>
              <SectionHeader
                label="Strategies"
                title="Beheer strategieën"
                description="Lijst van al jouw opgeslagen strategieën."
              />
              
              <View style={{ marginBottom: theme.spacing.md }}>
                <SegmentedControl
                  items={[
                    { key: 'alle', label: 'ALLE' },
                    { key: 'actief', label: 'ACTIEF' },
                    { key: 'inactief', label: 'INACTIEF' },
                  ]}
                  selected={strategiesFilter}
                  onChange={(value) => setStrategiesFilter(value as 'alle' | 'actief' | 'inactief')}
                />
              </View>

              <TouchableOpacity
                style={{ backgroundColor: theme.colors.accent, padding: theme.spacing.sm, borderRadius: 6, alignItems: 'center', marginBottom: theme.spacing.md }}
                onPress={() => {
                  openFinn({
                    prefill: `Vraag letterlijk: "Wil je een strategie maken voor ${activeAsset}?"`,
                    source: 'strategy-create',
                    symbol: activeAsset,
                  });
                }}
              >
                <Text style={{ color: '#FFFFFF', fontWeight: 'bold', fontSize: 13 }}>+ NIEUWE STRATEGIE</Text>
              </TouchableOpacity>

              {strategiesResource.loading ? (
                <Text style={{ color: theme.colors.textSoft }}>Laden...</Text>
              ) : strategiesResource.data && strategiesResource.data.length > 0 ? (
                strategiesResource.data.filter((strat: any) => {
                  if (strategiesFilter === 'alle') return true;
                  if (strategiesFilter === 'actief') return strat.status === 'active';
                  if (strategiesFilter === 'inactief') return strat.status !== 'active';
                  return true;
                }).map((strat: any) => (
                  <StrategyListCard key={strat.id} strat={strat} />
                ))
              ) : (
                <InsightCard
                  label="Strategies"
                  title="Geen strategieën gevonden"
                  body="Je hebt nog geen strategieën aangemaakt."
                  tone="neutral"
                />
              )}
            </View>
          )}
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
            'Controleer backend/API status.'
          }
          tone="warning"
          cta="Pull to refresh"
        />
      ) : null}

      <BottomSheet visible={sheet === 'setup'} title="Active setup" onClose={() => setSheet(null)}>
        <SetupSheet setup={setup} />
      </BottomSheet>
      <BottomSheet visible={sheet === 'strategy'} title="Strategy detail" onClose={() => setSheet(null)}>
        <StrategySheet strategy={strategySource} fallback={strategy} />
      </BottomSheet>
      <BottomSheet visible={sheet === 'risk'} title="Risk explanation" onClose={() => setSheet(null)}>
        <RiskSheet decisionState={decisionState} setup={setup} botReasons={botMeta.reasons} />
      </BottomSheet>
      <BottomSheet visible={sheet === 'confirm'} title="Review bot action" onClose={() => setSheet(null)}>
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

function SetupTabBar({ activeTab, onSelect }: { activeTab: string; onSelect: (tab: 'briefing' | 'actief' | 'setups' | 'strategies') => void }) {
  return (
    <SegmentedControl
      items={[
        { key: 'briefing', label: 'Briefing' },
        { key: 'actief', label: 'Actief' },
        { key: 'setups', label: 'Setups' },
        { key: 'strategies', label: 'Strategies' },
      ]}
      selected={activeTab}
      onChange={(value) => onSelect(value as 'briefing' | 'actief' | 'setups' | 'strategies')}
    />
  );
}

function FinnSetupBriefingCard({
  decisionState,
  isStale,
  onAskFinn,
  setup,
}: {
  decisionState: ReturnType<typeof mapDecisionState>;
  isStale: boolean;
  onAskFinn: () => void;
  setup: SetupSummary;
}) {
  const { appearance } = useAppPreferences();
  const colors = preferenceColors(appearance);

  return (
    <View style={[styles.heroCard, { borderColor: colors.border }]}>
      <View style={styles.sectionTop}>
        <Text style={styles.heroKicker}>FINN SETUP BRIEFING</Text>
        <View style={styles.heroPill}>
          <View style={styles.heroPillDot} />
          <Text style={styles.heroPillText}>{riskLabelForScore(decisionState.score).toUpperCase()}</Text>
        </View>
      </View>

      <Text style={[styles.heroTitle, { color: colors.text }]}>{decisionState.title}</Text>

      <Text style={[styles.briefingCopy, { color: colors.textMuted }]}>
        <Text style={{ color: colors.text }}>Beste huidige match: {setup.name}. Confidence {setup.score}%.</Text> FINN ziet {setup.trend.toLowerCase()} condities en adviseert: {setup.action.toLowerCase()}.
      </Text>

      <View style={styles.briefingMetaRow}>
        <View style={{ flex: 1, gap: 2 }}>
          <Text style={{ fontSize: 11, color: colors.textDim, fontWeight: '700', letterSpacing: 0.5 }}>CONFIDENCE</Text>
          <Text style={{ fontSize: 14, color: colors.success, fontWeight: '700' }}>{setup.score}%</Text>
        </View>
        <View style={{ flex: 1, gap: 2 }}>
          <Text style={{ fontSize: 11, color: colors.textDim, fontWeight: '700', letterSpacing: 0.5 }}>RISK POSTURE</Text>
          <Text style={{ fontSize: 14, color: colors.text, fontWeight: '700' }}>{riskLabelForScore(decisionState.score)}</Text>
        </View>
      </View>

    </View>
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
        cta="Pull to refresh"
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
      <Text style={[styles.sheetTitle, { color: colors.text }]}>{botDecision.botName}</Text>
      <Text style={[styles.bodyText, { color: colors.textMuted }]}>{botDecision.reason}</Text>
      <View style={{ gap: 8, marginTop: theme.spacing.md }}>
        <View style={{ flexDirection: 'row', justifyContent: 'space-between' }}>
          <Text style={{ fontSize: 13, color: colors.textDim }}>Action</Text>
          <Text style={{ fontSize: 13, color: colors.text, fontWeight: '600' }}>{botDecision.action}</Text>
        </View>
        <View style={{ flexDirection: 'row', justifyContent: 'space-between' }}>
          <Text style={{ fontSize: 13, color: colors.textDim }}>Amount</Text>
          <Text style={{ fontSize: 13, color: colors.text, fontWeight: '600' }}>{botDecision.amount}</Text>
        </View>
        <View style={{ flexDirection: 'row', justifyContent: 'space-between' }}>
          <Text style={{ fontSize: 13, color: colors.textDim }}>Confidence</Text>
          <Text style={{ fontSize: 13, color: colors.text, fontWeight: '600' }}>{botDecision.confidence}</Text>
        </View>
        <View style={{ flexDirection: 'row', justifyContent: 'space-between' }}>
          <Text style={{ fontSize: 13, color: colors.textDim }}>Status</Text>
          <Text style={{ fontSize: 13, color: colors.text, fontWeight: '600' }}>{botMeta.status || 'review'}</Text>
        </View>
      </View>
      <Text style={styles.warningCopy}>{botDecision.guardrail}</Text>
      <View style={styles.sheetActions}>
        <ActionButton disabled={!canSkip || actionLoading} label="Sla botactie over" tone="warning" onPress={onSkip} />
        <ActionButton
          disabled={!botMeta.canMarkExecuted || actionLoading}
          label="Markeer uitgevoerd"
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
    <Pressable
      disabled={disabled}
      onPress={async () => {
        await triggerHaptic('impact');
        onPress();
      }}
      style={({ pressed }) => [
        styles.sheetButton,
        {
          backgroundColor: disabled ? colors.surfaceMuted : palette.background,
          borderColor: disabled ? colors.border : palette.border,
        },
        pressed && !disabled && styles.pressed,
      ]}
    >
      <Text style={[styles.sheetButtonText, { color: disabled ? colors.textDim : palette.color }]}>
        {label}
      </Text>
    </Pressable>
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
  return asArray(source).slice(0, 4).map((item) => {
    const score = clampScore(readNumber(item, ['score', 'match_score', 'setup_score'], 50));
    return {
      action: readString(item, ['action'], 'Review'),
      explanation: readString(item, ['explanation', 'setup_explanation'], 'Setup uit backend-ranking.'),
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
  return isRecord(active) ? active : record;
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
          {strat.setup_name?.toUpperCase() || strat.name?.toUpperCase() || 'SETUP'}  >  {strat.name?.toUpperCase() || 'STRATEGIE'}
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
  setupScore: {
    fontSize: 18,
    fontWeight: '900',
  },
  sheetActions: {
    gap: theme.spacing.sm,
    marginTop: theme.spacing.md,
  },
  sheetButton: {
    alignItems: 'center',
    borderRadius: theme.radius.button,
    borderWidth: 1,
    justifyContent: 'center',
    minHeight: 50,
  },
  sheetButtonText: {
    fontSize: 12,
    fontWeight: '900',
    letterSpacing: 1.1,
    textTransform: 'uppercase',
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
