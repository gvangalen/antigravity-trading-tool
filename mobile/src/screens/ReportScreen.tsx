import { useCallback, useEffect, useMemo, useState } from 'react';
import { Feather } from '@expo/vector-icons';
import { useNavigation, useRoute } from '@react-navigation/native';
import type { NavigationProp, RouteProp } from '@react-navigation/native';
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';

import { CardShell } from '../components/cards/CardShell';
import { InsightCard } from '../components/cards/InsightCard';
import { LoadingSkeletonCard } from '../components/layout/LoadingSkeletonCard';
import { ScreenContainer } from '../components/layout/ScreenContainer';
import { StatusChip } from '../components/layout/StatusChip';
import { TodayWithFinnCard, type TodayWithFinnQueueItem } from '../components/workspace/TodayWithFinnCard';
import { WorkflowStepsRail } from '../components/workspace/WorkflowStepsRail';
import { SegmentedControl } from '../components/layout/SegmentedControl';
import { WorkspaceHeroSection } from '../components/workspace/WorkspaceHeroSection';
import { StatusTone, theme } from '../constants/theme';
import { typography } from '../constants/typography';
import { localizedBackendText, translate, translateFinnTag } from '../i18n';
import { triggerHaptic } from '../utils/haptics';
import { useFinnOverlay } from '../contexts/FinnOverlayContext';
import { useApiResource } from '../hooks/useApiResource';
import type { MainTabParamList } from '../navigation/MainTabNavigator';
import { preferenceColors, useAppPreferences } from '../preferences/AppPreferencesProvider';
import type { AppLanguage } from '../preferences/appLocale';
import { MobileOverviewResponse, MobileReportHighlight, MobileReportResponse, ReportResponse, assistantApi, intelligenceApi, mobileApi } from '../services/tradamindApi';
import { trackAssistantEvent } from '../services/assistantAnalytics';

type ReportPeriod = 'daily' | 'weekly' | 'monthly' | 'quarterly';
type ReportPayload = { full?: ReportResponse; mobile?: MobileReportResponse };
type FinnReflectionKey = 'today' | 'week' | 'blocked' | 'behavior';
type ReportCompanion =
  | {
      change: number;
      price: number;
      scores: Array<{ label: string; value: number; tone: StatusTone }>;
      type: 'market';
      volume: number;
    }
  | {
      items: Array<{
        interpretation: string;
        name: string;
        score: number | null;
        tone: StatusTone;
      }>;
      title: string;
      type: 'indicators';
    }
  | {
      matchLabel: string;
      name: string;
      score: number;
      symbol: string;
      timeframe: string;
      topSetups: Array<{ id: string; name: string; score: number }>;
      type: 'setup';
    }
  | {
      confidence: number | null;
      entry: number | null;
      name: string;
      stopLoss: number | null;
      symbol: string;
      targets: string[];
      timeframe: string;
      type: 'strategy';
    }
  | {
      action: string;
      amount: number | null;
      botName: string;
      confidence: number | null;
      reason: string;
      setupMatch: number | null;
      type: 'bot';
    };

type FinnReflectionResponse = {
  analysis?: Record<string, unknown> | null;
  body: string;
  headline: string;
  next?: string | null;
  risk?: string | null;
  summary?: string | null;
};

const FINN_REFLECTION_OPTIONS: Array<{ key: FinnReflectionKey; label: string; prompt: string }> = [
  { key: 'today', label: 'Today', prompt: 'Give me my Finn report for today' },
  { key: 'week', label: 'Weekly reflection', prompt: 'Give me my Finn report for this week' },
  { key: 'blocked', label: 'Blocked', prompt: 'Show me the blocked and guarded moments from my Finn report' },
  { key: 'behavior', label: '30 day behavior', prompt: 'Give me my behavioral Finn report' },
];

async function resolveReportPair<TMobile, TFull>(
  mobileFetcher: () => Promise<TMobile>,
  fullFetcher: () => Promise<TFull>,
): Promise<{ full?: TFull; mobile?: TMobile }> {
  const [mobileResult, fullResult] = await Promise.allSettled([mobileFetcher(), fullFetcher()]);
  return {
    full: fullResult.status === 'fulfilled' ? fullResult.value : undefined,
    mobile: mobileResult.status === 'fulfilled' ? mobileResult.value : undefined,
  };
}

export function ReportScreen() {
  const navigation = useNavigation<NavigationProp<MainTabParamList>>();
  const route = useRoute<RouteProp<MainTabParamList, 'Report'>>();
  const { openFinn } = useFinnOverlay();
  const [period, setPeriod] = useState<ReportPeriod>('daily');
  const activeSymbol = route.params?.symbol ?? '';
  const notificationType = route.params?.notificationType;
  const { appearance, language } = useAppPreferences();
  const colors = preferenceColors(appearance);
  const periods: Array<{ id: ReportPeriod; label: string; short: string }> = [
    { id: 'daily', label: translate(language, 'report.periodTab.daily'), short: 'D' },
    { id: 'weekly', label: translate(language, 'report.periodTab.weekly'), short: 'W' },
    { id: 'monthly', label: translate(language, 'report.periodTab.monthly'), short: 'M' },
    { id: 'quarterly', label: translate(language, 'report.periodTab.quarterly'), short: 'Q' },
  ];

  useEffect(() => {
    trackAssistantEvent({
      event_name: 'screen_view',
      page: 'report',
      flow_type: period,
      asset: activeSymbol,
      report_type: period,
    });
  }, [period, activeSymbol]);

  const fetchReport = useCallback(async (): Promise<ReportPayload> => {
    if (period === 'weekly') {
      return resolveReportPair(
        () => intelligenceApi.latestWeeklyReport('mobile'),
        () => intelligenceApi.latestWeeklyReportFull(),
      );
    }
    if (period === 'monthly') {
      return resolveReportPair(
        () => intelligenceApi.latestMonthlyReport('mobile'),
        () => intelligenceApi.latestMonthlyReportFull(),
      );
    }
    if (period === 'quarterly') {
      return resolveReportPair(
        () => intelligenceApi.latestQuarterlyReport('mobile'),
        () => intelligenceApi.latestQuarterlyReportFull(),
      );
    }

    return resolveReportPair(
      () => intelligenceApi.latestDailyReport(activeSymbol, 'mobile'),
      () => intelligenceApi.latestDailyReportFull(activeSymbol),
    );
  }, [activeSymbol, period]);

  const reportResource = useApiResource<ReportPayload>({
    fallbackData: {},
    fetcher: fetchReport,
  });
  const fetchOverview = useCallback(() => mobileApi.overview(activeSymbol), [activeSymbol]);
  const overviewResource = useApiResource<MobileOverviewResponse | undefined>({
    fallbackData: undefined,
    fetcher: fetchOverview,
  });

  const report = useMemo(
    () => mapMobileReport(reportResource.data.mobile, period, language, reportResource.data.full),
    [language, period, reportResource.data],
  );
  async function changePeriod(nextPeriod: ReportPeriod) {
    await triggerHaptic('selection');
    setPeriod(nextPeriod);
  }

  return (
    <ScreenContainer
      edgeToEdge={true}
      contentInsetBottom={320}
      refreshing={reportResource.refreshing || overviewResource.refreshing}
      onRefresh={async () => {
        await Promise.all([reportResource.refresh(), overviewResource.refresh()]);
      }}
    >
      <ReflectionTodayHero
        onAskFinn={() =>
          openFinn({
            prefill: `Translate the current ${period} report for ${activeSymbol} into conclusion, main risk and next safe step.`,
            source: 'reflection-today',
            symbol: activeSymbol,
          })
        }
        briefing={overviewResource.data?.finn_briefing}
        report={report}
      />
      <WorkflowStepsRail
        steps={[
          {
            body: translate(language, 'report.workflowStepResultBody'),
            icon: 'file-text',
            step: 1,
            title: translate(language, 'report.workflowStepResultTitle'),
          },
          {
            body: translate(language, 'report.workflowStepReviewBody'),
            icon: 'check-circle',
            step: 2,
            title: translate(language, 'report.workflowStepReviewTitle'),
          },
          {
            body: translate(language, 'report.workflowStepReportBody'),
            icon: 'book-open',
            step: 3,
            title: translate(language, 'report.workflowStepReportTitle'),
          },
        ]}
      />

      {reportResource.loading ? <LoadingSkeletonCard /> : null}

      {!reportResource.loading ? (
        <>
          <ReflectionFinnSection activeSymbol={activeSymbol} period={period} />
          <ReflectionTradingReportSection
            periodItems={periods.map((item) => ({ key: item.id, label: item.label }))}
            period={period}
            report={report}
            onChangePeriod={(value) => changePeriod(value)}
          />
          {reportResource.error && report.isUnavailable ? (
            <InsightCard
              label={translate(language, `report.period.${period}`)}
              title={translate(language, 'report.unavailableHeadline')}
              body={reportResource.error.message}
              tone="warning"
              cta={translate(language, 'portfolio.syncRefresh')}
            />
          ) : null}
        </>
      ) : null}

    </ScreenContainer>
  );
}

function ReflectionFinnSection({
  activeSymbol,
  period,
}: {
  activeSymbol: string;
  period: ReportPeriod;
}) {
  const { appearance } = useAppPreferences();
  const colors = preferenceColors(appearance);
  const defaultKey: FinnReflectionKey = period === 'weekly' ? 'week' : 'today';
  const [activeKey, setActiveKey] = useState<FinnReflectionKey>(defaultKey);
  const [expanded, setExpanded] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [cache, setCache] = useState<Record<string, FinnReflectionResponse>>({});

  useEffect(() => {
    setActiveKey(defaultKey);
  }, [defaultKey]);

  const activeOption =
    FINN_REFLECTION_OPTIONS.find((option) => option.key === activeKey) ?? FINN_REFLECTION_OPTIONS[0];
  const primaryOptions = FINN_REFLECTION_OPTIONS.filter((option) => option.key !== 'blocked').map((option) => ({
    key: option.key,
    label: option.key === 'behavior' ? '30 days' : option.label,
  }));
  const cacheKey = `${activeKey}:${activeSymbol || 'global'}:${period}`;
  const reflection = cache[cacheKey];
  const reflectionParagraphs = reflection ? splitReportParagraphs(reflection.body) : [];
  const presentation = reflection ? buildFinnReflectionPresentation(reflection) : null;

  const loadReflection = useCallback(async (force = false) => {
    if (!force && cache[cacheKey]) return;
    setLoading(true);
    setError(null);
    try {
      const envelope = await assistantApi.chat(
        activeOption.prompt,
        {
          page_type: 'Reflection',
          symbol: activeSymbol || undefined,
          timeframe: period,
        },
        undefined,
        'new',
      );
      setCache((current) => ({
        ...current,
        [cacheKey]: mapFinnReflectionEnvelope(envelope),
      }));
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : 'Finn reflection kon niet worden geladen.');
    } finally {
      setLoading(false);
    }
  }, [activeOption.prompt, activeSymbol, cache, cacheKey, period]);

  useEffect(() => {
    void loadReflection();
  }, [loadReflection]);

  return (
    <View style={styles.reflectionSection}>
      <View style={[styles.reflectionCard, { borderColor: colors.borderSubtle, backgroundColor: colors.surface }]}>
        <View style={styles.reflectionHeaderRow}>
          <View>
            <Text style={[styles.reflectionEyebrow, { color: theme.colors.accent }]}>FINN REPORTING</Text>
            <Text style={[styles.reflectionTitle, { color: colors.text }]}>Daily reflection with Finn</Text>
          </View>
        </View>

        <SegmentedControl
          compact
          items={primaryOptions}
          selected={activeKey}
          onChange={(value) => {
            setExpanded(false);
            setActiveKey(value as FinnReflectionKey);
          }}
        />

        {loading && !reflection ? (
          <View style={[styles.reflectionConclusionBox, { borderColor: colors.borderSubtle, backgroundColor: colors.surfaceMuted }]}>
            <Text style={[styles.reflectionConclusionBody, { color: colors.textMuted }]}>Finn reflection laden...</Text>
          </View>
        ) : null}

        {error && !reflection ? (
          <InsightCard label="FINN" title="Reflection unavailable" body={error} tone="warning" cta="Retry" />
        ) : null}

        {reflection ? (
          <>
            <View
              style={[
                styles.reflectionReportOverview,
                { borderColor: colors.borderSubtle, backgroundColor: colors.surfaceMuted, marginTop: theme.spacing.md },
              ]}
            >
              <View
                style={[styles.reflectionFinnHeadlineCard, { borderColor: colors.borderSubtle, backgroundColor: colors.surface }]}
              >
                <Text style={[styles.reflectionReportOverviewLabel, { color: theme.colors.accent }]}>
                  {activeOption.label.toUpperCase()}
                </Text>
                <Text style={[styles.reflectionFinnHeadlineText, { color: colors.text }]}>{presentation?.headline ?? reflection.headline}</Text>
                <Text style={[styles.reflectionFinnSupportText, { color: colors.textMuted }]}>
                  {presentation?.support ?? 'FINN needs a few explicit decisions before it can identify a meaningful pattern.'}
                </Text>
              </View>

              {presentation ? (
                <>
                  <View style={styles.reflectionFinnMetricRow}>
                    {presentation.metrics.map((item) => (
                      <View key={item.label} style={styles.reflectionFinnMetricInline}>
                        <View
                          style={[
                            styles.reflectionFinnMetricIcon,
                            { borderColor: colors.borderSubtle, backgroundColor: colors.surface },
                          ]}
                        >
                          <Feather color={colors.textDim} name={item.icon} size={16} />
                        </View>
                        <View style={styles.reflectionFinnMetricCopy}>
                          <Text style={[styles.reflectionFinnMetricInlineLabel, { color: colors.textDim }]}>{item.label}</Text>
                          <Text style={[styles.reflectionFinnMetricInlineValue, { color: colors.text }]}>{item.value}</Text>
                        </View>
                      </View>
                    ))}
                  </View>

                  <View style={[styles.reflectionFinnProgressWrap, { borderTopColor: colors.borderSubtle }]}>
                    <View style={styles.reflectionFinnProgressHeader}>
                      <Text style={[styles.reflectionFinnProgressLabel, { color: colors.textDim }]}>Evidence collected</Text>
                      <Text style={[styles.reflectionFinnProgressValue, { color: colors.textDim }]}>
                        {presentation.evidenceCount} of {presentation.evidenceTarget} decisions
                      </Text>
                    </View>
                    <View style={[styles.reflectionFinnProgressTrack, { backgroundColor: colors.borderSubtle }]}>
                      <View
                        style={[
                          styles.reflectionFinnProgressFill,
                          { backgroundColor: theme.colors.accent, width: `${presentation.evidenceProgress}%` },
                        ]}
                      />
                    </View>
                  </View>

                  <View
                    style={[
                      styles.reflectionFinnAsideCard,
                      { borderColor: colors.borderSubtle, backgroundColor: colors.surface },
                    ]}
                  >
                    <Text style={[styles.reflectionFinnAsideLabel, { color: theme.colors.accent }]}>WHEN REFLECTION APPEARS</Text>
                    <Text style={[styles.reflectionFinnAsideBody, { color: colors.textMuted }]}>{presentation.aside}</Text>
                  </View>
                </>
              ) : null}
            </View>

            <Pressable
              accessibilityRole="button"
              onPress={() => setExpanded((current) => !current)}
              style={[styles.reflectionFinnActivityRow, { borderColor: colors.borderSubtle, backgroundColor: colors.surface }]}
            >
              <View style={styles.reflectionFinnActivityLead}>
                <View
                  style={[
                    styles.reflectionFinnActivityIcon,
                    { borderColor: colors.borderSubtle, backgroundColor: colors.surfaceMuted },
                  ]}
                >
                  <Feather color={colors.textDim} name="file-text" size={16} />
                </View>
                <View style={styles.reflectionFinnActivityCopy}>
                  <Text style={[styles.reflectionFinnActivityTitle, { color: colors.text }]}>Activity & evidence</Text>
                  <Text style={[styles.reflectionFinnActivityBody, { color: colors.textMuted }]}>
                    See the decisions and events behind this reflection
                  </Text>
                </View>
              </View>
              <View style={styles.reflectionFinnActivityMeta}>
                <Text style={[styles.reflectionFinnActivityCount, { color: colors.textDim }]}>
                  {presentation?.eventsCount ?? 0} events
                </Text>
                <Feather color={colors.textDim} name={expanded ? 'chevron-down' : 'chevron-right'} size={18} />
              </View>
            </Pressable>

            {presentation && !presentation.hasLimitedEvidence ? (
              <View style={styles.reflectionFinnInsightGrid}>
                {presentation.insights.map((item) => (
                  <View
                    key={item.label}
                    style={[
                      styles.reflectionFinnInsightCard,
                      {
                        backgroundColor: item.background,
                        borderColor: item.border,
                      },
                    ]}
                  >
                    <Text style={[styles.reflectionFinnInsightLabel, { color: item.color }]}>{item.label}</Text>
                    <Text style={[styles.reflectionFinnInsightBody, { color: item.color }]}>{item.body}</Text>
                  </View>
                ))}
              </View>
            ) : null}

            {expanded ? (
              <View
                style={[
                  styles.reflectionFinnExpandedCard,
                  { borderColor: colors.borderSubtle, backgroundColor: colors.surfaceMuted },
                ]}
              >
                {reflectionParagraphs.length > 0 ? (
                  <View style={styles.reflectionReportRows}>
                    {reflectionParagraphs.map((paragraph, index) => (
                      <View
                        key={`${activeKey}-detail-${index}`}
                        style={[
                          styles.reflectionReportRow,
                          { borderBottomColor: colors.borderSubtle },
                          index === reflectionParagraphs.length - 1 && styles.reflectionReportRowLast,
                        ]}
                      >
                        <View style={styles.reflectionReportRowLead}>
                          <Feather color={colors.text} name="cpu" size={15} />
                          <View style={styles.reflectionReportRowCopy}>
                            <Text style={[styles.reflectionReportRowMeta, { color: colors.textDim }]}>FINN</Text>
                          </View>
                        </View>
                        <View style={styles.reflectionReportExpanded}>
                          <Text style={[styles.reflectionReportExpandedText, { color: colors.textMuted }]}>{paragraph}</Text>
                        </View>
                      </View>
                    ))}
                  </View>
                ) : null}

                <ReflectionFinnAnalysisBlocks analysis={reflection.analysis} />
              </View>
            ) : null}
          </>
        ) : null}
      </View>
    </View>
  );
}

function ReflectionFinnAnalysisBlocks({
  analysis,
}: {
  analysis?: Record<string, unknown> | null;
}) {
  const { appearance } = useAppPreferences();
  const colors = preferenceColors(appearance);
  const behavioralProfile = readRecord(analysis?.behavioral_profile);
  const trend = readRecord(analysis?.trend) ?? readRecord(analysis?.week_over_week) ?? readRecord(analysis?.month_over_month);
  const priorityEngine = readRecord(analysis?.priority_engine);
  const portfolioOS = readRecord(analysis?.portfolio_operating_system);
  const memoryV2 = readRecord(analysis?.memory_v2);
  const governanceSummary = readRecord(analysis?.governance_events_summary);
  const riskFlags = readArray(analysis?.risk_flags)
    .map((item) => readRecord(item))
    .filter((item): item is Record<string, unknown> => Boolean(item))
    .slice(0, 3);
  const habitCards = readArray(analysis?.habit_cards)
    .map((item) => readRecord(item))
    .filter((item): item is Record<string, unknown> => Boolean(item))
    .slice(0, 3);
  const nextActions = normalizeTargets(readField(portfolioOS ?? {}, ['next_best_actions']));

  if (!behavioralProfile && !trend && !priorityEngine && !portfolioOS && !memoryV2 && !governanceSummary) {
    return null;
  }

  return (
    <View style={styles.reflectionReportCompanions}>
      {(behavioralProfile || trend || riskFlags.length > 0 || habitCards.length > 0) ? (
        <View style={[styles.reflectionInlinePanel, { borderColor: colors.borderSubtle, backgroundColor: colors.surfaceMuted }]}>
          <View style={styles.reflectionInlinePanelHeader}>
            <Feather color={theme.colors.accent} name="activity" size={14} />
            <Text style={[styles.reflectionInlinePanelTitle, { color: colors.text }]}>Behavioral intelligence</Text>
          </View>
          {behavioralProfile ? (
            <>
              <Text style={[styles.reflectionInlinePrimary, { color: colors.text }]}>
                {readStringField(behavioralProfile, ['label']) || 'Behavioral profile'}
              </Text>
              <Text style={[styles.reflectionInlineVolume, { color: colors.textDim }]}>
                {readStringField(behavioralProfile, ['summary', 'watch_for']) || 'Geen behavioural summary beschikbaar.'}
              </Text>
            </>
          ) : null}
          {trend ? (
            <View style={styles.reflectionInlineScoreRow}>
              <View style={styles.reflectionInlineScoreChip}>
                <Text style={[styles.reflectionInlineScoreChipLabel, { color: colors.textDim }]}>Trend</Text>
                <Text style={[styles.reflectionInlineScoreChipValue, { color: colors.text }]}>
                  {readStringField(trend, ['status', 'momentum']) || 'Building'}
                </Text>
              </View>
              {readNumericField(analysis ?? {}, ['behavioral_balance_score']) !== null ? (
                <View style={styles.reflectionInlineScoreChip}>
                  <Text style={[styles.reflectionInlineScoreChipLabel, { color: colors.textDim }]}>Balance</Text>
                  <Text style={[styles.reflectionInlineScoreChipValue, { color: colors.text }]}>
                    {Math.round(readNumericField(analysis ?? {}, ['behavioral_balance_score']) ?? 0)}/100
                  </Text>
                </View>
              ) : null}
            </View>
          ) : null}
          {riskFlags.length > 0 ? (
            <View style={styles.reflectionReportRows}>
              {riskFlags.map((item, index) => (
                <View
                  key={`risk-flag-${index}`}
                  style={[
                    styles.reflectionReportRow,
                    { borderBottomColor: colors.borderSubtle },
                    index === riskFlags.length - 1 && styles.reflectionReportRowLast,
                  ]}
                >
                  <View style={styles.reflectionReportExpanded}>
                    <Text style={[styles.reflectionReportRowMeta, { color: colors.textDim }]}>
                      {readStringField(item, ['label', 'type']) || 'Brake'}
                    </Text>
                    <Text style={[styles.reflectionReportExpandedText, { color: colors.textMuted }]}>
                      {readStringField(item, ['summary']) || 'Geen extra toelichting.'}
                    </Text>
                  </View>
                </View>
              ))}
            </View>
          ) : null}
          {habitCards.length > 0 ? (
            <View style={styles.reflectionInlineScoreRow}>
              {habitCards.slice(0, 2).map((item, index) => (
                <View key={`habit-${index}`} style={styles.reflectionInlineScoreChip}>
                  <Text style={[styles.reflectionInlineScoreChipLabel, { color: colors.textDim }]}>
                    {readStringField(item, ['label']) || 'Habit'}
                  </Text>
                  <Text style={[styles.reflectionInlineScoreChipValue, { color: colors.text }]}>
                    {readStringField(item, ['status']) || 'Active'}
                  </Text>
                </View>
              ))}
            </View>
          ) : null}
        </View>
      ) : null}

      {(priorityEngine || portfolioOS || memoryV2 || governanceSummary) ? (
        <View style={[styles.reflectionInlinePanel, { borderColor: colors.borderSubtle, backgroundColor: colors.surfaceMuted }]}>
          <View style={styles.reflectionInlinePanelHeader}>
            <Feather color={theme.colors.accent} name="shield" size={14} />
            <Text style={[styles.reflectionInlinePanelTitle, { color: colors.text }]}>Governance layer</Text>
          </View>
          {portfolioOS ? (
            <>
              <Text style={[styles.reflectionInlinePrimary, { color: colors.text }]}>
                {readStringField(portfolioOS, ['operating_posture']) || 'Portfolio operating system'}
              </Text>
              <Text style={[styles.reflectionInlineVolume, { color: colors.textDim }]}>
                {readStringField(readRecord(readField(portfolioOS, ['control_plane'])), ['headline', 'why_now', 'habit_override']) || 'Geen governance summary beschikbaar.'}
              </Text>
            </>
          ) : null}
          {priorityEngine ? (
            <View style={styles.reflectionInlineMetricRow}>
              <View style={styles.reflectionInlineMetricBlock}>
                <Text style={[styles.reflectionInlineMetricLabel, { color: colors.textDim }]}>Priority engine</Text>
                <Text style={[styles.reflectionInlineMetricValue, { color: colors.text }]}>
                  {readStringField(priorityEngine, ['headline', 'why_now']) || 'Active'}
                </Text>
              </View>
            </View>
          ) : null}
          {memoryV2 ? (
            <View style={styles.reflectionInlineMetricRow}>
              <View style={styles.reflectionInlineMetricBlock}>
                <Text style={[styles.reflectionInlineMetricLabel, { color: colors.textDim }]}>Memory</Text>
                <Text style={[styles.reflectionInlineMetricValue, { color: colors.text }]}>
                  {readStringField(memoryV2, ['memory_pattern', 'behavioral_cost', 'recommended_rule']) || 'Active'}
                </Text>
              </View>
            </View>
          ) : null}
          {governanceSummary ? (
            <View style={styles.reflectionInlineScoreRow}>
              {[
                ['Review', readNumericField(governanceSummary, ['decision_review_count'])],
                ['Adherence', readNumericField(governanceSummary, ['plan_adherence_count'])],
                ['Outcome', readNumericField(governanceSummary, ['outcome_tracking_count'])],
              ]
                .filter((item) => item[1] !== null)
                .map(([label, value]) => (
                  <View key={String(label)} style={styles.reflectionInlineScoreChip}>
                    <Text style={[styles.reflectionInlineScoreChipLabel, { color: colors.textDim }]}>{label}</Text>
                    <Text style={[styles.reflectionInlineScoreChipValue, { color: colors.text }]}>{Math.round(Number(value))}</Text>
                  </View>
                ))}
            </View>
          ) : null}
          {nextActions.length > 0 ? (
            <View style={styles.reflectionReportRows}>
              {nextActions.slice(0, 3).map((item, index) => (
                <View
                  key={`next-action-${index}`}
                  style={[
                    styles.reflectionReportRow,
                    { borderBottomColor: colors.borderSubtle },
                    index === nextActions.slice(0, 3).length - 1 && styles.reflectionReportRowLast,
                  ]}
                >
                  <View style={styles.reflectionReportExpanded}>
                    <Text style={[styles.reflectionReportRowMeta, { color: colors.textDim }]}>Next action</Text>
                    <Text style={[styles.reflectionReportExpandedText, { color: colors.textMuted }]}>{item}</Text>
                  </View>
                </View>
              ))}
            </View>
          ) : null}
        </View>
      ) : null}
    </View>
  );
}

function ReflectionTodayHero({
  briefing,
  onAskFinn,
  report,
}: {
  briefing?: MobileOverviewResponse['finn_briefing'];
  onAskFinn: () => void;
  report: MappedReport;
}) {
  const { language } = useAppPreferences();
  const support = report.summary || translate(language, 'report.unavailableBody');
  const metaItems = [report.periodLabel, report.dateLabel, report.updatedAt].filter(
    (item): item is string => Boolean(item && item !== '-'),
  );
  const riskCount = report.highlights.filter((item) => item.tone === 'warning' || item.tone === 'danger').length;
  const openCount = report.isUnavailable ? 0 : 1;
  const queueItems: TodayWithFinnQueueItem[] = [
    {
      key: 'tasks',
      label: translate(language, 'queue.label.tasks'),
      value: openCount,
      body: report.isUnavailable ? translate(language, 'report.queueTaskUnavailable') : translate(language, 'report.queueTaskReview'),
      detail: report.isUnavailable
        ? translate(language, 'report.queueTaskDetailUnavailable')
        : translate(language, 'report.queueTaskDetailReady'),
    },
    {
      key: 'reviews',
      label: translate(language, 'queue.label.reviews'),
      value: report.highlights.length,
      body: report.highlights.length > 0 ? translate(language, 'report.queueReviewsCaptured') : translate(language, 'report.queueReviewsEmpty'),
    },
    {
      key: 'risks',
      label: translate(language, 'queue.label.risks'),
      value: riskCount,
      body: riskCount > 0 ? translate(language, 'report.queueRisksOpen') : translate(language, 'report.queueRisksClear'),
    },
    {
      key: 'performance',
      label: translate(language, 'queue.label.performance'),
      value: report.scores.filter((score) => score.value >= 50).length,
      body: translate(language, 'report.queuePerformance'),
    },
  ];

  return (
    <WorkspaceHeroSection>
      <TodayWithFinnCard
        headline={localizedBackendText(language, briefing?.summary?.trim(), report.headline)}
        support={support}
        metaItems={metaItems}
        queueItems={queueItems}
        queueStatusLabel={translate(language, 'common.itemsOpen', { count: openCount })}
      />
    </WorkspaceHeroSection>
  );
}

function ReflectionOverviewSection({ report }: { report: MappedReport }) {
  const { appearance, language } = useAppPreferences();
  const colors = preferenceColors(appearance);
  const cards = buildReflectionOverviewCards(report);

  if (cards.length === 0) {
    return null;
  }

  return (
    <View style={styles.reflectionSection}>
      <View style={styles.reflectionHeaderRow}>
        <View>
          <Text style={[styles.reflectionEyebrow, { color: theme.colors.accent }]}>
            {translate(language, 'report.yourReflection')}
          </Text>
          <Text style={[styles.reflectionTitle, { color: colors.text }]}>
            {translate(language, 'report.todayTitle')}
          </Text>
        </View>
        <Text style={[styles.reflectionDate, { color: colors.textDim }]}>{report.dateLabel}</Text>
      </View>

      <View style={[styles.reflectionCard, { borderColor: colors.borderSubtle, backgroundColor: colors.surface }]}>
        {cards.map((card, index) => (
          <View
            key={card.label}
            style={[
              styles.reflectionInsightRow,
              { borderBottomColor: colors.borderSubtle },
              index === cards.length - 1 && styles.reflectionInsightRowLast,
            ]}
          >
            <View style={[styles.reflectionInsightIcon, { backgroundColor: card.bg, borderColor: card.border }]}>
              <Feather color={card.color} name={card.icon} size={16} />
            </View>
            <View style={styles.reflectionInsightCopy}>
              <Text style={[styles.reflectionInsightLabel, { color: card.color }]}>{card.label}</Text>
              <Text numberOfLines={1} style={[styles.reflectionInsightTitle, { color: colors.text }]}>
                {card.title}
              </Text>
              <Text numberOfLines={1} style={[styles.reflectionInsightBody, { color: colors.textMuted }]}>
                {card.body}
              </Text>
              <Text style={[styles.reflectionInsightFoot, { color: card.color }]}>{card.foot}</Text>
            </View>
            <Feather color={colors.textDim} name="chevron-right" size={18} />
          </View>
        ))}
      </View>
    </View>
  );
}

function ReflectionTradingReportSection({
  onChangePeriod,
  period,
  periodItems,
  report,
}: {
  onChangePeriod: (period: ReportPeriod) => void;
  period: ReportPeriod;
  periodItems: Array<{ key: ReportPeriod; label: string }>;
  report: MappedReport;
}) {
  const { appearance, language } = useAppPreferences();
  const colors = preferenceColors(appearance);
  const scoreItems = report.scores.slice(0, 4);
  const sectionRows = report.fullSections.slice(0, 6);
  const reportTitle = reflectionReportTitle(report.periodLabel);
  const [reportExpanded, setReportExpanded] = useState(true);

  return (
    <View style={styles.reflectionSection}>
      <View style={[styles.reflectionCard, { borderColor: colors.borderSubtle, backgroundColor: colors.surface }]}>
        <Text style={[styles.reflectionReportLabel, { color: theme.colors.accent }]}>
          {translate(language, 'report.tradingReport')}
        </Text>
        <Text style={[styles.reflectionReportSub, { color: colors.textMuted }]}>
          {translate(language, 'report.tradingReportSubtitle')}
        </Text>

        <SegmentedControl
          compact
          items={periodItems}
          selected={period}
          onChange={(value) => onChangePeriod(value as ReportPeriod)}
        />

        <View
          style={[
            styles.reflectionReportOverview,
            { borderColor: colors.borderSubtle, backgroundColor: colors.surfaceMuted },
          ]}
        >
          <View style={styles.reflectionReportOverviewHeader}>
            <View style={styles.reflectionReportOverviewLead}>
              <View style={[styles.reflectionReportAccentBar, { backgroundColor: theme.colors.accent }]} />
              <View style={styles.reflectionReportOverviewCopy}>
                <Text style={[styles.reflectionReportOverviewLabel, { color: theme.colors.accent }]}>
                  {translate(language, 'report.overviewLabel')}
                </Text>
                <Text style={[styles.reflectionReportOverviewTitle, { color: colors.text }]}>{reportTitle}</Text>
                <View style={styles.reflectionReportOverviewMeta}>
                  <Feather color={colors.textDim} name="calendar" size={13} />
                  <Text style={[styles.reflectionReportOverviewMetaText, { color: colors.textDim }]}>
                    {translate(language, 'report.periodMeta', { date: report.dateLabel })}
                  </Text>
                </View>
              </View>
            </View>

            <View
              style={[
                styles.reflectionScoreCluster,
                { borderColor: colors.borderSubtle, backgroundColor: colors.surface },
              ]}
            >
              <View style={styles.reflectionScoreGrid}>
                {scoreItems.map((score) => (
                  <View key={score.label} style={[styles.reflectionScoreCell, { borderColor: colors.borderSubtle }]}>
                    <View style={[styles.reflectionScoreIconWrap, { backgroundColor: softBackgroundForTone(score.tone) }]}>
                      <Feather color={colorForTone(score.tone)} name={iconForScoreLabel(score.label)} size={13} />
                    </View>
                    <Text style={[styles.reflectionScoreLabel, { color: colors.textDim }]}>{score.label}</Text>
                    <Text style={[styles.reflectionScoreValue, { color: colorForTone(score.tone) }]}>{score.value}</Text>
                  </View>
                ))}
              </View>
            </View>
          </View>

          <View style={[styles.reflectionReportOverviewFooter, { borderTopColor: colors.borderSubtle }]}>
            <View style={styles.reflectionReportOverviewStatus}>
              <Feather color={theme.colors.accent} name="info" size={13} />
              <Text style={[styles.reflectionReportOverviewStatusText, { color: colors.textDim }]}>
                {translate(language, 'report.validated')}
              </Text>
            </View>
            <Text style={[styles.reflectionReportOverviewStatusMeta, { color: colors.textDim }]}>
              {translate(language, 'report.updatedAt', { value: report.updatedAt })}
            </Text>
          </View>
        </View>

        <Pressable
          accessibilityRole="button"
          onPress={() => setReportExpanded((current) => !current)}
          style={[styles.reflectionReportToggle, { borderColor: colors.borderSubtle, backgroundColor: colors.surface }]}
        >
          <Text style={[styles.reflectionReportToggleText, { color: colors.text }]}>
            {translate(language, reportExpanded ? 'report.hideFull' : 'report.showFull')}
          </Text>
          <Feather
            color={colors.textDim}
            name={reportExpanded ? 'chevron-up' : 'chevron-down'}
            size={16}
          />
        </Pressable>

        {reportExpanded ? (
          <>
            <Text style={[styles.reflectionReportIntro, { color: colors.text }]}>
              {translate(language, 'report.greeting')}
            </Text>
            <Text style={[styles.reflectionReportLead, { color: colors.textMuted }]}>
              {translate(language, 'report.lead')}
            </Text>
            <Text style={[styles.reflectionReportSummary, { color: colors.textMuted }]}>
              {report.summary || translate(language, 'report.unavailableBody')}
            </Text>

            {sectionRows.length > 0 ? (
              <View style={styles.reflectionReportRows}>
                {sectionRows.map((section, index) => (
                  <View
                    key={`${section.label}-${index}`}
                    style={[
                      styles.reflectionReportRow,
                      { borderBottomColor: colors.borderSubtle },
                      index === sectionRows.length - 1 && styles.reflectionReportRowLast,
                    ]}
                  >
                    <View style={styles.reflectionReportRowLead}>
                      <Feather
                        color={colors.text}
                        name={iconForReflectionSection(section.title)}
                        size={15}
                      />
                      <View style={styles.reflectionReportRowCopy}>
                        <Text style={[styles.reflectionReportRowMeta, { color: colors.textDim }]}>
                          {section.label}
                        </Text>
                      </View>
                    </View>
                    <View style={styles.reflectionReportExpanded}>
                      {section.paragraphs.map((paragraph, paragraphIndex) => (
                        <Text
                          key={`${section.title}-${paragraphIndex}`}
                          style={[styles.reflectionReportExpandedText, { color: colors.textMuted }]}
                        >
                          {paragraph}
                        </Text>
                      ))}
                      {section.companions?.length ? (
                        <View style={styles.reflectionReportCompanions}>
                          {section.companions.slice(0, 1).map((companion, companionIndex) => (
                            <ReflectionEmbeddedCompanion
                              companion={companion}
                              key={`${section.title}-${companion.type}-${companionIndex}`}
                            />
                          ))}
                        </View>
                      ) : null}
                    </View>
                  </View>
                ))}
              </View>
            ) : (
              <View style={[styles.reflectionConclusionBox, { borderColor: colors.borderSubtle, backgroundColor: colors.surfaceMuted }]}>
                <Text style={[styles.reflectionConclusionBody, { color: colors.textMuted }]}>
                  {translate(language, 'report.unavailableBody')}
                </Text>
              </View>
            )}

            <View style={[styles.reflectionConclusionBox, { borderColor: colors.borderSubtle, backgroundColor: colors.surfaceMuted }]}>
              <Text style={[styles.reflectionConclusionTitle, { color: colors.text }]}>
                {translate(language, 'report.conclusion')}
              </Text>
              <Text style={[styles.reflectionConclusionBody, { color: colors.textMuted }]}>
                {report.conclusionTitle || report.outlook || translate(language, 'report.unavailableHeadline')}
              </Text>
            </View>

            <View style={styles.reflectionReportFooter}>
              <Text style={[styles.reflectionFooterMeta, { color: colors.textDim }]}>
                {translate(language, 'report.lastReflection', { value: report.updatedAt })}
              </Text>
              <Text style={[styles.reflectionFooterMeta, { color: colors.success }]}>
                {translate(language, 'report.allReviewed')}
              </Text>
            </View>
          </>
        ) : null}
      </View>
    </View>
  );
}

function ReflectionEmbeddedCompanion({ companion }: { companion: ReportCompanion }) {
  const { appearance, language } = useAppPreferences();
  const colors = preferenceColors(appearance);

  if (companion.type === 'market') {
    return (
      <View style={[styles.reflectionInlinePanel, { borderColor: colors.borderSubtle, backgroundColor: colors.surfaceMuted }]}>
        <View style={styles.reflectionInlinePanelHeader}>
          <Feather color={theme.colors.accent} name="activity" size={14} />
          <Text style={[styles.reflectionInlinePanelTitle, { color: colors.text }]}>
            {translate(language, 'report.marketAnalysis')}
          </Text>
        </View>
        <View style={styles.reflectionInlineMetricRow}>
          <View style={styles.reflectionInlineMetricBlock}>
            <Text style={[styles.reflectionInlineMetricLabel, { color: colors.textDim }]}>
              {translate(language, 'report.bitcoinPrice')}
            </Text>
            <Text style={[styles.reflectionInlineMetricValue, { color: colors.text }]}>{formatCurrency(companion.price)}</Text>
          </View>
          <Text style={[styles.reflectionInlineChange, { color: companion.change >= 0 ? theme.colors.success : theme.colors.danger }]}>
            {formatSignedPercent(companion.change)}
          </Text>
        </View>
        <Text style={[styles.reflectionInlineVolume, { color: colors.textDim }]}>
          {translate(language, 'report.volume')} {formatFullNumber(companion.volume)}
        </Text>
        <View style={styles.reflectionInlineScoreRow}>
          {companion.scores.slice(0, 4).map((score) => (
            <View key={score.label} style={styles.reflectionInlineScoreChip}>
              <Text style={[styles.reflectionInlineScoreChipLabel, { color: colors.textDim }]}>{score.label}</Text>
              <Text style={[styles.reflectionInlineScoreChipValue, { color: colorForTone(score.tone) }]}>{score.value}</Text>
            </View>
          ))}
        </View>
      </View>
    );
  }

  if (companion.type === 'indicators') {
    return (
      <View style={[styles.reflectionInlinePanel, { borderColor: colors.borderSubtle, backgroundColor: colors.surfaceMuted }]}>
        <View style={styles.reflectionInlinePanelHeader}>
          <Feather color={theme.colors.accent} name="list" size={14} />
          <Text style={[styles.reflectionInlinePanelTitle, { color: colors.text }]}>{companion.title}</Text>
        </View>
        {companion.items.slice(0, 3).map((item, index) => (
          <View
            key={`${item.name}-${index}`}
            style={[
              styles.reflectionInlineIndicatorRow,
              index === companion.items.slice(0, 3).length - 1 && styles.reflectionInlineIndicatorRowLast,
            ]}
          >
            <View style={styles.reflectionInlineIndicatorCopy}>
              <Text style={[styles.reflectionInlineIndicatorTitle, { color: colors.text }]}>{formatDecisionMomentTitle(item.name)}</Text>
              <Text numberOfLines={1} style={[styles.reflectionInlineIndicatorText, { color: colors.textDim }]}>
                {compactText(item.interpretation, 56)}
              </Text>
            </View>
            {item.score === null ? null : (
              <Text style={[styles.reflectionInlineIndicatorScore, { color: colorForTone(item.tone) }]}>{item.score}</Text>
            )}
          </View>
        ))}
      </View>
    );
  }

  if (companion.type === 'setup') {
    return (
      <View style={[styles.reflectionInlinePanel, { borderColor: colors.borderSubtle, backgroundColor: colors.surfaceMuted }]}>
        <View style={styles.reflectionInlinePanelHeader}>
          <Feather color={theme.colors.accent} name="target" size={14} />
          <Text style={[styles.reflectionInlinePanelTitle, { color: colors.text }]}>
            {translate(language, 'report.bestSetup')}
          </Text>
        </View>
        <Text style={[styles.reflectionInlinePrimary, { color: colors.text }]}>{companion.name}</Text>
        <Text style={[styles.reflectionInlineSub, { color: colors.textDim }]}>{companion.symbol} · {companion.timeframe}</Text>
        <View style={styles.reflectionInlineMetricRow}>
          <Text style={[styles.reflectionInlineMetricLabel, { color: colors.textDim }]}>
            {translate(language, 'report.match')}
          </Text>
          <Text style={[styles.reflectionInlineMetricScore, { color: colorForTone(toneForScore(companion.score)) }]}>
            {Math.round(companion.score)}%
          </Text>
        </View>
      </View>
    );
  }

  if (companion.type === 'strategy') {
    return (
      <View style={[styles.reflectionInlinePanel, { borderColor: colors.borderSubtle, backgroundColor: colors.surfaceMuted }]}>
        <View style={styles.reflectionInlinePanelHeader}>
          <Feather color={theme.colors.accent} name="crosshair" size={14} />
          <Text style={[styles.reflectionInlinePanelTitle, { color: colors.text }]}>
            {translate(language, 'report.activeStrategy')}
          </Text>
        </View>
        <Text style={[styles.reflectionInlinePrimary, { color: colors.text }]}>{companion.name}</Text>
        <Text style={[styles.reflectionInlineSub, { color: colors.textDim }]}>{companion.symbol} · {companion.timeframe}</Text>
        <View style={styles.reflectionInlineScoreRow}>
          <View style={styles.reflectionInlineScoreChip}>
            <Text style={[styles.reflectionInlineScoreChipLabel, { color: colors.textDim }]}>
              {translate(language, 'report.entry')}
            </Text>
            <Text style={[styles.reflectionInlineScoreChipValue, { color: colors.text }]}>{formatCurrency(companion.entry ?? 0)}</Text>
          </View>
          <View style={styles.reflectionInlineScoreChip}>
            <Text style={[styles.reflectionInlineScoreChipLabel, { color: colors.textDim }]}>
              {translate(language, 'report.stop')}
            </Text>
            <Text style={[styles.reflectionInlineScoreChipValue, { color: colors.text }]}>{formatCurrency(companion.stopLoss ?? 0)}</Text>
          </View>
          <View style={styles.reflectionInlineScoreChip}>
            <Text style={[styles.reflectionInlineScoreChipLabel, { color: colors.textDim }]}>
              {translate(language, 'report.confShort')}
            </Text>
            <Text style={[styles.reflectionInlineScoreChipValue, { color: colorForTone(toneForScore(companion.confidence ?? 0)) }]}>
              {companion.confidence === null ? '-' : `${Math.round(companion.confidence)}%`}
            </Text>
          </View>
        </View>
      </View>
    );
  }

  if (companion.type === 'bot') {
    return (
      <View style={[styles.reflectionInlinePanel, { borderColor: colors.borderSubtle, backgroundColor: colors.surfaceMuted }]}>
        <View style={styles.reflectionInlinePanelHeader}>
          <Feather color={theme.colors.accent} name="cpu" size={14} />
          <Text style={[styles.reflectionInlinePanelTitle, { color: colors.text }]}>
            {translate(language, 'report.botSnapshot')}
          </Text>
        </View>
        <Text style={[styles.reflectionInlinePrimary, { color: colors.text }]}>{companion.botName}</Text>
        <View style={styles.reflectionInlineMetricRow}>
          <Text style={[styles.reflectionInlineMetricLabel, { color: colors.textDim }]}>
            {translate(language, 'report.action')}
          </Text>
          <Text style={[styles.reflectionInlineMetricScore, { color: colorForTone(companion.action === 'buy' ? 'success' : companion.action === 'sell' ? 'danger' : 'neutral') }]}>
            {companion.action.toUpperCase()}
          </Text>
        </View>
        <Text numberOfLines={2} style={[styles.reflectionInlineVolume, { color: colors.textDim }]}>
          {compactText(companion.reason, 92)}
        </Text>
      </View>
    );
  }

  return null;
}

function ReflectionWorkspaceHero({
  activeSymbol,
  onAskFinn,
  report,
}: {
  activeSymbol: string;
  onAskFinn: () => void;
  report: MappedReport;
}) {
  const { appearance, language } = useAppPreferences();
  const colors = preferenceColors(appearance);

  return (
    <View style={styles.summaryGridWrap}>
      <View style={styles.summaryTop}>
        <View style={styles.summaryCopy}>
          <Text style={styles.heroLabel}>Reflection briefing</Text>
          <Text style={[styles.heroTitle, { color: colors.text }]}>{activeSymbol} {report.periodLabel}</Text>
          <Text style={[styles.notificationBody, { color: colors.textMuted }]}>{report.headline}</Text>
        </View>
        <StatusChip label={report.periodLabel} tone={report.overallTone} />
      </View>
      <View style={styles.summaryGrid}>
        <View style={[styles.summaryCard, { borderColor: colors.border, backgroundColor: colors.surface }]}>
          <Text style={[styles.summaryLabel, { color: colors.textDim }]}>Reading</Text>
          <Text style={[styles.summaryValue, { color: colors.text }]}>{report.readingMinutes} min</Text>
        </View>
        <View style={[styles.summaryCard, { borderColor: colors.border, backgroundColor: colors.surface }]}>
          <Text style={[styles.summaryLabel, { color: colors.textDim }]}>Sections</Text>
          <Text style={[styles.summaryValue, { color: colors.text }]}>{report.fullSections.length}</Text>
        </View>
      </View>
      <View style={styles.heroFooter}>
        <Text style={[styles.integrity, { color: colors.textDim }]}>Integrity check voltooid</Text>
        <Text style={[styles.generated, { color: colors.textDim }]}>Update: {report.generatedLabel}</Text>
      </View>
      <Pressable onPress={onAskFinn} style={styles.reportAction}>
        <Text style={styles.reportActionText}>{translate(language, 'report.askTranslate')}</Text>
      </Pressable>
    </View>
  );
}

type MappedReport = {
  fullSections: Array<{
    companions?: ReportCompanion[];
    label: string;
    paragraphs: string[];
    title: string;
    tone: StatusTone;
  }>;
  isUnavailable: boolean;
  periodLabel: string;
  readingMinutes: number;
  dateLabel: string;
  generatedLabel: string;
  updatedAt: string;
  headline: string;
  summary: string;
  marketAnalysis: string;
  outlook: string;
  conclusionTitle: string;
  overallTone: StatusTone;
  scores: Array<{ label: string; value: number; tone: StatusTone }>;
  highlights: Array<{
    category: string;
    name: string;
    score: number | null;
    interpretation: string;
    tone: StatusTone;
  }>;
};

function ReflectionSummaryGrid({ report }: { report: MappedReport }) {
  const { appearance, language } = useAppPreferences();
  const colors = preferenceColors(appearance);
  const items = [
    { label: 'Conclusion', value: report.conclusionTitle, tone: report.overallTone },
    { label: 'Market', value: report.marketAnalysis, tone: 'accent' as const },
    { label: 'Outlook', value: report.outlook, tone: 'warning' as const },
    { label: 'Read time', value: `${report.readingMinutes} min`, tone: 'neutral' as const },
    ...report.scores.slice(0, 4).map((score) => ({
      label: score.label,
      value: String(score.value),
      tone: score.tone,
    })),
  ];

  return (
    <View style={styles.summaryGridWrap}>
      <View style={styles.summaryGrid}>
        {items.map((item, index) => (
          <View
            key={`${item.label}-${index}`}
            style={[styles.summaryCard, { borderColor: colors.border, backgroundColor: colors.surface }]}
          >
            <Text style={[styles.summaryLabel, { color: colors.textDim }]}>{item.label}</Text>
            <Text style={[styles.summaryValue, { color: colorForTone(item.tone) }]} numberOfLines={4}>
              {item.value}
            </Text>
          </View>
        ))}
      </View>
    </View>
  );
}

function ReportNotificationCard({
  notificationType,
  onAskFinn,
  symbol,
}: {
  notificationType: string;
  onAskFinn: () => void;
  symbol: string;
}) {
  const { appearance, language } = useAppPreferences();
  const colors = preferenceColors(appearance);

  return (
    <View style={{ paddingVertical: theme.spacing.md, paddingHorizontal: theme.spacing.lg }}>
      <View style={styles.heroTop}>
        <View>
          <Text style={styles.heroLabel}>{translate(language, 'report.pushContextLabel')}</Text>
          <Text style={[styles.notificationTitle, { color: colors.text }]}>
            {notificationType === 'report_ready'
              ? translate(language, 'report.pushReadyTitle')
              : translate(language, 'report.pushContextTitle')}
          </Text>
        </View>
        <StatusChip label={symbol} tone="accent" />
      </View>
      <Text style={[styles.notificationBody, { color: colors.textMuted }]}>
        {translate(language, 'report.pushBody')}
      </Text>
      <Pressable
        onPress={async () => {
          await triggerHaptic('selection');
          onAskFinn();
        }}
        style={({ pressed }) => [styles.notificationButton, pressed && styles.pressed]}
      >
        <Text style={styles.notificationButtonText}>{translate(language, 'report.askExplain')}</Text>
      </Pressable>
    </View>
  );
}

function HighlightCard({
  highlight,
}: {
  highlight: MappedReport['highlights'][number];
}) {
  const { appearance, language } = useAppPreferences();
  const colors = preferenceColors(appearance);

  return (
    <View style={{ paddingVertical: theme.spacing.md, paddingHorizontal: theme.spacing.lg }}>
      <View style={styles.highlightTop}>
        <View>
          <Text style={[styles.highlightCategory, { color: colors.textDim }]}>{highlight.category}</Text>
          <Text style={[styles.highlightName, { color: colors.text }]}>{highlight.name}</Text>
        </View>
        {highlight.score === null ? null : <StatusChip label={String(highlight.score)} tone={highlight.tone} />}
      </View>
      <Text style={[styles.highlightText, { color: colors.textMuted }]}>{highlight.interpretation}</Text>
    </View>
  );
}

function ReportSectionCard({
  section,
}: {
  section: MappedReport['fullSections'][number];
}) {
  const { appearance, language } = useAppPreferences();
  const colors = preferenceColors(appearance);

  return (
    <View style={{ paddingVertical: theme.spacing.md, paddingHorizontal: theme.spacing.lg }}>
      <View style={[styles.readerCard, { borderColor: colors.border, backgroundColor: colors.surface }]}>
      <View style={styles.reportSectionHeader}>
        <View>
          <Text style={[styles.reportSectionLabel, { color: colors.textDim }]}>{section.label}</Text>
          <Text style={[styles.reportSectionTitle, { color: colors.text }]}>{section.title}</Text>
        </View>
        <StatusChip label={translate(language, 'common.read')} tone={section.tone} />
      </View>

      <View style={styles.paragraphs}>
        {section.paragraphs.map((paragraph, index) => (
          <Text key={`${section.title}-${index}`} style={[styles.reportParagraph, { color: colors.textMuted }]}>
            {paragraph}
          </Text>
        ))}
      </View>

      {section.companions?.length ? (
        <View style={styles.sectionCompanions}>
          {section.companions.map((companion, index) => (
            <ReportCompanionCard companion={companion} key={`${section.title}-${companion.type}-${index}`} />
          ))}
        </View>
      ) : null}
      </View>
    </View>
  );
}

function ReportCompanionCard({ companion }: { companion: ReportCompanion }) {
  if (companion.type === 'market') return <MarketCompanionCard companion={companion} />;
  if (companion.type === 'indicators') return <IndicatorCompanionCard companion={companion} />;
  if (companion.type === 'setup') return <SetupCompanionCard companion={companion} />;
  if (companion.type === 'strategy') return <StrategyCompanionCard companion={companion} />;
  return <BotCompanionCard companion={companion} />;
}

function MarketCompanionCard({ companion }: { companion: Extract<ReportCompanion, { type: 'market' }> }) {
  const { appearance } = useAppPreferences();
  const colors = preferenceColors(appearance);

  return (
    <View style={{ 
      paddingVertical: theme.spacing.md,
      borderTopWidth: 0.5,
      borderColor: colors.border,
      marginTop: theme.spacing.md,
    }}>
      <Text style={[styles.companionTitle, { color: colors.text }]}>Marktanalyse</Text>

      <View style={styles.marketBlock}>
        <Text style={{ fontSize: 11, color: colors.textDim, fontWeight: '700', letterSpacing: 0.5 }}>BITCOIN PRIJS</Text>
        <View style={styles.marketPriceRow}>
          <Text style={{ fontSize: 20, color: colors.text, fontWeight: '700' }}>{formatCurrency(companion.price)}</Text>
          <Text style={[styles.marketChange, { color: companion.change >= 0 ? theme.colors.success : theme.colors.danger }]}>
            {formatSignedPercent(companion.change)}
          </Text>
        </View>
      </View>

      <View style={styles.marketBlock}>
        <Text style={{ fontSize: 11, color: colors.textDim, fontWeight: '700', letterSpacing: 0.5 }}>TOTAAL VOLUME</Text>
        <Text style={{ fontSize: 18, color: colors.text, fontWeight: '700' }}>{formatFullNumber(companion.volume)}</Text>
      </View>

      <View style={[styles.companionScoreGrid, { borderTopColor: colors.border }]}>
        {companion.scores.map((score, index) => (
          <View key={`${score.label}-${index}`} style={{ flex: 1, minWidth: '45%', gap: 2 }}>
            <Text style={{ fontSize: 10, color: colors.textDim, fontWeight: '700', letterSpacing: 0.5 }}>{score.label.toUpperCase()}</Text>
            <Text style={{ fontSize: 14, color: colorForTone(score.tone), fontWeight: '700' }}>{score.value}</Text>
          </View>
        ))}
      </View>
    </View>
  );
}

function IndicatorCompanionCard({ companion }: { companion: Extract<ReportCompanion, { type: 'indicators' }> }) {
  const { appearance } = useAppPreferences();
  const colors = preferenceColors(appearance);

  return (
    <View style={{ 
      paddingVertical: theme.spacing.md,
      borderTopWidth: 0.5,
      borderColor: colors.border,
      marginTop: theme.spacing.md,
    }}>
      <Text style={[styles.companionTitle, { color: colors.text }]}>{companion.title}</Text>
      <View style={styles.indicatorList}>
        {companion.items.map((item, index) => (
          <View key={`${item.name}-${index}`} style={{ paddingVertical: 8, gap: 2 }}>
            <View style={styles.indicatorTop}>
              <Text style={[styles.indicatorName, { color: colors.text }]}>{item.name}</Text>
              {item.score === null ? null : <Text style={[styles.indicatorScore, { color: colorForTone(item.tone) }]}>{item.score}</Text>}
            </View>
            <Text style={[styles.indicatorText, { color: colors.textMuted }]}>{item.interpretation}</Text>
          </View>
        ))}
      </View>
    </View>
  );
}

function SetupCompanionCard({ companion }: { companion: Extract<ReportCompanion, { type: 'setup' }> }) {
  const { appearance } = useAppPreferences();
  const colors = preferenceColors(appearance);

  return (
    <View style={{ 
      paddingVertical: theme.spacing.md,
      borderTopWidth: 0.5,
      borderColor: colors.border,
      marginTop: theme.spacing.md,
    }}>
      <Text style={[styles.companionTitle, { color: colors.text }]}>Optimale Setup</Text>
      
      <View style={{ paddingVertical: 8, gap: 2 }}>
        <Text style={{ fontSize: 11, color: colors.textDim, fontWeight: '700', letterSpacing: 0.5 }}>BESTE MATCH</Text>
        <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}>
          <Text style={{ fontSize: 20, color: colors.text, fontWeight: '700' }}>{companion.name}</Text>
          <StatusChip label={`${Math.round(companion.score)}%`} tone={toneForScore(companion.score)} />
        </View>
        <Text style={{ fontSize: 13, color: colors.textDim }}>{companion.symbol} · {companion.timeframe}</Text>
      </View>

      {companion.topSetups.length > 0 ? (
        <View style={[styles.companionList, { borderTopColor: colors.border }]}>
          {companion.topSetups.slice(0, 3).map((setup) => (
            <View key={setup.id} style={styles.companionListRow}>
              <Text style={[styles.companionListName, { color: colors.textMuted }]}>{setup.name}</Text>
              <Text style={[styles.companionListValue, { color: colors.text }]}>{Math.round(setup.score)}%</Text>
            </View>
          ))}
        </View>
      ) : null}

      <Text style={[styles.companionNote, { color: colors.textMuted }]}>
        Geselecteerd op basis van huidige macro-, markt- en setupcondities.
      </Text>
    </View>
  );
}

function StrategyCompanionCard({ companion }: { companion: Extract<ReportCompanion, { type: 'strategy' }> }) {
  const { appearance } = useAppPreferences();
  const colors = preferenceColors(appearance);

  return (
    <View style={{ 
      paddingVertical: theme.spacing.md,
      borderTopWidth: 0.5,
      borderColor: colors.border,
      marginTop: theme.spacing.md,
    }}>
      <Text style={[styles.companionTitle, { color: colors.text }]}>Actieve Strategie</Text>
      <Text style={[styles.companionPrimary, { color: colors.text }]}>{companion.name}</Text>
      <Text style={[styles.companionSub, { color: colors.textDim }]}>{companion.symbol} · {companion.timeframe}</Text>

      <View style={{ paddingVertical: 8, gap: 2 }}>
        <Text style={{ fontSize: 11, color: colors.textDim, fontWeight: '700', letterSpacing: 0.5 }}>{companion.entry === null ? 'REFERENTIEPRIJS' : 'INSTAPPRIJS'}</Text>
        <Text style={{ fontSize: 18, color: colors.text, fontWeight: '700' }}>{formatCurrency(companion.entry ?? 0)}</Text>
      </View>

      {companion.targets.length > 0 ? (
        <View style={{ flexDirection: 'row', gap: 4, flexWrap: 'wrap', marginTop: 4 }}>
          {companion.targets.slice(0, 4).map((target, index) => (
            <View key={`${target}-${index}`} style={{ paddingVertical: 2, paddingHorizontal: 6, borderRadius: theme.radius.pill, borderWidth: 0.5, borderColor: colors.border }}>
              <Text style={{ fontSize: 11, color: colors.textMuted }}>{target}</Text>
            </View>
          ))}
        </View>
      ) : null}

      <View style={[styles.companionSplit, { borderTopColor: colors.border, marginTop: 12 }]}>
        <View>
          <Text style={{ fontSize: 11, color: colors.textDim, fontWeight: '700', letterSpacing: 0.5 }}>STOP-LOSS</Text>
          <Text style={{ fontSize: 14, color: colors.text, fontWeight: '700' }}>{formatCurrency(companion.stopLoss ?? 0)}</Text>
        </View>
        <View style={styles.alignRight}>
          <Text style={{ fontSize: 11, color: colors.textDim, fontWeight: '700', letterSpacing: 0.5 }}>VERTROUWEN</Text>
          <Text style={{ fontSize: 14, color: colorForTone(toneForScore(companion.confidence ?? 0)), fontWeight: '700' }}>{companion.confidence === null ? '-' : `${Math.round(companion.confidence)}%`}</Text>
        </View>
      </View>
    </View>
  );
}

function BotCompanionCard({ companion }: { companion: Extract<ReportCompanion, { type: 'bot' }> }) {
  const { appearance } = useAppPreferences();
  const colors = preferenceColors(appearance);
  const actionTone = companion.action === 'buy' ? 'success' : companion.action === 'sell' ? 'danger' : 'neutral';

  return (
    <View style={{ 
      paddingVertical: theme.spacing.md,
      borderTopWidth: 0.5,
      borderColor: colors.border,
      marginTop: theme.spacing.md,
    }}>
      <Text style={[styles.companionTitle, { color: colors.text }]}>Handelsactie</Text>
      <Text style={[styles.companionPrimary, { color: colors.text }]}>{companion.botName}</Text>

      <View style={{ flexDirection: 'row', justifyContent: 'space-between', paddingVertical: 8 }}>
        <View>
          <Text style={{ fontSize: 10, color: colors.textDim, fontWeight: '700', letterSpacing: 0.5 }}>ACTIE</Text>
          <Text style={{ fontSize: 18, color: colorForTone(actionTone), fontWeight: '700' }}>{companion.action.toUpperCase()}</Text>
        </View>
        <View style={styles.alignRight}>
          <Text style={{ fontSize: 10, color: colors.textDim, fontWeight: '700', letterSpacing: 0.5 }}>VERTROUWEN</Text>
          <Text style={{ fontSize: 18, color: colorForTone(toneForScore(companion.confidence ?? 0)), fontWeight: '700' }}>{companion.confidence === null ? '-' : `${Math.round(companion.confidence)}%`}</Text>
        </View>
      </View>

      <View style={[styles.companionSplit, { borderTopColor: colors.border }]}>
        <View>
          <Text style={{ fontSize: 10, color: colors.textDim, fontWeight: '700', letterSpacing: 0.5 }}>ORDERGROOTTE</Text>
          <Text style={{ fontSize: 14, color: colors.text, fontWeight: '700' }}>{companion.amount === null ? '-' : `EUR ${formatCompactNumber(companion.amount)}`}</Text>
        </View>
        <View style={styles.alignRight}>
          <Text style={{ fontSize: 10, color: colors.textDim, fontWeight: '700', letterSpacing: 0.5 }}>SETUP MATCH</Text>
          <Text style={{ fontSize: 14, color: colorForTone(toneForScore(companion.setupMatch ?? 0)), fontWeight: '700' }}>{companion.setupMatch === null ? '-' : `${Math.round(companion.setupMatch)}%`}</Text>
        </View>
      </View>

      <Text style={[styles.companionNote, { color: colors.textMuted }]}>{companion.reason}</Text>
    </View>
  );
}

function mapMobileReport(
  report: MobileReportResponse | undefined,
  period: ReportPeriod,
  language: AppLanguage,
  fullReport?: ReportResponse,
): MappedReport {
  let hydratedReport: MobileReportResponse | undefined;
  if (report && report._status !== 'pending') {
    hydratedReport = report;
  } else if (fullReport && hasUsableFullReport(fullReport)) {
    hydratedReport = buildMobileReportFromFullReport(fullReport);
  }

  if (!hydratedReport) return unavailableReport(period, language);

  const summary = normalizeReportText(String(hydratedReport.executive_summary_compact || ''));
  const marketAnalysis = normalizeReportText(String(hydratedReport.market_analysis_compact || ''));
  const outlook = normalizeReportText(String(hydratedReport.outlook_compact || ''));
  const scores = scoresFromKpis(hydratedReport.kpi_metrics);
  const avgScore = scores.reduce((total, item) => total + item.value, 0) / Math.max(1, scores.length);
  const headline = headlineFromReport(summary, avgScore);
  const highlights = normalizeHighlights(hydratedReport.highlights);
  const fullSections = fullReportSections(fullReport, hydratedReport);

  return {
    conclusionTitle: conclusionTitle(avgScore),
    dateLabel: hydratedReport.report_date || dateRange(hydratedReport.period_start, hydratedReport.period_end) || 'Recent',
    fullSections,
    generatedLabel: timeLabel(hydratedReport.generated_at),
    headline,
    highlights,
    isUnavailable: false,
    marketAnalysis,
    overallTone: toneForScore(avgScore),
    outlook,
    periodLabel: periodLabel(period, language),
    readingMinutes: readingMinutes(fullSections),
    scores,
    summary: summary || '',
    updatedAt: timeLabel(hydratedReport.generated_at),
  };
}

function hasUsableFullReport(fullReport: ReportResponse | undefined) {
  if (!fullReport) return false;
  return Boolean(
    readReportText(fullReport, [
      'executive_summary',
      'summary',
      'market_analysis',
      'market_overview',
      'outlook',
      'strategic_lessons',
      'macro_context',
      'macro_trends',
      'technical_analysis',
      'technical_structure',
    ]) || readReportNumber(fullReport, ['macro_score', 'technical_score', 'market_score', 'setup_score']),
  );
}

function buildMobileReportFromFullReport(fullReport: ReportResponse): MobileReportResponse {
  const highlights = [
    ...reportHighlightsFromField(fullReport, 'market_indicator_highlights', 'market'),
    ...reportHighlightsFromField(fullReport, 'macro_indicator_highlights', 'macro'),
    ...reportHighlightsFromField(fullReport, 'technical_indicator_highlights', 'technical'),
  ];

  return {
    active_strategy: fullReport.active_strategy,
    best_setup: fullReport.best_setup,
    bot_snapshot: fullReport.bot_snapshot,
    executive_summary_compact: normalizeReportText(
      readReportText(fullReport, ['executive_summary', 'summary']),
    ),
    generated_at:
      readStringField(fullReport, ['generated_at', 'created_at']) || null,
    highlights,
    kpi_metrics: {
      change_24h: readReportNumber(fullReport, ['change_24h', 'price_change_24h']) ?? 0,
      macro_score: readReportNumber(fullReport, ['macro_score']) ?? 0,
      market_score: readReportNumber(fullReport, ['market_score']) ?? 0,
      price: readReportNumber(fullReport, ['price', 'bitcoin_price']) ?? 0,
      setup_score: readReportNumber(fullReport, ['setup_score']) ?? 0,
      technical_score: readReportNumber(fullReport, ['technical_score']) ?? 0,
      volume: readReportNumber(fullReport, ['volume', 'total_volume']) ?? 0,
    },
    market_analysis_compact: normalizeReportText(
      readReportText(fullReport, ['market_analysis', 'market_overview']),
    ),
    outlook_compact: normalizeReportText(
      readReportText(fullReport, ['outlook', 'strategic_lessons']),
    ),
    period_end: readStringField(fullReport, ['period_end']) || null,
    period_start: readStringField(fullReport, ['period_start']) || null,
    report_date: readStringField(fullReport, ['report_date']) || null,
    top_setups: readArray(fullReport.top_setups),
    watchlist: readArray(fullReport.watchlist),
  };
}

function reportHighlightsFromField(
  fullReport: ReportResponse,
  field: string,
  fallbackCategory: string,
): MobileReportHighlight[] {
  return readArray(fullReport[field])
    .flatMap((item) => {
      const record = readRecord(item);
      if (!record) return [];
      const rawValue = readField(record, ['value', 'reading', 'current']);
      const value =
        typeof rawValue === 'string' || typeof rawValue === 'number' || rawValue === null
          ? rawValue
          : undefined;
      return {
        category: readStringField(record, ['category']) || fallbackCategory,
        interpretation:
          readStringField(record, ['interpretation', 'explanation', 'uitleg', 'advies']) || null,
        name: readStringField(record, ['name', 'indicator']) || null,
        score: readNumericField(record, ['score']),
        value,
      } satisfies MobileReportHighlight;
    })
}

function unavailableReport(period: ReportPeriod, language: AppLanguage): MappedReport {
  return {
    conclusionTitle: translate(language, 'report.unavailableHeadline'),
    dateLabel: '-',
    fullSections: [],
    generatedLabel: '-',
    headline: translate(language, 'report.unavailableHeadline'),
    highlights: [],
    isUnavailable: true,
    marketAnalysis: '',
    overallTone: 'neutral',
    outlook: '',
    periodLabel: periodLabel(period, language),
    readingMinutes: 0,
    scores: [],
    summary: translate(language, 'report.unavailableBody'),
    updatedAt: '-',
  };
}

function scoresFromKpis(kpis?: Record<string, unknown> | null) {
  if (!kpis) return [];
  const items = [
    ['Macro', readNumber(kpis, 'macro_score')],
    ['Technical', readNumber(kpis, 'technical_score')],
    ['Market', readNumber(kpis, 'market_score')],
    ['Setup', readNumber(kpis, 'setup_score')],
  ].filter((item): item is [string, number] => typeof item[1] === 'number' && Number.isFinite(item[1]));

  return items.map(([label, value]) => ({
    label,
    tone: toneForScore(value),
    value,
  }));
}

function normalizeHighlights(highlights?: MobileReportHighlight[]) {
  const normalized = (highlights ?? [])
    .filter((item) => item.name || item.interpretation)
    .slice(0, 5)
    .map((item) => {
      const score = item.score === null || item.score === undefined ? null : Number(item.score);
      return {
        category: String(item.category || 'report'),
        interpretation: normalizeReportText(String(item.interpretation || 'Geen interpretatie beschikbaar.')),
        name: String(item.name || 'Indicator'),
        score: Number.isFinite(score) ? score : null,
        tone: score === null || !Number.isFinite(score) ? 'neutral' as StatusTone : toneForScore(score),
      };
    });

  return normalized;
}

function fullReportSections(fullReport: ReportResponse | undefined, mobileReport: MobileReportResponse) {
  const scores = scoresFromKpis(mobileReport.kpi_metrics);
  const sections = [
    {
      companions: [marketCompanion(fullReport, mobileReport, scores)].filter(Boolean) as ReportCompanion[],
      label: 'Overview',
      source: readReportText(fullReport, ['executive_summary', 'summary']) || String(mobileReport.executive_summary_compact || ''),
      title: 'Dagoverzicht',
      tone: 'accent' as StatusTone,
    },
    {
      companions: [indicatorCompanion(fullReport, mobileReport, 'market_indicator_highlights', 'Market Indicator Highlights', 'market')].filter(Boolean) as ReportCompanion[],
      label: 'Market analyse',
      source:
        readReportText(fullReport, ['market_analysis', 'market_overview']) ||
        String(mobileReport.market_analysis_compact || ''),
      title: 'Marktbeeld',
      tone: 'warning' as StatusTone,
    },
    {
      companions: [indicatorCompanion(fullReport, mobileReport, 'technical_indicator_highlights', 'Technical Indicator Highlights', 'technical')].filter(Boolean) as ReportCompanion[],
      label: 'Technical',
      source: readReportText(fullReport, ['technical_analysis', 'technical_structure']),
      title: 'Technische analyse',
      tone: 'danger' as StatusTone,
    },
    {
      companions: [indicatorCompanion(fullReport, mobileReport, 'macro_indicator_highlights', 'Macro Indicator Highlights', 'macro')].filter(Boolean) as ReportCompanion[],
      label: 'Macro',
      source: readReportText(fullReport, ['macro_context', 'macro_trends']),
      title: 'Macro context',
      tone: 'neutral' as StatusTone,
    },
    {
      companions: [setupCompanion(fullReport, mobileReport)].filter(Boolean) as ReportCompanion[],
      label: 'Setup',
      source: readReportText(fullReport, ['setup_validation', 'setup_performance']),
      title: 'Setup validatie',
      tone: 'success' as StatusTone,
    },
    {
      companions: [strategyCompanion(fullReport, mobileReport)].filter(Boolean) as ReportCompanion[],
      label: 'Strategy',
      source: readReportText(fullReport, ['strategy_implication']),
      title: 'Strategische implicatie',
      tone: 'accent' as StatusTone,
    },
    {
      companions: [botCompanion(fullReport, mobileReport)].filter(Boolean) as ReportCompanion[],
      label: 'Bot',
      source: readReportText(fullReport, ['bot_strategy', 'bot_performance']),
      title: 'Bot strategie',
      tone: 'neutral' as StatusTone,
    },
    {
      label: 'Outlook',
      source:
        readReportText(fullReport, ['outlook', 'strategic_lessons']) ||
        String(mobileReport.outlook_compact || ''),
      title: 'Vooruitblik',
      tone: 'warning' as StatusTone,
    },
  ];

  return sections
    .map((section) => ({
      companions: section.companions,
      label: section.label,
      paragraphs: splitReportParagraphs(section.source),
      title: section.title,
      tone: section.tone,
    }))
    .filter((section) => section.paragraphs.length > 0);
}

function marketCompanion(
  fullReport: ReportResponse | undefined,
  mobileReport: MobileReportResponse,
  scores: Array<{ label: string; value: number; tone: StatusTone }>,
): ReportCompanion {
  return {
    change: readReportNumber(fullReport, ['change_24h', 'price_change_24h']) ?? readNumber(mobileReport.kpi_metrics, 'change_24h'),
    price: readReportNumber(fullReport, ['price', 'bitcoin_price']) ?? readNumber(mobileReport.kpi_metrics, 'price'),
    scores,
    type: 'market',
    volume: readReportNumber(fullReport, ['volume', 'total_volume']) ?? readNumber(mobileReport.kpi_metrics, 'volume'),
  };
}

function indicatorCompanion(
  fullReport: ReportResponse | undefined,
  mobileReport: MobileReportResponse,
  field: string,
  title: string,
  fallbackCategory: string,
): ReportCompanion | undefined {
  const sourceItems = readArray(fullReport?.[field]);
  const fallbackItems = (mobileReport.highlights ?? []).filter((item) =>
    String(item.category || '').toLowerCase().includes(fallbackCategory),
  );
  const items = (sourceItems.length > 0 ? sourceItems : fallbackItems)
    .map((item) => {
      const record = readRecord(item);
      if (!record) return undefined;
      const score = readNumericField(record, ['score']);
      const name = readStringField(record, ['name', 'indicator']) || 'Indicator';
      const interpretation =
        readStringField(record, ['interpretation', 'explanation', 'uitleg', 'advies']) ||
        'Geen interpretatie beschikbaar.';
      return {
        interpretation: normalizeReportText(interpretation),
        name,
        score,
        tone: score === null ? 'neutral' as StatusTone : toneForScore(score),
      };
    })
    .filter((item): item is Extract<ReportCompanion, { type: 'indicators' }>['items'][number] => Boolean(item))
    .slice(0, 3);

  if (items.length === 0) return undefined;
  return { items, title, type: 'indicators' };
}

function setupCompanion(fullReport: ReportResponse | undefined, mobileReport: MobileReportResponse): ReportCompanion | undefined {
  const bestSetup = readRecord(fullReport?.best_setup ?? mobileReport.best_setup);
  if (!bestSetup) return undefined;

  const topSetups = readArray(fullReport?.top_setups ?? mobileReport.top_setups)
    .map((item, index) => {
      const setup = readRecord(item);
      if (!setup) return undefined;
      return {
        id: String(readField(setup, ['id', 'setup_id']) ?? index),
        name: readStringField(setup, ['name', 'setup_name']) || 'Setup',
        score: readNumericField(setup, ['score', 'match_score']) ?? 0,
      };
    })
    .filter((item): item is { id: string; name: string; score: number } => Boolean(item));

  return {
    matchLabel: 'Beste match',
    name: readStringField(bestSetup, ['name', 'setup_name']) || 'Setup',
    score: readNumericField(bestSetup, ['score', 'match_score']) ?? 0,
    symbol: readStringField(bestSetup, ['symbol', 'asset']) || '',
    timeframe: readStringField(bestSetup, ['timeframe', 'frequency']) || '',
    topSetups,
    type: 'setup',
  };
}

function strategyCompanion(fullReport: ReportResponse | undefined, mobileReport: MobileReportResponse): ReportCompanion | undefined {
  const strategy = readRecord(fullReport?.active_strategy ?? mobileReport.active_strategy);
  if (!strategy) return undefined;

  return {
    confidence: readNumericField(strategy, ['confidence_score', 'confidence']),
    entry: readNumericField(strategy, ['entry', 'entry_price']),
    name: readStringField(strategy, ['setup_name', 'name', 'strategy']) || 'Actieve strategie',
    stopLoss: readNumericField(strategy, ['stop_loss', 'stop']),
    symbol: readStringField(strategy, ['symbol', 'asset']) || '',
    targets: normalizeTargets(readField(strategy, ['targets', 'target_prices'])),
    timeframe: readStringField(strategy, ['timeframe', 'frequency']) || '',
    type: 'strategy',
  };
}

function botCompanion(fullReport: ReportResponse | undefined, mobileReport: MobileReportResponse): ReportCompanion | undefined {
  const snapshot = readRecord(fullReport?.bot_snapshot ?? mobileReport.bot_snapshot);
  if (!snapshot) return undefined;

  return {
    action: (readStringField(snapshot, ['action', 'decision']) || 'hold').toLowerCase(),
    amount: readNumericField(snapshot, ['amount_eur', 'amount', 'order_size']),
    botName: readStringField(snapshot, ['bot_name', 'name']) || 'Handelsbot',
    confidence: readNumericField(snapshot, ['confidence', 'confidence_score']),
    reason: readStringField(snapshot, ['reason', 'explanation']) || 'Geen actie: criteria niet bereikt.',
    setupMatch: readNumericField(snapshot, ['setup_match', 'match_score']),
    type: 'bot',
  };
}

function readingMinutes(sections: MappedReport['fullSections']) {
  const words = sections
    .flatMap((section) => section.paragraphs)
    .join(' ')
    .split(/\s+/)
    .filter(Boolean).length;

  if (words === 0) return 0;
  return Math.ceil(words / 180);
}

function mapFinnReflectionEnvelope(envelope: {
  analysis?: Record<string, unknown> | null;
  next_best_action?: string | null;
  response?: string;
  risk_summary?: string | null;
  summary?: string | null;
}) {
  const body = normalizeReportText(String(envelope.response || envelope.summary || 'No Finn reflection available.'));
  const headline = compactText(
    firstSentence(body) || String(envelope.summary || envelope.risk_summary || envelope.next_best_action || 'Finn reflection'),
    88,
  );

  return {
    analysis:
      readRecord((envelope as Record<string, unknown>)?.analysis) ??
      readRecord(readField(readRecord((envelope as Record<string, unknown>)?.state), ['analysis'])) ??
      readRecord((envelope as Record<string, unknown>)?.state),
    body,
    headline,
    next: envelope.next_best_action || null,
    risk: envelope.risk_summary || null,
    summary: envelope.summary || null,
  } satisfies FinnReflectionResponse;
}

function buildFinnReflectionPresentation(reflection: FinnReflectionResponse) {
  const analysis = readRecord(reflection.analysis);
  const sections = readRecord(readField(analysis, ['sections']));
  const dayClose = readRecord(readField(analysis, ['day_close']));
  const activityBlock =
    readRecord(readField(dayClose, ['what_i_did_today'])) ?? readRecord(readField(sections, ['activity_journal']));
  const blockedBlock =
    readRecord(readField(dayClose, ['what_finn_blocked'])) ?? readRecord(readField(sections, ['blocked_summary']));
  const deviationBlock =
    readRecord(readField(dayClose, ['where_i_deviated'])) ?? readRecord(readField(sections, ['plan_adherence']));
  const activityEntries = readArray(readField(activityBlock, ['entries']));
  const blockedEntries = readArray(readField(blockedBlock, ['entries']));
  const deviationEntries = readArray(readField(deviationBlock, ['entries']));
  const reviewed = activityEntries.length;
  const blocked = blockedEntries.length;
  const open = activityEntries.filter((entry) => {
    const record = readRecord(entry);
    const haystack = [
      readStringField(record, ['status', 'resolve_state', 'label', 'type']),
      readStringField(record, ['message', 'outcome']),
    ]
      .filter(Boolean)
      .join(' ')
      .toLowerCase();
    return ['pending', 'open', 'later', 'snooz', 'waiting', 'needs review', 'needs input'].some((pattern) =>
      haystack.includes(pattern),
    );
  }).length;
  const riskBody =
    reflection.risk ||
    readStringField(blockedBlock, ['summary', 'headline']) ||
    readStringField(deviationBlock, ['summary', 'headline']) ||
    'Keep logging decisions clearly so Finn can judge patterns with more confidence.';
  const nextBody =
    reflection.next ||
    readStringField(dayClose, ['coach_message', 'next_best_action']) ||
    'Keep decisions explicit and let the next few actions build a clearer reflection.';
  const summaryBody =
    reflection.summary ||
    readStringField(activityBlock, ['summary', 'headline']) ||
    'The available evidence is still too limited for a stronger positive conclusion.';
  const headline =
    reflection.headline ||
    readStringField(dayClose, ['headline']) ||
    'There is not enough real activity yet for a firm reflection.';
  const evidenceTarget = 3;
  const evidenceCount = reviewed + blocked + open;
  const evidenceProgress = Math.max(0, Math.min(100, (evidenceCount / evidenceTarget) * 100));
  const hasLimitedEvidence = evidenceCount < evidenceTarget;
  const eventsCount = activityEntries.length + blockedEntries.length + deviationEntries.length;
  const support = hasLimitedEvidence
    ? 'FINN needs a few explicit decisions before it can identify a meaningful pattern.'
    : 'FINN reviews how closely you followed your plan and what to improve next.';
  const aside = hasLimitedEvidence
    ? 'FINN will show patterns here once enough existing activity and reviews have been recorded.'
    : 'FINN is now seeing enough evidence to surface repeatable patterns and coaching signals.';

  return {
    aside,
    evidenceCount,
    evidenceProgress,
    evidenceTarget,
    eventsCount,
    hasLimitedEvidence,
    headline,
    insights: [
      {
        background: '#ECFDF5',
        body: summaryBody,
        border: '#A7F3D0',
        color: '#166534',
        label: 'WHAT WENT WELL',
      },
      {
        background: '#FFFBEB',
        body: riskBody,
        border: '#FCD34D',
        color: '#9A3412',
        label: 'WHAT NEEDS ATTENTION',
      },
      {
        background: '#EFF6FF',
        body: nextBody,
        border: '#BFDBFE',
        color: '#1D4ED8',
        label: 'NEXT STEP',
      },
    ],
    metrics: [
      { icon: 'file-text' as const, label: 'Reviewed', value: String(reviewed) },
      { icon: 'shield' as const, label: 'Blocked', value: String(blocked) },
      { icon: 'activity' as const, label: 'Open', value: String(open) },
    ],
    support,
  };
}

function readRecord(value: unknown): Record<string, unknown> | undefined {
  if (!value) return undefined;
  if (Array.isArray(value)) return readRecord(value[0]);
  if (typeof value === 'string') {
    try {
      return readRecord(JSON.parse(value));
    } catch {
      return undefined;
    }
  }
  if (typeof value === 'object') return value as Record<string, unknown>;
  return undefined;
}

function readArray(value: unknown): unknown[] {
  if (!value) return [];
  if (Array.isArray(value)) return value;
  if (typeof value === 'string') {
    try {
      const parsed = JSON.parse(value);
      return Array.isArray(parsed) ? parsed : [];
    } catch {
      return [];
    }
  }
  return [];
}

function readField(source: Record<string, unknown> | undefined, keys: string[]) {
  for (const key of keys) {
    const value = source?.[key];
    if (value !== undefined && value !== null) return value;
  }
  return undefined;
}

function readStringField(source: Record<string, unknown> | undefined, keys: string[]) {
  const value = readField(source, keys);
  if (typeof value === 'string' && value.trim()) return value.trim();
  if (typeof value === 'number' && Number.isFinite(value)) return String(value);
  return '';
}

function readNumericField(source: Record<string, unknown> | undefined, keys: string[]) {
  const value = readField(source, keys);
  if (typeof value === 'number' && Number.isFinite(value)) return value;
  if (typeof value === 'string' && Number.isFinite(Number(value))) return Number(value);
  return null;
}

function normalizeTargets(value: unknown) {
  if (Array.isArray(value)) return value.map((target) => String(target).trim()).filter(Boolean);
  if (typeof value === 'string') {
    return value
      .split(',')
      .map((target) => target.trim())
      .filter(Boolean);
  }
  return [];
}

function readReportText(source: ReportResponse | undefined, keys: string[]) {
  for (const key of keys) {
    const value = source?.[key];
    if (typeof value === 'string' && value.trim()) return value;
  }
  return '';
}

function readReportNumber(source: ReportResponse | undefined, keys: string[]) {
  for (const key of keys) {
    const value = source?.[key];
    if (typeof value === 'number' && Number.isFinite(value)) return value;
    if (typeof value === 'string' && Number.isFinite(Number(value))) return Number(value);
  }
  return undefined;
}

function splitReportParagraphs(value: string) {
  const clean = normalizeReportText(value);
  if (!clean) return [];

  const explicitParagraphs = clean
    .split(/\n{2,}/)
    .map((paragraph) => paragraph.trim())
    .filter(Boolean);

  if (explicitParagraphs.length > 1) return explicitParagraphs;

  const sentences = clean.match(/[^.!?]+[.!?]+(?:\s|$)|[^.!?]+$/g)?.map((sentence) => sentence.trim()) ?? [clean];
  const paragraphs: string[] = [];

  for (let index = 0; index < sentences.length; index += 3) {
    paragraphs.push(sentences.slice(index, index + 3).join(' '));
  }

  return paragraphs.filter(Boolean);
}

function normalizeReportText(value: string) {
  return value
    .replace(/\*\*/g, '')
    .replace(/\r/g, '')
    .replace(/[ \t]+\n/g, '\n')
    .replace(/\n{3,}/g, '\n\n')
    .trim();
}

function firstSentence(value: string) {
  const clean = normalizeReportText(value);
  const sentence = clean.match(/[^.!?]+[.!?]+|[^.!?]+$/)?.[0]?.trim() || '';
  return sentence;
}

function headlineFromReport(summary: string, avgScore: number) {
  if (avgScore >= 70) return 'Risk-on, selective';
  if (avgScore >= 55) return 'Constructive, wait confirmation';
  if (avgScore < 40) return 'Defensive posture';
  if (summary.toLowerCase().includes('bull-trap')) return 'Bull-trap risk elevated';
  return 'Neutral, monitor risk';
}

function conclusionTitle(avgScore: number) {
  if (avgScore >= 70) return 'Rapport ondersteunt selectieve actie';
  if (avgScore >= 55) return 'Context is bruikbaar, maar niet agressief';
  if (avgScore < 40) return 'Risico eerst beoordelen';
  return 'Wachten blijft verdedigbaar';
}

function buildReflectionOverviewCards(report: MappedReport) {
  if (report.highlights.length === 0) return [];
  const warningHighlight = report.highlights.find((item) => item.tone === 'danger' || item.tone === 'warning') ?? report.highlights[0];

  return [
    {
      bg: '#EEF4FF',
      body: compactText(report.summary || report.headline, 52),
      border: '#D7E5FF',
      color: theme.colors.accent,
      foot: report.highlights.length > 0 ? `${report.highlights.length} beslissingen bekeken` : 'Dagbeeld',
      icon: 'file-text' as const,
      label: 'RESULTAAT',
      title: compactText(report.conclusionTitle || 'Plan grotendeels gevolgd', 30),
    },
    {
      bg: '#FFF7E8',
      body: compactText(
        warningHighlight?.interpretation || report.marketAnalysis || 'Een moment vroeg om extra bevestiging.',
        52,
      ),
      border: '#F8D9A6',
      color: theme.colors.warning,
      foot: warningHighlight ? 'Aandacht' : 'Controle',
      icon: 'check-circle' as const,
      label: 'BEOORDELING',
      title: compactText(formatDecisionMomentTitle(warningHighlight?.name || 'Bevestiging vroeg aangenomen'), 30),
    },
    {
      bg: '#EAF8F1',
      body: compactText(report.outlook || 'Leg vast wat je de volgende keer anders doet.', 52),
      border: '#C9ECD8',
      color: theme.colors.success,
      foot: 'Volgende trade',
      icon: 'arrow-up-right' as const,
      label: 'VERBETERING',
      title: report.outlook ? compactText(report.outlook, 30) : 'Wacht op candle close',
    },
  ];
}

function buildDecisionMoments(report: MappedReport) {
  const source = report.highlights.length > 0 ? report.highlights.slice(0, 3) : report.fullSections.slice(0, 3).map((section) => ({
    category: section.label,
    interpretation: section.paragraphs[0] || '',
    name: section.title,
    score: null,
    tone: section.tone,
  }));

  return source.map((item, index) => ({
    color: colorForTone(item.tone),
    note:
      item.tone === 'danger'
        ? 'review voltooid'
        : item.tone === 'warning'
          ? 'controle nodig'
          : 'risicolimiet gevolgd',
    tag:
      item.tone === 'danger'
        ? 'Afwijking'
        : item.tone === 'warning'
        ? 'Aandacht'
        : 'Goed',
    time: '—',
    title: formatDecisionMomentTitle(item.name),
  }));
}

function formatDecisionMomentTitle(value: string) {
  const clean = value.replace(/_/g, ' ').trim();
  const knownMap: Record<string, string> = {
    'change 24h': 'BTC bevestiging te vroeg',
    volume: 'Geen extra positie toegevoegd',
    'fear greed index': 'Marktsentiment te zwak',
  };
  const mapped = knownMap[clean.toLowerCase()];
  if (mapped) return mapped;
  return compactText(clean.charAt(0).toUpperCase() + clean.slice(1), 30);
}

function reflectionReportTitle(periodLabel: string) {
  const clean = periodLabel.toLowerCase();
  if (clean.includes('week')) return 'Weekly Report';
  if (clean.includes('maand') || clean.includes('month')) return 'Monthly Report';
  if (clean.includes('kwart') || clean.includes('quarter')) return 'Quarterly Report';
  return 'Daily Report';
}

function iconForScoreLabel(label: string): keyof typeof Feather.glyphMap {
  const clean = label.toLowerCase();
  if (clean.includes('macro')) return 'globe';
  if (clean.includes('technical')) return 'activity';
  if (clean.includes('market')) return 'bar-chart-2';
  if (clean.includes('setup')) return 'target';
  return 'circle';
}

function iconForReflectionSection(title: string): keyof typeof Feather.glyphMap {
  const clean = title.toLowerCase();
  if (clean.includes('market')) return 'globe';
  if (clean.includes('macro')) return 'bar-chart-2';
  if (clean.includes('techn')) return 'trending-up';
  if (clean.includes('setup')) return 'crosshair';
  if (clean.includes('trade')) return 'briefcase';
  if (clean.includes('risico')) return 'shield';
  if (clean.includes('conclus')) return 'flag';
  return 'file-text';
}

function periodLabel(period: ReportPeriod, language: AppLanguage) {
  if (period === 'weekly') return translate(language, 'report.period.weekly');
  if (period === 'monthly') return translate(language, 'report.period.monthly');
  if (period === 'quarterly') return translate(language, 'report.period.quarterly');
  return translate(language, 'report.period.daily');
}

function dateRange(start?: string | null, end?: string | null) {
  if (start && end) return `${start} - ${end}`;
  return start || end || '';
}

function readNumber(source: Record<string, unknown> | null | undefined, key: string) {
  const value = source?.[key];
  if (typeof value === 'number' && Number.isFinite(value)) return Math.round(value);
  if (typeof value === 'string' && Number.isFinite(Number(value))) return Math.round(Number(value));
  return 0;
}

function toneForScore(score: number): StatusTone {
  if (score >= 70) return 'success';
  if (score >= 55) return 'accent';
  if (score >= 40) return 'warning';
  return 'danger';
}

function colorForTone(tone: StatusTone) {
  if (tone === 'success') return theme.colors.success;
  if (tone === 'warning') return theme.colors.warning;
  if (tone === 'danger') return theme.colors.danger;
  if (tone === 'neutral') return theme.colors.textDim;
  return theme.colors.accent;
}

function softBackgroundForTone(tone: StatusTone) {
  if (tone === 'success') return theme.colors.successSoft;
  if (tone === 'warning') return theme.colors.warningSoft;
  if (tone === 'danger') return theme.colors.dangerSoft;
  if (tone === 'neutral') return theme.colors.surfaceMuted;
  return theme.colors.accentSoft;
}

function compactText(value: string, maxLength: number) {
  const clean = value.replace(/\s+/g, ' ').trim();
  if (clean.length <= maxLength) return clean;
  return `${clean.slice(0, maxLength - 1).trim()}...`;
}

function formatCurrency(value: number) {
  if (!Number.isFinite(value) || value <= 0) return '-';
  return `$${Intl.NumberFormat('en-US', {
    maximumFractionDigits: value >= 1000 ? 0 : 2,
    notation: value >= 1000000 ? 'compact' : 'standard',
  }).format(value)}`;
}

function formatCompactNumber(value: number) {
  if (!Number.isFinite(value) || value <= 0) return '-';
  return Intl.NumberFormat('en-US', {
    maximumFractionDigits: 1,
    notation: 'compact',
  }).format(value);
}

function formatFullNumber(value: number) {
  if (!Number.isFinite(value) || value <= 0) return '-';
  return Intl.NumberFormat('nl-NL', {
    maximumFractionDigits: 0,
  }).format(value);
}

function formatSignedPercent(value: number) {
  if (!Number.isFinite(value)) return '0.0%';
  const prefix = value > 0 ? '+' : '';
  return `${prefix}${value.toFixed(1)}%`;
}

function timeLabel(value?: string | null) {
  if (!value) return new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value.slice(0, 5);
  return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

const styles = StyleSheet.create({
  reflectionSection: {
    paddingHorizontal: 12,
    paddingVertical: 8,
  },
  reflectionHeroCard: {
    borderRadius: 16,
    borderWidth: 1,
    paddingHorizontal: theme.spacing.md,
    paddingVertical: theme.spacing.md,
  },
  reflectionHeroLabelRow: {
    alignItems: 'center',
    flexDirection: 'row',
    gap: 10,
  },
  reflectionHeroDot: {
    backgroundColor: theme.colors.accent,
    borderRadius: 999,
    height: 10,
    width: 10,
  },
  reflectionHeroLabel: {
    fontSize: 14,
    fontWeight: '700',
    lineHeight: 18,
  },
  reflectionHeroHeadline: {
    fontSize: 16,
    fontWeight: '800',
    lineHeight: 22,
    marginTop: theme.spacing.md,
  },
  reflectionHeroSupport: {
    fontSize: 14,
    fontWeight: '500',
    lineHeight: 21,
    marginTop: theme.spacing.sm,
  },
  reflectionHeroAction: {
    alignSelf: 'flex-start',
    marginTop: theme.spacing.md,
  },
  reflectionHeroActionText: {
    color: theme.colors.accent,
    fontSize: 15,
    fontWeight: '700',
    lineHeight: 20,
  },
  reflectionHeaderRow: {
    alignItems: 'flex-end',
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginTop: theme.spacing.sm,
  },
  reflectionEyebrow: {
    ...typography.eyebrow,
  },
  reflectionTitle: {
    ...typography.sectionTitle,
    marginTop: 2,
  },
  reflectionDate: {
    fontSize: 14,
    fontWeight: '500',
    lineHeight: 18,
  },
  reflectionCard: {
    borderRadius: 16,
    borderWidth: 1,
    marginTop: 8,
    overflow: 'hidden',
    paddingHorizontal: 14,
    paddingVertical: 8,
  },
  reflectionInsightRow: {
    alignItems: 'center',
    borderBottomWidth: 1,
    flexDirection: 'row',
    gap: 12,
    paddingVertical: 8,
  },
  reflectionInsightRowLast: {
    borderBottomWidth: 0,
    paddingBottom: 0,
  },
  reflectionInsightIcon: {
    alignItems: 'center',
    borderRadius: 12,
    borderWidth: 1,
    height: 46,
    justifyContent: 'center',
    width: 46,
  },
  reflectionInsightCopy: {
    flex: 1,
    minWidth: 0,
  },
  reflectionInsightLabel: {
    fontSize: 9,
    fontWeight: '900',
    letterSpacing: 1.8,
    textTransform: 'uppercase',
  },
  reflectionInsightTitle: {
    fontSize: 13,
    fontWeight: '800',
    lineHeight: 16,
    marginTop: 1,
  },
  reflectionInsightBody: {
    fontSize: 11,
    fontWeight: '500',
    lineHeight: 14,
    marginTop: 1,
  },
  reflectionInsightFoot: {
    fontSize: 11,
    fontWeight: '700',
    lineHeight: 13,
    marginTop: 2,
  },
  reflectionMomentsHeader: {
    alignItems: 'center',
    flexDirection: 'row',
    justifyContent: 'space-between',
  },
  reflectionMomentsTitle: {
    fontSize: 16,
    fontWeight: '700',
    lineHeight: 20,
  },
  reflectionMomentsCount: {
    fontSize: 13,
    fontWeight: '500',
    lineHeight: 16,
  },
  reflectionMomentRow: {
    alignItems: 'center',
    borderBottomWidth: 1,
    flexDirection: 'row',
    gap: 8,
    paddingVertical: 8,
  },
  reflectionMomentRowLast: {
    borderBottomWidth: 0,
    paddingBottom: 0,
  },
  reflectionMomentTime: {
    fontSize: 12,
    fontWeight: '500',
    lineHeight: 14,
    width: 40,
  },
  reflectionMomentCopy: {
    flex: 1,
    minWidth: 0,
  },
  reflectionMomentTitle: {
    fontSize: 12,
    fontWeight: '600',
    lineHeight: 15,
  },
  reflectionMomentMeta: {
    fontSize: 10,
    fontWeight: '500',
    lineHeight: 12,
    marginTop: 1,
  },
  reflectionReportLabel: {
    fontSize: 11,
    fontWeight: '900',
    letterSpacing: 2.2,
    textTransform: 'uppercase',
  },
  reflectionReportSub: {
    fontSize: 13,
    fontWeight: '500',
    lineHeight: 17,
    marginTop: 4,
  },
  reflectionReportOverview: {
    borderRadius: 18,
    borderWidth: 1,
    marginTop: 10,
    overflow: 'hidden',
  },
  reflectionReportOverviewHeader: {
    gap: 14,
    paddingHorizontal: 14,
    paddingVertical: 14,
  },
  reflectionFinnHeadlineCard: {
    borderBottomWidth: 1,
    paddingHorizontal: 14,
    paddingVertical: 12,
  },
  reflectionFinnHeadlineText: {
    ...typography.heroTitle,
    lineHeight: 24,
    marginTop: 4,
  },
  reflectionFinnSupportText: {
    ...typography.body,
    marginTop: 6,
  },
  reflectionFinnMetricRow: {
    flexDirection: 'row',
    gap: 12,
    paddingHorizontal: 14,
    paddingTop: 12,
  },
  reflectionFinnMetricInline: {
    alignItems: 'flex-start',
    flex: 1,
    flexDirection: 'column',
    gap: 8,
    minWidth: 0,
  },
  reflectionFinnMetricIcon: {
    alignItems: 'center',
    borderRadius: 999,
    borderWidth: 1,
    height: 40,
    justifyContent: 'center',
    width: 40,
  },
  reflectionFinnMetricCopy: {
    flex: 1,
    minWidth: 0,
    width: '100%',
  },
  reflectionFinnMetricInlineLabel: {
    ...typography.body,
    fontSize: 11,
    lineHeight: 14,
  },
  reflectionFinnMetricInlineValue: {
    fontSize: 24,
    fontWeight: '900',
    lineHeight: 28,
  },
  reflectionFinnInsightGrid: {
    gap: 12,
    marginTop: 12,
  },
  reflectionFinnInsightCard: {
    borderRadius: 16,
    borderWidth: 1,
    minWidth: 0,
    paddingHorizontal: 14,
    paddingVertical: 14,
  },
  reflectionFinnInsightLabel: {
    ...typography.metricLabelStrong,
    letterSpacing: 1.8,
  },
  reflectionFinnInsightBody: {
    fontSize: 15,
    fontWeight: '700',
    lineHeight: 24,
    marginTop: 10,
  },
  reflectionFinnProgressWrap: {
    borderTopWidth: 1,
    marginTop: 12,
    paddingHorizontal: 14,
    paddingTop: 12,
  },
  reflectionFinnProgressHeader: {
    alignItems: 'center',
    flexDirection: 'row',
    justifyContent: 'space-between',
  },
  reflectionFinnProgressLabel: {
    ...typography.body,
    fontSize: 12,
  },
  reflectionFinnProgressValue: {
    ...typography.bodyStrong,
    fontSize: 12,
  },
  reflectionFinnProgressTrack: {
    borderRadius: 999,
    height: 8,
    marginTop: 8,
    overflow: 'hidden',
  },
  reflectionFinnProgressFill: {
    borderRadius: 999,
    height: '100%',
  },
  reflectionFinnAsideCard: {
    borderRadius: 16,
    borderWidth: 1,
    marginTop: 10,
    paddingHorizontal: 14,
    paddingVertical: 12,
  },
  reflectionFinnAsideLabel: {
    ...typography.metricLabelStrong,
    letterSpacing: 1.8,
  },
  reflectionFinnAsideBody: {
    ...typography.body,
    marginTop: 6,
  },
  reflectionFinnActivityRow: {
    alignItems: 'center',
    borderRadius: 16,
    borderWidth: 1,
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginTop: 12,
    paddingHorizontal: 14,
    paddingVertical: 12,
  },
  reflectionFinnActivityLead: {
    alignItems: 'center',
    flex: 1,
    flexDirection: 'row',
    gap: 12,
    minWidth: 0,
  },
  reflectionFinnActivityIcon: {
    alignItems: 'center',
    borderRadius: 14,
    borderWidth: 1,
    height: 40,
    justifyContent: 'center',
    width: 40,
  },
  reflectionFinnActivityCopy: {
    flex: 1,
    minWidth: 0,
  },
  reflectionFinnActivityTitle: {
    ...typography.sectionTitle,
    fontSize: 16,
    lineHeight: 20,
  },
  reflectionFinnActivityBody: {
    ...typography.body,
    marginTop: 2,
  },
  reflectionFinnActivityMeta: {
    alignItems: 'center',
    flexDirection: 'row',
    gap: 8,
    marginLeft: 12,
  },
  reflectionFinnActivityCount: {
    ...typography.bodyStrong,
    fontSize: 12,
  },
  reflectionFinnExpandedCard: {
    borderRadius: 16,
    borderWidth: 1,
    marginTop: 12,
    paddingHorizontal: 14,
    paddingVertical: 14,
  },
  reflectionReportOverviewLead: {
    alignItems: 'flex-start',
    flexDirection: 'row',
    gap: 10,
  },
  reflectionReportAccentBar: {
    borderRadius: 999,
    height: 56,
    marginTop: 2,
    width: 4,
  },
  reflectionReportOverviewCopy: {
    flex: 1,
    minWidth: 0,
  },
  reflectionReportOverviewLabel: {
    ...typography.metricLabelStrong,
    letterSpacing: 1.8,
  },
  reflectionReportOverviewTitle: {
    ...typography.heroTitle,
    lineHeight: 26,
    marginTop: 6,
  },
  reflectionReportOverviewMeta: {
    alignItems: 'center',
    flexDirection: 'row',
    gap: 6,
    marginTop: 10,
  },
  reflectionReportOverviewMetaText: {
    ...typography.bodyStrong,
    lineHeight: 16,
  },
  reflectionScoreCluster: {
    borderRadius: 18,
    borderWidth: 1,
    padding: 10,
  },
  reflectionReportIntro: {
    ...typography.bodyStrong,
    lineHeight: 17,
    marginTop: 14,
  },
  reflectionReportLead: {
    ...typography.body,
    fontStyle: 'italic',
    marginTop: 4,
  },
  reflectionScoreGrid: {
    flexDirection: 'row',
    gap: 8,
  },
  reflectionScoreCell: {
    alignItems: 'center',
    borderRadius: 14,
    borderWidth: 1,
    flex: 1,
    minWidth: 0,
    paddingHorizontal: 6,
    paddingVertical: 10,
  },
  reflectionScoreIconWrap: {
    alignItems: 'center',
    borderRadius: 999,
    height: 28,
    justifyContent: 'center',
    marginBottom: 8,
    width: 28,
  },
  reflectionScoreLabel: {
    minHeight: 24,
    ...typography.chipLabelCompact,
    textAlign: 'center',
  },
  reflectionScoreValue: {
    ...typography.metricValue,
    marginTop: 2,
  },
  reflectionReportOverviewFooter: {
    alignItems: 'center',
    borderTopWidth: 1,
    flexDirection: 'row',
    justifyContent: 'space-between',
    paddingHorizontal: 14,
    paddingVertical: 10,
  },
  reflectionReportOverviewStatus: {
    alignItems: 'center',
    flexDirection: 'row',
    gap: 6,
  },
  reflectionReportOverviewStatusText: {
    ...typography.subcopy,
    fontWeight: '700',
    lineHeight: 14,
    textTransform: 'uppercase',
  },
  reflectionReportOverviewStatusMeta: {
    ...typography.subcopy,
    fontWeight: '600',
    lineHeight: 14,
  },
  reflectionReportSummary: {
    ...typography.body,
    marginTop: 14,
  },
  reflectionReportToggle: {
    alignItems: 'center',
    alignSelf: 'flex-end',
    borderRadius: 999,
    borderWidth: 1,
    flexDirection: 'row',
    gap: 8,
    marginTop: 12,
    paddingHorizontal: 12,
    paddingVertical: 8,
  },
  reflectionReportToggleText: {
    ...typography.chipLabel,
    lineHeight: 13,
  },
  reflectionReportRows: {
    marginTop: 8,
  },
  reflectionReportRow: {
    borderBottomWidth: 1,
    paddingVertical: 12,
  },
  reflectionReportRowLast: {
    borderBottomWidth: 0,
    paddingBottom: 0,
  },
  reflectionReportRowLead: {
    alignItems: 'flex-start',
    flexDirection: 'row',
    gap: 8,
  },
  reflectionReportRowCopy: {
    flex: 1,
    minWidth: 0,
  },
  reflectionReportRowMeta: {
    ...typography.chipLabel,
    lineHeight: 14,
  },
  reflectionReportExpanded: {
    gap: 10,
    marginLeft: 23,
    marginTop: 8,
  },
  reflectionReportExpandedText: {
    ...typography.body,
    lineHeight: 20,
  },
  reflectionReportCompanions: {
    marginTop: 4,
  },
  reflectionInlinePanel: {
    borderRadius: 14,
    borderWidth: 1,
    paddingHorizontal: 12,
    paddingVertical: 10,
  },
  reflectionInlinePanelHeader: {
    alignItems: 'center',
    flexDirection: 'row',
    gap: 8,
  },
  reflectionInlinePanelTitle: {
    ...typography.subcopy,
    fontWeight: '700',
    lineHeight: 15,
  },
  reflectionInlineMetricRow: {
    alignItems: 'center',
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginTop: 10,
  },
  reflectionInlineMetricBlock: {
    flex: 1,
    minWidth: 0,
  },
  reflectionInlineMetricLabel: {
    ...typography.metricLabel,
  },
  reflectionInlineMetricValue: {
    ...typography.metricValue,
    marginTop: 3,
  },
  reflectionInlineChange: {
    fontSize: 15,
    fontWeight: '800',
    lineHeight: 18,
    marginLeft: 10,
  },
  reflectionInlineVolume: {
    fontSize: 12,
    fontWeight: '500',
    lineHeight: 17,
    marginTop: 8,
  },
  reflectionInlineScoreRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
    marginTop: 10,
  },
  reflectionInlineScoreChip: {
    minWidth: 56,
  },
  reflectionInlineScoreChipLabel: {
    fontSize: 10,
    fontWeight: '700',
    lineHeight: 12,
  },
  reflectionInlineScoreChipValue: {
    fontSize: 14,
    fontWeight: '800',
    lineHeight: 16,
    marginTop: 2,
  },
  reflectionInlineIndicatorRow: {
    alignItems: 'center',
    borderBottomWidth: 1,
    borderBottomColor: theme.colors.borderSubtle,
    flexDirection: 'row',
    gap: 8,
    justifyContent: 'space-between',
    paddingVertical: 8,
  },
  reflectionInlineIndicatorRowLast: {
    borderBottomWidth: 0,
    paddingBottom: 0,
  },
  reflectionInlineIndicatorCopy: {
    flex: 1,
    minWidth: 0,
  },
  reflectionInlineIndicatorTitle: {
    fontSize: 12,
    fontWeight: '700',
    lineHeight: 15,
  },
  reflectionInlineIndicatorText: {
    fontSize: 11,
    fontWeight: '500',
    lineHeight: 14,
    marginTop: 2,
  },
  reflectionInlineIndicatorScore: {
    fontSize: 14,
    fontWeight: '800',
    lineHeight: 16,
    marginLeft: 8,
  },
  reflectionInlinePrimary: {
    fontSize: 14,
    fontWeight: '800',
    lineHeight: 18,
    marginTop: 8,
  },
  reflectionInlineSub: {
    fontSize: 12,
    fontWeight: '500',
    lineHeight: 15,
    marginTop: 2,
  },
  reflectionInlineMetricScore: {
    fontSize: 14,
    fontWeight: '800',
    lineHeight: 16,
  },
  reflectionConclusionBox: {
    borderRadius: 14,
    borderWidth: 1,
    marginTop: 10,
    paddingHorizontal: 14,
    paddingVertical: 10,
  },
  reflectionConclusionTitle: {
    fontSize: 14,
    fontWeight: '700',
    lineHeight: 18,
  },
  reflectionConclusionBody: {
    fontSize: 13,
    fontWeight: '500',
    lineHeight: 17,
    marginTop: 4,
  },
  reflectionReportFooter: {
    alignItems: 'center',
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginTop: 10,
  },
  reflectionFooterMeta: {
    fontSize: 12,
    fontWeight: '500',
    lineHeight: 15,
  },
  summaryCard: {
    borderRadius: theme.radius.md,
    borderWidth: 0.5,
    flexBasis: '47.5%',
    flexGrow: 0,
    flexShrink: 0,
    gap: 4,
    maxWidth: '47.5%',
    minHeight: 74,
    minWidth: 0,
    paddingHorizontal: 12,
    paddingVertical: 10,
  },
  summaryGrid: {
    columnGap: theme.spacing.sm,
    flexDirection: 'row',
    flexWrap: 'wrap',
    rowGap: theme.spacing.sm,
  },
  summaryGridWrap: {
    paddingHorizontal: 8,
    paddingBottom: theme.spacing.sm,
  },
  summaryCopy: {
    flex: 1,
  },
  summaryLabel: {
    fontSize: 11,
    fontWeight: '800',
    letterSpacing: 0.5,
    textTransform: 'uppercase',
  },
  summaryTop: {
    alignItems: 'flex-start',
    flexDirection: 'row',
    gap: theme.spacing.md,
    justifyContent: 'space-between',
    marginBottom: 10,
  },
  summaryValue: {
    flexShrink: 1,
    fontSize: 14,
    fontWeight: '700',
    lineHeight: 19,
  },
  reportAction: {
    alignItems: 'center',
    backgroundColor: theme.colors.accent,
    borderRadius: theme.radius.button,
    justifyContent: 'center',
    minHeight: 48,
    marginTop: theme.spacing.md,
  },
  reportActionText: {
    color: '#ffffff',
    fontSize: 11,
    fontWeight: '900',
    letterSpacing: 0.9,
    textTransform: 'uppercase',
  },
  actionPanel: {
    alignItems: 'center',
    borderRadius: theme.radius.lg,
    borderWidth: 1,
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginTop: theme.spacing.lg,
    padding: theme.spacing.md,
  },
  actionValue: {
    fontSize: 20,
    fontWeight: '900',
    letterSpacing: 0,
    marginTop: theme.spacing.xs,
  },
  alignRight: {
    alignItems: 'flex-end',
  },
  companionCard: {
    backgroundColor: theme.colors.backgroundSoft,
    borderColor: theme.colors.border,
    borderRadius: theme.radius.lg,
    borderWidth: 1,
    marginTop: theme.spacing.lg,
    padding: theme.spacing.md,
  },
  companionInner: {
    backgroundColor: theme.colors.surface,
    borderColor: theme.colors.borderSubtle,
    borderRadius: theme.radius.md,
    borderWidth: 1,
    marginTop: theme.spacing.md,
    padding: theme.spacing.md,
  },
  companionList: {
    borderTopColor: theme.colors.border,
    borderTopWidth: 1,
    gap: theme.spacing.sm,
    marginTop: theme.spacing.md,
    paddingTop: theme.spacing.md,
  },
  companionListName: {
    color: theme.colors.textMuted,
    flex: 1,
    fontSize: theme.typography.small,
    fontWeight: '800',
  },
  companionListRow: {
    alignItems: 'center',
    flexDirection: 'row',
    gap: theme.spacing.md,
    justifyContent: 'space-between',
  },
  companionListValue: {
    color: theme.colors.text,
    fontSize: theme.typography.small,
    fontWeight: '900',
  },
  companionMeta: {
    color: theme.colors.textMuted,
    fontSize: theme.typography.label,
    fontWeight: '900',
    letterSpacing: 1.2,
    textTransform: 'uppercase',
  },
  companionNote: {
    color: theme.colors.textMuted,
    fontSize: theme.typography.small,
    fontStyle: 'italic',
    fontWeight: '600',
    lineHeight: 20,
    marginTop: theme.spacing.md,
  },
  companionPrimary: {
    color: theme.colors.text,
    fontSize: 18,
    fontWeight: '900',
    letterSpacing: 0,
    lineHeight: 22,
    marginTop: theme.spacing.md,
  },
  companionRow: {
    alignItems: 'center',
    flexDirection: 'row',
    justifyContent: 'space-between',
  },
  companionSplit: {
    borderTopColor: theme.colors.border,
    borderTopWidth: 1,
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginTop: theme.spacing.lg,
    paddingTop: theme.spacing.md,
  },
  companionSub: {
    color: theme.colors.textDim,
    fontSize: theme.typography.small,
    fontWeight: '800',
    marginTop: theme.spacing.xs,
  },
  companionTitle: {
    color: theme.colors.text,
    fontSize: theme.typography.cardTitle,
    fontWeight: '900',
  },
  companionScoreGrid: {
    borderTopColor: theme.colors.border,
    borderTopWidth: 1,
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: theme.spacing.sm,
    marginTop: theme.spacing.lg,
    paddingTop: theme.spacing.md,
  },
  companionScoreTile: {
    backgroundColor: theme.colors.surface,
    borderColor: theme.colors.borderSubtle,
    borderRadius: theme.radius.sm,
    borderWidth: 0.5,
    flexBasis: '45%',
    flexGrow: 1,
    padding: theme.spacing.sm,
  },
  companionScoreValue: {
    fontSize: 22,
    fontWeight: '900',
    marginTop: theme.spacing.xs,
  },
  generated: {
    color: theme.colors.textDim,
    ...typography.metricLabelStrong,
  },
  heroDate: {
    color: theme.colors.textMuted,
    fontSize: theme.typography.small,
    fontWeight: '900',
    marginTop: theme.spacing.md,
  },
  heroFooter: {
    borderTopColor: theme.colors.border,
    borderTopWidth: 1,
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginTop: theme.spacing.lg,
    paddingTop: theme.spacing.md,
  },
  heroHeadline: {
    color: theme.colors.text,
    ...typography.metricValue,
    marginTop: theme.spacing.lg,
  },
  heroLabel: {
    color: theme.colors.accent,
    ...typography.eyebrow,
  },
  heroTitle: {
    color: theme.colors.text,
    ...typography.heroTitle,
    marginTop: 4,
  },
  heroTop: {
    alignItems: 'flex-start',
    flexDirection: 'row',
    justifyContent: 'space-between',
  },
  highlightCategory: {
    color: theme.colors.textDim,
    ...typography.eyebrow,
  },
  highlightHeader: {
    alignItems: 'center',
    flexDirection: 'row',
    justifyContent: 'space-between',
  },
  highlightName: {
    color: theme.colors.text,
    fontSize: theme.typography.cardTitle,
    fontWeight: '900',
    marginTop: 4,
  },
  highlightText: {
    color: theme.colors.textMuted,
    ...typography.bodyStrong,
    lineHeight: 22,
    marginTop: theme.spacing.md,
  },
  highlightTop: {
    alignItems: 'flex-start',
    flexDirection: 'row',
    gap: theme.spacing.md,
    justifyContent: 'space-between',
  },
  indicatorItem: {
    backgroundColor: theme.colors.surface,
    borderColor: theme.colors.borderSubtle,
    borderRadius: theme.radius.md,
    borderWidth: 0.5,
    padding: theme.spacing.md,
  },
  indicatorList: {
    gap: theme.spacing.md,
    marginTop: theme.spacing.md,
  },
  indicatorName: {
    color: theme.colors.text,
    flex: 1,
    fontSize: theme.typography.cardTitle,
    fontWeight: '900',
  },
  indicatorScore: {
    fontSize: theme.typography.cardTitle,
    fontWeight: '900',
  },
  indicatorText: {
    color: theme.colors.textMuted,
    ...typography.bodyStrong,
    lineHeight: 22,
    marginTop: theme.spacing.sm,
  },
  indicatorTop: {
    alignItems: 'flex-start',
    flexDirection: 'row',
    gap: theme.spacing.md,
    justifyContent: 'space-between',
  },
  highlights: {
    gap: theme.spacing.md,
  },
  integrity: {
    color: theme.colors.textDim,
    ...typography.metricLabelStrong,
  },
  periodShortcut: {
    alignItems: 'center',
    backgroundColor: theme.colors.surfaceMuted,
    borderRadius: theme.radius.sm,
    height: 18,
    justifyContent: 'center',
    width: 18,
  },
  periodShortcutActive: {
    backgroundColor: theme.colors.accent,
  },
  periodShortcutText: {
    color: theme.colors.textMuted,
    fontSize: 10,
    fontWeight: '900',
  },
  periodShortcutTextActive: {
    color: theme.colors.white,
  },
  periodTab: {
    alignItems: 'center',
    backgroundColor: theme.colors.surface,
    borderColor: theme.colors.border,
    borderRadius: theme.radius.pill,
    borderWidth: 1,
    flexDirection: 'row',
    gap: theme.spacing.sm,
    paddingHorizontal: 12,
    paddingVertical: 5,
  },
  periodTabActive: {
    backgroundColor: theme.colors.surfaceElevated,
    borderColor: theme.colors.borderStrong,
  },
  periodTabs: {
    gap: theme.spacing.sm,
  },
  periodText: {
    color: theme.colors.textMuted,
    ...typography.metaStrong,
  },
  periodTextActive: {
    color: theme.colors.text,
  },
  paragraphs: {
    gap: theme.spacing.md,
    marginTop: theme.spacing.lg,
  },
  metricLabel: {
    color: theme.colors.textDim,
    ...typography.eyebrow,
  },
  metricPanel: {
    backgroundColor: theme.colors.surface,
    borderColor: theme.colors.borderSubtle,
    borderRadius: theme.radius.md,
    borderWidth: 0.5,
    marginTop: theme.spacing.lg,
    padding: theme.spacing.md,
  },
  metricValue: {
    color: theme.colors.text,
    ...typography.metricValue,
    marginTop: theme.spacing.sm,
  },
  marketBlock: {
    marginTop: theme.spacing.lg,
  },
  marketChange: {
    fontSize: theme.typography.cardTitle,
    fontWeight: '900',
  },
  marketPrice: {
    color: theme.colors.text,
    ...typography.metricValue,
  },
  marketPriceRow: {
    alignItems: 'baseline',
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: theme.spacing.md,
    marginTop: theme.spacing.sm,
  },
  notificationBody: {
    color: theme.colors.textMuted,
    ...typography.bodyStrong,
    lineHeight: 22,
    marginTop: theme.spacing.md,
  },
  notificationButton: {
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 8,
    paddingHorizontal: 16,
    borderRadius: theme.radius.pill,
    borderWidth: 0.5,
    borderColor: theme.colors.border,
    backgroundColor: 'transparent',
    marginTop: theme.spacing.lg,
  },
  notificationButtonText: {
    color: theme.colors.accent,
    ...typography.subcopy,
    fontWeight: '700',
    letterSpacing: 0.5,
    textTransform: 'uppercase',
  },
  notificationTitle: {
    color: theme.colors.text,
    ...typography.heroTitle,
    marginTop: 4,
  },
  progressFill: {
    borderRadius: theme.radius.pill,
    height: '100%',
  },
  progressTrack: {
    backgroundColor: theme.colors.border,
    borderRadius: theme.radius.pill,
    height: 7,
    marginTop: theme.spacing.md,
    overflow: 'hidden',
    width: '100%',
  },
  pressed: {
    opacity: 0.86,
    transform: [{ scale: 0.995 }],
  },
  reader: {
    gap: theme.spacing.md,
  },
  readerCard: {
    borderRadius: theme.radius.lg,
    borderWidth: 0.5,
    overflow: 'hidden',
    paddingHorizontal: theme.spacing.md,
    paddingVertical: theme.spacing.md,
  },
  readerHeader: {
    alignItems: 'center',
    flexDirection: 'row',
    justifyContent: 'space-between',
  },
  reportParagraph: {
    color: theme.colors.textMuted,
    fontSize: theme.typography.body,
    fontWeight: '600',
    lineHeight: 24,
  },
  reportSectionHeader: {
    alignItems: 'flex-start',
    flexDirection: 'row',
    gap: theme.spacing.md,
    justifyContent: 'space-between',
  },
  reportSectionLabel: {
    color: theme.colors.textDim,
    fontSize: theme.typography.label,
    fontWeight: '900',
    letterSpacing: 1.4,
    textTransform: 'uppercase',
  },
  reportSectionTitle: {
    color: theme.colors.text,
    fontSize: theme.typography.cardTitle,
    fontWeight: '900',
    marginTop: 4,
  },
  sectionCompanions: {
    gap: theme.spacing.md,
  },
  splitValue: {
    color: theme.colors.text,
    fontSize: theme.typography.cardTitle,
    fontWeight: '900',
    marginTop: theme.spacing.xs,
  },
  targetChip: {
    backgroundColor: theme.colors.surface,
    borderColor: theme.colors.border,
    borderRadius: theme.radius.sm,
    borderWidth: 1,
    paddingHorizontal: theme.spacing.sm,
    paddingVertical: theme.spacing.xs,
  },
  targetText: {
    color: theme.colors.textMuted,
    fontSize: theme.typography.small,
    fontWeight: '900',
  },
  targetWrap: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: theme.spacing.sm,
    marginTop: theme.spacing.md,
  },
  sectionLabel: {
    color: theme.colors.accent,
    fontSize: theme.typography.label,
    fontWeight: '900',
    letterSpacing: 1.5,
    textTransform: 'uppercase',
  },
  sectionTitle: {
    color: theme.colors.text,
    fontSize: theme.typography.title,
    fontWeight: '900',
    marginTop: 4,
  },
});
