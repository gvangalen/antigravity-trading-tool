import { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigation, useRoute } from '@react-navigation/native';
import type { NavigationProp, RouteProp } from '@react-navigation/native';
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';

import { CardShell } from '../components/cards/CardShell';
import { InsightCard } from '../components/cards/InsightCard';
import { LoadingSkeletonCard } from '../components/layout/LoadingSkeletonCard';
import { ScreenContainer } from '../components/layout/ScreenContainer';
import { StatusChip } from '../components/layout/StatusChip';
import { TodayWithFinnCard } from '../components/workspace/TodayWithFinnCard';
import { SegmentedControl } from '../components/layout/SegmentedControl';
import { WorkspaceHeroSection } from '../components/workspace/WorkspaceHeroSection';
import { StatusTone, theme } from '../constants/theme';
import { localizedBackendText, translate, translateFinnTag } from '../i18n';
import { triggerHaptic } from '../utils/haptics';
import { useFinnOverlay } from '../contexts/FinnOverlayContext';
import { useApiResource } from '../hooks/useApiResource';
import type { MainTabParamList } from '../navigation/MainTabNavigator';
import { preferenceColors, useAppPreferences } from '../preferences/AppPreferencesProvider';
import type { AppLanguage } from '../preferences/appLocale';
import { MobileOverviewResponse, MobileReportHighlight, MobileReportResponse, ReportResponse, intelligenceApi, mobileApi } from '../services/tradamindApi';
import { trackAssistantEvent } from '../services/assistantAnalytics';

type ReportPeriod = 'daily' | 'weekly' | 'monthly' | 'quarterly';
type ReportPayload = { full?: ReportResponse; mobile?: MobileReportResponse };
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

export function ReportScreen() {
  const navigation = useNavigation<NavigationProp<MainTabParamList>>();
  const route = useRoute<RouteProp<MainTabParamList, 'Report'>>();
  const { openFinn } = useFinnOverlay();
  const [period, setPeriod] = useState<ReportPeriod>('daily');
  const activeSymbol = route.params?.symbol ?? 'BTC';
  const notificationType = route.params?.notificationType;
  const { appearance, language } = useAppPreferences();
  const colors = preferenceColors(appearance);
  const periods: Array<{ id: ReportPeriod; label: string; short: string }> = [
    { id: 'daily', label: translate(language, 'report.period.daily'), short: 'D' },
    { id: 'weekly', label: translate(language, 'report.period.weekly'), short: 'W' },
    { id: 'monthly', label: translate(language, 'report.period.monthly'), short: 'M' },
    { id: 'quarterly', label: translate(language, 'report.period.quarterly'), short: 'Q' },
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
      const [mobile, full] = await Promise.all([
        intelligenceApi.latestWeeklyReport('mobile'),
        intelligenceApi.latestWeeklyReportFull(),
      ]);
      return { full, mobile };
    }
    if (period === 'monthly') {
      const [mobile, full] = await Promise.all([
        intelligenceApi.latestMonthlyReport('mobile'),
        intelligenceApi.latestMonthlyReportFull(),
      ]);
      return { full, mobile };
    }
    if (period === 'quarterly') {
      const [mobile, full] = await Promise.all([
        intelligenceApi.latestQuarterlyReport('mobile'),
        intelligenceApi.latestQuarterlyReportFull(),
      ]);
      return { full, mobile };
    }

    const [mobile, full] = await Promise.all([
      intelligenceApi.latestDailyReport(activeSymbol, 'mobile'),
      intelligenceApi.latestDailyReportFull(activeSymbol),
    ]);
    return { full, mobile };
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
      refreshing={reportResource.refreshing || overviewResource.refreshing}
      onRefresh={async () => {
        await Promise.all([reportResource.refresh(), overviewResource.refresh()]);
      }}
    >
      <ReflectionTodayHero
        activeSymbol={activeSymbol}
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

      {notificationType ? (
        <ReportNotificationCard
          notificationType={notificationType}
          symbol={activeSymbol}
          onAskFinn={() => {
            trackAssistantEvent({
              event_name: 'report_finn_requested',
              page: 'report',
              flow_type: 'report_explain',
              asset: activeSymbol,
              report_type: period,
            });
            return (
            openFinn({
              prefill: `Leg uit wat belangrijk is in het ${period} rapport voor ${activeSymbol}. Geef conclusie, risico en veilige volgende stap.`,
              source: `push-${notificationType}`,
            })
            );
          }}
        />
      ) : null}

      {reportResource.loading ? (
        <LoadingSkeletonCard />
      ) : (
        <ReflectionSummaryGrid report={report} />
      )}

      <SegmentedControl
        items={periods.map((item) => ({ key: item.id, label: item.label }))}
        selected={period}
        onChange={(value) => changePeriod(value as ReportPeriod)}
      />

      {!reportResource.loading && report.highlights.length > 0 ? (
        <View style={styles.highlights}>
          {report.highlights.slice(0, 3).map((highlight, index) => (
            <HighlightCard key={`${highlight.category}-${highlight.name}-${index}`} highlight={highlight} />
          ))}
        </View>
      ) : null}

      <View style={styles.readerHeader}>
        <View>
          <Text style={styles.sectionLabel}>Full report</Text>
          <Text style={[styles.sectionTitle, { color: colors.text }]}>Leesmodus</Text>
        </View>
        <StatusChip label={`${report.fullSections.length} secties · ${report.readingMinutes} min`} tone="accent" />
      </View>

      <View style={styles.reader}>
        {report.fullSections.map((section, index) => (
          <ReportSectionCard key={`${section.title}-${index}`} section={section} />
        ))}
      </View>

      {reportResource.error ? (
        <InsightCard
          label="Report error"
          title="Rapport kon niet live laden."
          body={reportResource.error.message}
          cta="Retry"
          tone="danger"
          onPress={reportResource.refresh}
        />
      ) : null}

      {report.isUnavailable ? (
        <InsightCard
          label="Report"
          title={translate(language, 'report.unavailableHeadline')}
          body={translate(language, 'report.unavailableBody')}
          tone="warning"
        />
      ) : null}
    </ScreenContainer>
  );
}

function ReflectionTodayHero({
  activeSymbol,
  briefing,
  onAskFinn,
  report,
}: {
  activeSymbol: string;
  briefing?: MobileOverviewResponse['finn_briefing'];
  onAskFinn: () => void;
  report: MappedReport;
}) {
  const { language } = useAppPreferences();
  const warningCount = report.highlights.filter((item) => item.tone === 'danger' || item.tone === 'warning').length;
  const confidenceLabel =
    report.scores.find((item) => item.label.toLowerCase().includes('combined')) ||
    report.scores[0];
  const tags = [
    { label: translateFinnTag(language, report.conclusionTitle), tone: report.overallTone },
    { label: report.periodLabel, tone: 'accent' as StatusTone },
    confidenceLabel ? { label: translate(language, 'common.confidence', { count: confidenceLabel.value }), tone: confidenceLabel.tone } : null,
    { label: translate(language, 'common.sections', { count: report.fullSections.length }), tone: 'neutral' as StatusTone },
  ].filter(Boolean) as Array<{ label: string; tone: StatusTone }>;
  const queueItems = [
    {
      key: 'sections',
      label: translate(language, 'queue.label.sections'),
      value: report.fullSections.length,
      body: translate(language, 'queue.body.fullReportBlocks'),
    },
    {
      key: 'highlights',
      label: translate(language, 'queue.label.highlights'),
      value: report.highlights.length,
      body: translate(language, 'queue.body.topItemsSurfaced'),
    },
    {
      key: 'risks',
      label: translate(language, 'queue.label.risks'),
      value: warningCount,
      body: translate(language, 'queue.body.warningsAndFlags'),
    },
    {
      key: 'reading',
      label: translate(language, 'queue.label.reading'),
      value: `${report.readingMinutes}m`,
      body: translate(language, 'queue.body.estimatedTimeToFinish'),
    },
  ];

  const support = report.isUnavailable
    ? translate(language, 'report.unavailableBody')
    : translate(language, 'report.risksNeedAttention', { count: warningCount });

  return (
    <WorkspaceHeroSection>
      <TodayWithFinnCard
        headline={localizedBackendText(
          language,
          briefing?.summary?.trim(),
          report.isUnavailable ? translate(language, 'report.unavailableHeadline') : translate(language, 'finn.noBriefingReady'),
        )}
        support={support}
        tags={tags}
        primaryActionLabel={translate(language, 'finn.askAboutThisReport')}
        onPrimaryAction={onAskFinn}
        queueItems={queueItems}
        queueStatusLabel={translate(language, 'common.itemsOpen', { count: Number(queueItems[0]?.value ?? 0) })}
      />
    </WorkspaceHeroSection>
  );
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
  const { appearance } = useAppPreferences();
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
        <Text style={styles.reportActionText}>Ask FINN to translate this report</Text>
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
  const { appearance } = useAppPreferences();
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
  const { appearance } = useAppPreferences();
  const colors = preferenceColors(appearance);

  return (
    <View style={{ paddingVertical: theme.spacing.md, paddingHorizontal: theme.spacing.lg }}>
      <View style={styles.heroTop}>
        <View>
          <Text style={styles.heroLabel}>Push context</Text>
          <Text style={[styles.notificationTitle, { color: colors.text }]}>{notificationType === 'report_ready' ? 'Rapport staat klaar' : 'Rapport context'}</Text>
        </View>
        <StatusChip label={symbol} tone="accent" />
      </View>
      <Text style={[styles.notificationBody, { color: colors.textMuted }]}>
        Open dit rapport als context, niet als alarm. FINN kan de conclusie, risico's en volgende stap kort duiden.
      </Text>
      <Pressable
        onPress={async () => {
          await triggerHaptic('selection');
          onAskFinn();
        }}
        style={({ pressed }) => [styles.notificationButton, pressed && styles.pressed]}
      >
        <Text style={styles.notificationButtonText}>Vraag FINN om uitleg</Text>
      </Pressable>
    </View>
  );
}

function HighlightCard({
  highlight,
}: {
  highlight: MappedReport['highlights'][number];
}) {
  const { appearance } = useAppPreferences();
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
  const { appearance } = useAppPreferences();
  const colors = preferenceColors(appearance);

  return (
    <View style={{ paddingVertical: theme.spacing.md, paddingHorizontal: theme.spacing.lg }}>
      <View style={[styles.readerCard, { borderColor: colors.border, backgroundColor: colors.surface }]}>
      <View style={styles.reportSectionHeader}>
        <View>
          <Text style={[styles.reportSectionLabel, { color: colors.textDim }]}>{section.label}</Text>
          <Text style={[styles.reportSectionTitle, { color: colors.text }]}>{section.title}</Text>
        </View>
        <StatusChip label="Read" tone={section.tone} />
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
          <Text style={{ fontSize: 24, color: colors.text, fontWeight: '700' }}>{formatCurrency(companion.price)}</Text>
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
          <Text style={{ fontSize: 24, color: colors.text, fontWeight: '700' }}>{companion.name}</Text>
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
        <Text style={{ fontSize: 11, color: colors.textDim, fontWeight: '700', letterSpacing: 0.5 }}>{companion.entry === null ? 'REFERENTIEPRIJS' : 'INSTAPPRYS'}</Text>
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

  const summary = compactText(String(hydratedReport.executive_summary_compact || ''), 420);
  const marketAnalysis = compactText(String(hydratedReport.market_analysis_compact || ''), 380);
  const outlook = compactText(String(hydratedReport.outlook_compact || ''), 320);
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
    executive_summary_compact: compactText(
      readReportText(fullReport, ['executive_summary', 'summary']),
      420,
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
    market_analysis_compact: compactText(
      readReportText(fullReport, ['market_analysis', 'market_overview']),
      380,
    ),
    outlook_compact: compactText(
      readReportText(fullReport, ['outlook', 'strategic_lessons']),
      320,
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
    conclusionTitle: 'Unavailable',
    dateLabel: '-',
    fullSections: [],
    generatedLabel: '-',
    headline: '',
    highlights: [],
    isUnavailable: true,
    marketAnalysis: '',
    overallTone: 'warning',
    outlook: '',
    periodLabel: periodLabel(period, language),
    readingMinutes: 0,
    scores: [],
    summary: '',
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
        interpretation: compactText(String(item.interpretation || 'Geen interpretatie beschikbaar.'), 160),
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
        interpretation: compactText(interpretation, 150),
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
    symbol: readStringField(bestSetup, ['symbol', 'asset']) || 'BTC',
    timeframe: readStringField(bestSetup, ['timeframe', 'frequency']) || '1w',
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
    symbol: readStringField(strategy, ['symbol', 'asset']) || 'BTC',
    targets: normalizeTargets(readField(strategy, ['targets', 'target_prices'])),
    timeframe: readStringField(strategy, ['timeframe', 'frequency']) || '1w',
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

function readField(source: Record<string, unknown>, keys: string[]) {
  for (const key of keys) {
    if (source[key] !== undefined && source[key] !== null) return source[key];
  }
  return undefined;
}

function readStringField(source: Record<string, unknown>, keys: string[]) {
  const value = readField(source, keys);
  if (typeof value === 'string' && value.trim()) return value.trim();
  if (typeof value === 'number' && Number.isFinite(value)) return String(value);
  return '';
}

function readNumericField(source: Record<string, unknown>, keys: string[]) {
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
  summaryCard: {
    borderRadius: theme.radius.md,
    borderWidth: 0.5,
    flexBasis: '47.5%',
    flexGrow: 0,
    flexShrink: 0,
    gap: 4,
    maxWidth: '47.5%',
    minHeight: 86,
    minWidth: 0,
    paddingHorizontal: theme.spacing.md,
    paddingVertical: theme.spacing.md,
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
    marginBottom: theme.spacing.md,
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
    fontSize: 24,
    fontWeight: '900',
    letterSpacing: 0,
    lineHeight: 29,
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
    fontSize: 10,
    fontWeight: '900',
    letterSpacing: 1.2,
    textTransform: 'uppercase',
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
    fontSize: 18,
    fontWeight: '900',
    letterSpacing: 0,
    lineHeight: 22,
    marginTop: theme.spacing.lg,
  },
  heroLabel: {
    color: theme.colors.accent,
    fontSize: theme.typography.label,
    fontWeight: '900',
    letterSpacing: 1.6,
    textTransform: 'uppercase',
  },
  heroTitle: {
    color: theme.colors.text,
    fontSize: theme.typography.title,
    fontWeight: '900',
    marginTop: 4,
  },
  heroTop: {
    alignItems: 'flex-start',
    flexDirection: 'row',
    justifyContent: 'space-between',
  },
  highlightCategory: {
    color: theme.colors.textDim,
    fontSize: theme.typography.label,
    fontWeight: '900',
    letterSpacing: 1.4,
    textTransform: 'uppercase',
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
    fontSize: theme.typography.body,
    fontWeight: '600',
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
    fontSize: theme.typography.body,
    fontWeight: '600',
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
    fontSize: 10,
    fontWeight: '900',
    letterSpacing: 1.2,
    textTransform: 'uppercase',
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
    fontSize: 11,
    fontWeight: '900',
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
    fontSize: theme.typography.label,
    fontWeight: '900',
    letterSpacing: 1.1,
    textTransform: 'uppercase',
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
    fontSize: 18,
    fontWeight: '900',
    letterSpacing: 0,
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
    fontSize: 18,
    fontWeight: '900',
    letterSpacing: 0,
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
    fontSize: theme.typography.body,
    fontWeight: '600',
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
    fontSize: 12,
    fontWeight: '700',
    letterSpacing: 0.5,
    textTransform: 'uppercase',
  },
  notificationTitle: {
    color: theme.colors.text,
    fontSize: theme.typography.title,
    fontWeight: '900',
    lineHeight: 28,
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
