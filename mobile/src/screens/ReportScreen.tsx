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
import { mockBriefing, mockReportHighlights } from '../data/mockFoundation';
import { useApiResource } from '../hooks/useApiResource';
import { MobileReportHighlight, MobileReportResponse, ReportResponse, intelligenceApi } from '../services/tradamindApi';
import { triggerHaptic } from '../utils/haptics';

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

const periods: Array<{ id: ReportPeriod; label: string; short: string }> = [
  { id: 'daily', label: 'Dagrapport', short: 'D' },
  { id: 'weekly', label: 'Weekrapport', short: 'W' },
  { id: 'monthly', label: 'Maandrapport', short: 'M' },
  { id: 'quarterly', label: 'Kwartaalrapport', short: 'Q' },
];

export function ReportScreen() {
  const [period, setPeriod] = useState<ReportPeriod>('daily');

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
      intelligenceApi.latestDailyReport('BTC', 'mobile'),
      intelligenceApi.latestDailyReportFull('BTC'),
    ]);
    return { full, mobile };
  }, [period]);

  const reportResource = useApiResource<ReportPayload>({
    fallbackData: {},
    fetcher: fetchReport,
  });

  const report = useMemo(
    () => mapMobileReport(reportResource.data.mobile, period, reportResource.data.full),
    [period, reportResource.data],
  );

  async function changePeriod(nextPeriod: ReportPeriod) {
    await triggerHaptic('selection');
    setPeriod(nextPeriod);
  }

  return (
    <ScreenContainer
      refreshing={reportResource.refreshing}
      onRefresh={reportResource.refresh}
    >
      <AssetContextHeader asset="BTC" context="Reports intelligence" updatedAt={report.updatedAt} />
      <SectionHeader
        label="Report"
        title="Tradamind intelligence"
        description="Compacte conclusie bovenin, volledige report reader eronder voor de desktop-inhoud op mobiel."
      />

      <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.periodTabs}>
        {periods.map((item) => (
          <Pressable
            key={item.id}
            onPress={() => changePeriod(item.id)}
            style={[styles.periodTab, item.id === period && styles.periodTabActive]}
          >
            <View style={[styles.periodShortcut, item.id === period && styles.periodShortcutActive]}>
              <Text style={[styles.periodShortcutText, item.id === period && styles.periodShortcutTextActive]}>{item.short}</Text>
            </View>
            <Text style={[styles.periodText, item.id === period && styles.periodTextActive]}>{item.label}</Text>
          </Pressable>
        ))}
      </ScrollView>

      {reportResource.loading ? (
        <LoadingSkeletonCard />
      ) : (
        <ReportHero report={report} />
      )}

      <View style={styles.readerHeader}>
        <View>
          <Text style={styles.sectionLabel}>Full report</Text>
          <Text style={styles.sectionTitle}>Leesmodus</Text>
        </View>
        <StatusChip label={`${report.fullSections.length} secties · ${report.readingMinutes} min`} tone="accent" />
      </View>

      <View style={styles.reader}>
        {report.fullSections.map((section) => (
          <ReportSectionCard key={section.title} section={section} />
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

      {report.isFallback ? (
        <InsightCard
          label="Fallback"
          title="Report gebruikt tijdelijk voorbeeldcontext."
          body="De mobiele report API gaf geen bruikbaar rapport terug. De layout blijft testbaar met fallbackdata."
          tone="warning"
        />
      ) : null}
    </ScreenContainer>
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
  isFallback: boolean;
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

function ReportHero({ report }: { report: MappedReport }) {
  return (
    <CardShell emphasis="primary">
      <View style={styles.heroTop}>
        <View>
          <Text style={styles.heroLabel}>System rapportage</Text>
          <Text style={styles.heroTitle}>{report.periodLabel}</Text>
        </View>
        <StatusChip label={report.overallTone === 'danger' ? 'Review' : 'Ready'} tone={report.overallTone} />
      </View>

      <Text style={styles.heroHeadline}>{report.headline}</Text>
      <Text style={styles.heroDate}>Periode: {report.dateLabel}</Text>

      <View style={styles.heroFooter}>
        <Text style={styles.integrity}>Integrity check voltooid</Text>
        <Text style={styles.generated}>Update: {report.generatedLabel}</Text>
      </View>
    </CardShell>
  );
}

function HighlightCard({
  highlight,
}: {
  highlight: MappedReport['highlights'][number];
}) {
  return (
    <CardShell>
      <View style={styles.highlightTop}>
        <View>
          <Text style={styles.highlightCategory}>{highlight.category}</Text>
          <Text style={styles.highlightName}>{highlight.name}</Text>
        </View>
        {highlight.score === null ? null : <StatusChip label={String(highlight.score)} tone={highlight.tone} />}
      </View>
      <Text style={styles.highlightText}>{highlight.interpretation}</Text>
    </CardShell>
  );
}

function ReportSectionCard({
  section,
}: {
  section: MappedReport['fullSections'][number];
}) {
  return (
    <CardShell>
      <View style={styles.reportSectionHeader}>
        <View>
          <Text style={styles.reportSectionLabel}>{section.label}</Text>
          <Text style={styles.reportSectionTitle}>{section.title}</Text>
        </View>
        <StatusChip label="Read" tone={section.tone} />
      </View>

      <View style={styles.paragraphs}>
        {section.paragraphs.map((paragraph, index) => (
          <Text key={`${section.title}-${index}`} style={styles.reportParagraph}>
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
    </CardShell>
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
  return (
    <View style={styles.companionCard}>
      <Text style={styles.companionTitle}>Marktanalyse</Text>

      <View style={styles.marketBlock}>
        <Text style={styles.metricLabel}>Bitcoin prijs</Text>
        <View style={styles.marketPriceRow}>
          <Text style={styles.marketPrice}>{formatCurrency(companion.price)}</Text>
          <Text style={[styles.marketChange, { color: companion.change >= 0 ? theme.colors.success : theme.colors.danger }]}>
            {formatSignedPercent(companion.change)}
          </Text>
        </View>
      </View>

      <View style={styles.marketBlock}>
        <Text style={styles.metricLabel}>Totaal volume</Text>
        <Text style={styles.metricValue}>{formatFullNumber(companion.volume)}</Text>
      </View>

      <View style={styles.companionScoreGrid}>
        {companion.scores.map((score) => (
          <View key={score.label} style={styles.companionScoreTile}>
            <Text style={styles.metricLabel}>{score.label}</Text>
            <Text style={[styles.companionScoreValue, { color: colorForTone(score.tone) }]}>{score.value}</Text>
          </View>
        ))}
      </View>
    </View>
  );
}

function IndicatorCompanionCard({ companion }: { companion: Extract<ReportCompanion, { type: 'indicators' }> }) {
  return (
    <View style={styles.companionCard}>
      <Text style={styles.companionTitle}>{companion.title}</Text>
      <View style={styles.indicatorList}>
        {companion.items.map((item, index) => (
          <View key={`${item.name}-${index}`} style={styles.indicatorItem}>
            <View style={styles.indicatorTop}>
              <Text style={styles.indicatorName}>{item.name}</Text>
              {item.score === null ? null : <Text style={[styles.indicatorScore, { color: colorForTone(item.tone) }]}>{item.score}</Text>}
            </View>
            <Text style={styles.indicatorText}>{item.interpretation}</Text>
          </View>
        ))}
      </View>
    </View>
  );
}

function SetupCompanionCard({ companion }: { companion: Extract<ReportCompanion, { type: 'setup' }> }) {
  return (
    <View style={styles.companionCard}>
      <Text style={styles.companionTitle}>Optimale Setup</Text>
      <View style={styles.companionInner}>
        <View style={styles.companionRow}>
          <Text style={styles.companionMeta}>{companion.matchLabel}</Text>
          <StatusChip label={`${Math.round(companion.score)}%`} tone={toneForScore(companion.score)} />
        </View>
        <Text style={styles.companionPrimary}>{companion.name}</Text>
        <Text style={styles.companionSub}>{companion.symbol} · {companion.timeframe}</Text>
        <View style={styles.progressTrack}>
          <View style={[styles.progressFill, { backgroundColor: colorForTone(toneForScore(companion.score)), width: `${Math.max(0, Math.min(100, companion.score))}%` }]} />
        </View>
      </View>

      {companion.topSetups.length > 0 ? (
        <View style={styles.companionList}>
          {companion.topSetups.slice(0, 3).map((setup) => (
            <View key={setup.id} style={styles.companionListRow}>
              <Text style={styles.companionListName}>{setup.name}</Text>
              <Text style={styles.companionListValue}>{Math.round(setup.score)}%</Text>
            </View>
          ))}
        </View>
      ) : null}

      <Text style={styles.companionNote}>
        Geselecteerd op basis van huidige macro-, markt- en setupcondities.
      </Text>
    </View>
  );
}

function StrategyCompanionCard({ companion }: { companion: Extract<ReportCompanion, { type: 'strategy' }> }) {
  return (
    <View style={styles.companionCard}>
      <Text style={styles.companionTitle}>Actieve Strategie</Text>
      <Text style={styles.companionPrimary}>{companion.name}</Text>
      <Text style={styles.companionSub}>{companion.symbol} · {companion.timeframe}</Text>

      <View style={styles.metricPanel}>
        <Text style={styles.metricLabel}>{companion.entry === null ? 'Referentieprijs' : 'Instapprijs'}</Text>
        <Text style={styles.metricValue}>{formatCurrency(companion.entry ?? 0)}</Text>
      </View>

      {companion.targets.length > 0 ? (
        <View style={styles.targetWrap}>
          {companion.targets.slice(0, 4).map((target, index) => (
            <View key={`${target}-${index}`} style={styles.targetChip}>
              <Text style={styles.targetText}>{target}</Text>
            </View>
          ))}
        </View>
      ) : null}

      <View style={styles.companionSplit}>
        <View>
          <Text style={styles.metricLabel}>Stop-loss</Text>
          <Text style={styles.splitValue}>{formatCurrency(companion.stopLoss ?? 0)}</Text>
        </View>
        <View style={styles.alignRight}>
          <Text style={styles.metricLabel}>Vertrouwen</Text>
          <Text style={styles.splitValue}>{companion.confidence === null ? '-' : `${Math.round(companion.confidence)}%`}</Text>
        </View>
      </View>
    </View>
  );
}

function BotCompanionCard({ companion }: { companion: Extract<ReportCompanion, { type: 'bot' }> }) {
  const actionTone = companion.action === 'buy' ? 'success' : companion.action === 'sell' ? 'danger' : 'neutral';

  return (
    <View style={styles.companionCard}>
      <Text style={styles.companionTitle}>Handelsactie</Text>
      <Text style={styles.companionPrimary}>{companion.botName}</Text>

      <View style={[styles.actionPanel, { borderColor: colorForTone(actionTone), backgroundColor: softBackgroundForTone(actionTone) }]}>
        <View>
          <Text style={styles.metricLabel}>Actie</Text>
          <Text style={[styles.actionValue, { color: colorForTone(actionTone) }]}>{companion.action.toUpperCase()}</Text>
        </View>
        <View style={styles.alignRight}>
          <Text style={styles.metricLabel}>Vertrouwen</Text>
          <Text style={styles.splitValue}>{companion.confidence === null ? '-' : `${Math.round(companion.confidence)}%`}</Text>
        </View>
      </View>

      <View style={styles.companionSplit}>
        <View>
          <Text style={styles.metricLabel}>Ordergrootte</Text>
          <Text style={styles.splitValue}>{companion.amount === null ? '-' : `EUR ${formatCompactNumber(companion.amount)}`}</Text>
        </View>
        <View style={styles.alignRight}>
          <Text style={styles.metricLabel}>Setup match</Text>
          <Text style={styles.splitValue}>{companion.setupMatch === null ? '-' : `${Math.round(companion.setupMatch)}%`}</Text>
        </View>
      </View>

      <Text style={styles.companionNote}>{companion.reason}</Text>
    </View>
  );
}

function mapMobileReport(
  report: MobileReportResponse | undefined,
  period: ReportPeriod,
  fullReport?: ReportResponse,
): MappedReport {
  if (!report || report._status === 'pending') return fallbackReport(period);

  const summary = compactText(String(report.executive_summary_compact || ''), 420);
  const marketAnalysis = compactText(String(report.market_analysis_compact || ''), 380);
  const outlook = compactText(String(report.outlook_compact || ''), 320);
  const scores = scoresFromKpis(report.kpi_metrics);
  const avgScore = scores.reduce((total, item) => total + item.value, 0) / Math.max(1, scores.length);
  const headline = headlineFromReport(summary, avgScore);
  const highlights = normalizeHighlights(report.highlights);
  const fullSections = fullReportSections(fullReport, report);

  return {
    conclusionTitle: conclusionTitle(avgScore),
    dateLabel: report.report_date || dateRange(report.period_start, report.period_end) || 'Recent',
    fullSections,
    generatedLabel: timeLabel(report.generated_at),
    headline,
    highlights,
    isFallback: false,
    marketAnalysis,
    overallTone: toneForScore(avgScore),
    outlook,
    periodLabel: periodLabel(period),
    readingMinutes: readingMinutes(fullSections),
    scores,
    summary: summary || 'FINN heeft het rapport geladen, maar er is geen compacte samenvatting beschikbaar.',
    updatedAt: timeLabel(report.generated_at),
  };
}

function fallbackReport(period: ReportPeriod): MappedReport {
  const highlights = mockReportHighlights.map((item) => ({
    category: item.title,
    interpretation: item.value,
    name: item.title,
    score: null,
    tone: item.tone,
  }));

  return {
    conclusionTitle: 'Geduld blijft de hoofdactie',
    dateLabel: 'Recent',
    fullSections: [
      {
        companions: [
          {
            change: 0.4,
            price: 81187,
            scores: [
              { label: 'Macro', value: 68, tone: 'accent' },
              { label: 'Technical', value: 71, tone: 'success' },
              { label: 'Market', value: 74, tone: 'success' },
              { label: 'Setup', value: 63, tone: 'warning' },
            ],
            type: 'market',
            volume: 31897671988,
          },
        ],
        label: 'Overview',
        paragraphs: splitReportParagraphs(
          'The morning read favors patience: market structure is supportive, setup confirmation is incomplete, and portfolio exposure is already meaningful.',
        ),
        title: 'Dagoverzicht',
        tone: 'accent',
      },
      {
        companions: [
          {
            matchLabel: 'Beste match',
            name: 'SOL Setup',
            score: 63,
            symbol: 'SOL',
            timeframe: '1w',
            topSetups: [],
            type: 'setup',
          },
        ],
        label: 'Setup',
        paragraphs: splitReportParagraphs('Fallback setup-context zodat de report companion card zichtbaar blijft tijdens offline testen.'),
        title: 'Setup validatie',
        tone: 'warning',
      },
      {
        label: 'Outlook',
        paragraphs: splitReportParagraphs('Vraag FINN om dit rapport te vertalen naar setup- en risicocontext.'),
        title: 'Vooruitblik',
        tone: 'warning',
      },
    ],
    generatedLabel: mockBriefing.updatedAt,
    headline: 'Constructive, not urgent',
    highlights,
    isFallback: true,
    marketAnalysis: 'Market structure is supportive, but setup confirmation remains incomplete.',
    overallTone: 'warning',
    outlook: 'Vraag FINN om dit rapport te vertalen naar setup- en risicocontext.',
    periodLabel: periodLabel(period),
    readingMinutes: 1,
    scores: [
      { label: 'Macro', value: 68, tone: 'accent' },
      { label: 'Technical', value: 71, tone: 'success' },
      { label: 'Market', value: 74, tone: 'success' },
      { label: 'Setup', value: 63, tone: 'warning' },
    ],
    summary:
      'The morning read favors patience: market structure is supportive, setup confirmation is incomplete, and portfolio exposure is already meaningful.',
    updatedAt: mockBriefing.updatedAt,
  };
}

function scoresFromKpis(kpis?: Record<string, unknown> | null) {
  const items = [
    ['Macro', readNumber(kpis, 'macro_score')],
    ['Technical', readNumber(kpis, 'technical_score')],
    ['Market', readNumber(kpis, 'market_score')],
    ['Setup', readNumber(kpis, 'setup_score')],
  ] as const;

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

  if (normalized.length > 0) return normalized;

  return mockReportHighlights.map((item) => ({
    category: item.title,
    interpretation: item.value,
    name: item.title,
    score: null,
    tone: item.tone,
  }));
}

function fullReportSections(fullReport: ReportResponse | undefined, mobileReport: MobileReportResponse) {
  const scores = scoresFromKpis(mobileReport.kpi_metrics);
  const sections = [
    {
      companions: [marketCompanion(fullReport, mobileReport, scores)].filter(Boolean) as ReportCompanion[],
      label: 'Overview',
      source: readReportText(fullReport, ['executive_summary']) || String(mobileReport.executive_summary_compact || ''),
      title: 'Dagoverzicht',
      tone: 'accent' as StatusTone,
    },
    {
      companions: [indicatorCompanion(fullReport, mobileReport, 'market_indicator_highlights', 'Market Indicator Highlights', 'market')].filter(Boolean) as ReportCompanion[],
      label: 'Market analyse',
      source: readReportText(fullReport, ['market_analysis']) || String(mobileReport.market_analysis_compact || ''),
      title: 'Marktbeeld',
      tone: 'warning' as StatusTone,
    },
    {
      companions: [indicatorCompanion(fullReport, mobileReport, 'technical_indicator_highlights', 'Technical Indicator Highlights', 'technical')].filter(Boolean) as ReportCompanion[],
      label: 'Technical',
      source: readReportText(fullReport, ['technical_analysis']),
      title: 'Technische analyse',
      tone: 'danger' as StatusTone,
    },
    {
      companions: [indicatorCompanion(fullReport, mobileReport, 'macro_indicator_highlights', 'Macro Indicator Highlights', 'macro')].filter(Boolean) as ReportCompanion[],
      label: 'Macro',
      source: readReportText(fullReport, ['macro_context']),
      title: 'Macro context',
      tone: 'neutral' as StatusTone,
    },
    {
      companions: [setupCompanion(fullReport, mobileReport)].filter(Boolean) as ReportCompanion[],
      label: 'Setup',
      source: readReportText(fullReport, ['setup_validation']),
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
      source: readReportText(fullReport, ['bot_strategy']),
      title: 'Bot strategie',
      tone: 'neutral' as StatusTone,
    },
    {
      label: 'Outlook',
      source: readReportText(fullReport, ['outlook']) || String(mobileReport.outlook_compact || ''),
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

  return Math.max(1, Math.ceil(words / 180));
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

function periodLabel(period: ReportPeriod) {
  if (period === 'weekly') return 'Weekrapport';
  if (period === 'monthly') return 'Maandrapport';
  if (period === 'quarterly') return 'Kwartaalrapport';
  return 'Dagrapport';
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
    borderWidth: 1,
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
    fontSize: 29,
    fontWeight: '900',
    letterSpacing: 0,
    lineHeight: 34,
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
    borderWidth: 1,
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
    height: 22,
    justifyContent: 'center',
    width: 22,
  },
  periodShortcutActive: {
    backgroundColor: theme.colors.accent,
  },
  periodShortcutText: {
    color: theme.colors.textMuted,
    fontSize: 11,
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
    paddingHorizontal: theme.spacing.md,
    paddingVertical: theme.spacing.sm,
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
    fontSize: 12,
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
    borderWidth: 1,
    marginTop: theme.spacing.lg,
    padding: theme.spacing.md,
  },
  metricValue: {
    color: theme.colors.text,
    fontSize: 24,
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
    fontSize: 34,
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
  reader: {
    gap: theme.spacing.md,
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
