import { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigation, useRoute } from '@react-navigation/native';
import type { NavigationProp, RouteProp } from '@react-navigation/native';
import { Pressable, StyleSheet, Text, View } from 'react-native';

import { BotDecisionCard } from '../components/cards/BotDecisionCard';
import { CardShell } from '../components/cards/CardShell';
import { InsightCard } from '../components/cards/InsightCard';
import { RiskWarningCard } from '../components/cards/RiskWarningCard';
import { StrategyStatusCard } from '../components/cards/StrategyStatusCard';
import { AssetContextHeader } from '../components/layout/AssetContextHeader';
import { LoadingSkeletonCard } from '../components/layout/LoadingSkeletonCard';
import { ScreenContainer } from '../components/layout/ScreenContainer';
import { SectionHeader } from '../components/layout/SectionHeader';
import { StatusChip } from '../components/layout/StatusChip';
import { BottomSheet } from '../components/sheets/BottomSheet';
import { StatusTone, statusTones, theme } from '../constants/theme';
import { mockBotDecision, mockStrategy } from '../data/mockFoundation';
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
  const navigation = useNavigation<NavigationProp<MainTabParamList>>();
  const route = useRoute<RouteProp<MainTabParamList, 'Setup'>>();
  const [sheet, setSheet] = useState<SheetKey>(null);
  const [handledNotification, setHandledNotification] = useState<string | null>(null);
  const [actionStatus, setActionStatus] = useState<string>('');
  const [actionLoading, setActionLoading] = useState(false);

  const fetchOverview = useCallback(() => mobileApi.overview(), []);
  const overviewResource = useApiResource<MobileOverviewResponse | undefined>({
    fallbackData: undefined,
    fetcher: fetchOverview,
  });

  const notificationType = route.params?.notificationType;
  const activeAsset = route.params?.symbol ?? overviewResource.data?.watchlist[0]?.symbol ?? 'BTC';
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

  const fetchStrategy = useCallback(() => intelligenceApi.activeStrategyToday(), []);
  const strategyResource = useApiResource<StrategyResponse | undefined>({
    fallbackData: undefined,
    fetcher: fetchStrategy,
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
      navigation.navigate('FINN', {
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
      navigation.navigate('FINN', {
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
        context="Action decision layer"
        updatedAt={latestLabel([
          overviewResource.updatedAt,
          activeSetupResource.updatedAt,
          strategyResource.updatedAt,
          botResource.updatedAt,
        ])}
      />
      <SectionHeader
        label="Action"
        title="Decision center"
        description="Setup, strategie en botbeslissing live uit de backend. Mobile blijft review-first."
      />

      {notificationType ? (
        <NotificationContextCard
          activeAsset={activeAsset}
          notificationType={notificationType}
          onAskFinn={() =>
            navigation.navigate('FINN', {
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
          <DecisionStateCard state={decisionState} stale={isStale} />
          <ActiveSetupCard onPress={() => setSheet('setup')} setup={setup} />
          <StrategyStatusCard {...strategy} onPress={() => setSheet('strategy')} />
          <BotDecisionCard
            {...botDecision}
            onAskWhy={() =>
              navigation.navigate('FINN', {
                prefill: `Leg uit waarom de botactie "${botDecision.action}" voor ${activeAsset} nu logisch of juist riskant is. Betrek setup, strategy en guardrails.`,
                source: 'bot-ask-why',
              })
            }
            onConfirm={() => setSheet('confirm')}
          />
          <RiskWarningCard
            severity={riskSeverity(decisionState.score, botDecision.action)}
            title={riskTitle(decisionState.score, botDecision.action)}
            body={riskBody(setup, strategy.status, botDecision.reason)}
            nextStep="Controleer setup, strategie en botstatus voordat je iets markeert of overslaat."
            onExplain={() => setSheet('risk')}
          />
          <TopSetupsCard setups={topSetups} />
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
          <View key={`${setup.name}-${index}`} style={[styles.setupRow, { backgroundColor: colors.surface, borderColor: colors.border }]}>
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
      <View style={styles.compactGrid}>
        <MiniMetric label="Entry" value={fallback.entryZone} />
        <MiniMetric label="Targets" value={fallback.targets.join(' / ')} />
        <MiniMetric label="Stop" value={fallback.invalidation} />
        <MiniMetric label="R:R" value={riskReward} />
        <MiniMetric label="Mode" value={mode} />
        <MiniMetric label="Base" value={Number.isFinite(baseAmount) ? formatMoney(baseAmount, 'EUR') : 'n/a'} />
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
      <View style={styles.compactGrid}>
        <MiniMetric label="Action" value={botDecision.action} />
        <MiniMetric label="Amount" value={botDecision.amount} />
        <MiniMetric label="Confidence" value={`${botDecision.confidence}`} />
        <MiniMetric label="Status" value={botMeta.status || 'review'} />
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
    <View style={[styles.miniMetric, { backgroundColor: colors.backgroundSoft, borderColor: colors.border }]}>
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
        <Pressable
          onPress={async () => {
            await triggerHaptic('selection');
            onAskFinn();
          }}
          style={({ pressed }) => [styles.notificationSecondary, { borderColor: colors.borderStrong }, pressed && styles.pressed]}
        >
          <Text style={[styles.notificationSecondaryText, { color: colors.textSoft }]}>Vraag FINN waarom</Text>
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

const styles = StyleSheet.create({
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
  compactGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: theme.spacing.sm,
    marginTop: theme.spacing.md,
  },
  heroTitle: {
    color: theme.colors.text,
    fontSize: 28,
    fontWeight: '900',
    lineHeight: 33,
    marginTop: 5,
  },
  kicker: {
    color: theme.colors.accent,
    fontSize: theme.typography.label,
    fontWeight: '900',
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
  metricLabel: {
    color: theme.colors.textDim,
    fontSize: theme.typography.label,
    fontWeight: '900',
    letterSpacing: 1.2,
    textTransform: 'uppercase',
  },
  metricValue: {
    color: theme.colors.text,
    fontSize: theme.typography.body,
    fontWeight: '900',
    lineHeight: 20,
    marginTop: 5,
  },
  miniMetric: {
    backgroundColor: theme.colors.backgroundSoft,
    borderColor: theme.colors.border,
    borderRadius: theme.radius.md,
    borderWidth: 1,
    flexBasis: '47%',
    flexGrow: 1,
    minHeight: 76,
    padding: theme.spacing.md,
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
    fontSize: 27,
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
    fontSize: 28,
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
  setupName: {
    color: theme.colors.text,
    fontSize: theme.typography.body,
    fontWeight: '900',
  },
  setupRow: {
    alignItems: 'center',
    backgroundColor: theme.colors.surface,
    borderColor: theme.colors.border,
    borderRadius: theme.radius.md,
    borderWidth: 1,
    flexDirection: 'row',
    gap: theme.spacing.md,
    justifyContent: 'space-between',
    padding: theme.spacing.md,
  },
  setupScore: {
    fontSize: 26,
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
});
