import { useCallback, useMemo, useState, useEffect } from 'react';
import { useRoute, useNavigation } from '@react-navigation/native';
import type { RouteProp } from '@react-navigation/native';
import {
  KeyboardAvoidingView,
  Platform,
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';

import { AssistantFeedRenderer } from '../components/assistant/AssistantFeedRenderer';
import { SuggestedPromptChips } from '../components/assistant/SuggestedPromptChips';
import { MobileFINNFeed } from '../components/assistant/MobileFINNFeed';
import { ActionCard } from '../components/cards/ActionCard';
import { AssistantBriefingCard } from '../components/cards/AssistantBriefingCard';
import { BotDecisionCard } from '../components/cards/BotDecisionCard';
import { InsightCard } from '../components/cards/InsightCard';
import { MarketSnapshotCard } from '../components/cards/MarketSnapshotCard';
import { MasterDecisionCard } from '../components/cards/MasterDecisionCard';
import { AssetContextHeader } from '../components/layout/AssetContextHeader';
import { LoadingSkeletonCard } from '../components/layout/LoadingSkeletonCard';
import { ScreenContainer } from '../components/layout/ScreenContainer';
import { SectionHeader } from '../components/layout/SectionHeader';
import { BottomSheet } from '../components/sheets/BottomSheet';
import {
  ConfirmActionSheetContent,
  DraftReviewSheetContent,
  RiskExplanationSheetContent,
} from '../components/sheets/SheetContent';
import { theme } from '../constants/theme';
import { useApiResource } from '../hooks/useApiResource';
import { mapAssistantEnvelopeToFeedItems } from '../services/assistantEnvelopeMapper';
import {
  mapAssistantInsightCard,
  mapAssistantInsightDetails,
  mapMobileOverviewBotDecision,
  mapMobileOverviewDecision,
  mapMobileOverviewMarket,
  mapMobileOverviewPortfolio,
  mapMobileOverviewPrompts,
} from '../services/dataMappers';
import { preferenceColors, useAppPreferences } from '../preferences/AppPreferencesProvider';
import { AssistantInsightResponse, MobileOverviewAsset, MobileOverviewResponse, MobileIntelligenceEvent, assistantApi, mobileApi, intelligenceApi } from '../services/tradamindApi';
import { apiClient } from '../services/apiClient';
import { AssistantFeedItem, AssistantDraft } from '../types/assistant';
import { triggerHaptic } from '../utils/haptics';
import { useIntelligenceContext } from '../contexts/ActiveIntelligenceContext';
import { useAuth } from '../auth/AuthProvider';
import type { MainTabParamList } from '../navigation/MainTabNavigator';
import { trackAssistantEvent } from '../services/assistantAnalytics';

type SheetType = 'risk' | 'confirm' | 'draft' | null;

function formatFinnContextLabel(pageType?: string, symbol?: string, timeframe?: string) {
  const laneMap: Record<string, string> = {
    FINN: 'Finn',
    Portfolio: 'Portfolio',
    Report: 'Report',
    Setup: 'Setup',
    Setups: 'Setup',
    Strategies: 'Setup',
    Watchlist: 'Watchlist',
  };

  const lane = laneMap[pageType || ''] || pageType || 'Finn';
  return `${lane} · ${symbol || 'BTC'} · ${(timeframe || '1D').toUpperCase()}`;
}

function deriveFinnModeLabel(source?: string, activeState?: any) {
  if (activeState?.current_flow && activeState.current_flow !== 'none') {
    return 'Concept';
  }
  if (source?.includes('live')) return 'Live';
  if (source?.includes('paper')) return 'Paper';
  return 'Read-only';
}

export function FinnScreen({
  isOverlay = false,
  prefill,
  source,
  contextMetric,
  symbol,
  onClose,
}: {
  isOverlay?: boolean;
  prefill?: string;
  source?: string;
  contextMetric?: string;
  symbol?: string;
  onClose?: () => void;
} = {}) {
  const { logout, user } = useAuth();
  const { appearance } = useAppPreferences();
  const colors = preferenceColors(appearance);
  const [query, setQuery] = useState('');
  const [sending, setSending] = useState(false);
  const [chatError, setChatError] = useState<string | null>(null);
  const [sheet, setSheet] = useState<SheetType>(null);
  const [localEvents, setLocalEvents] = useState<MobileIntelligenceEvent[]>([]);
  const [feedItems, setFeedItems] = useState<AssistantFeedItem[]>([]);
  const [currentDraft, setCurrentDraft] = useState<AssistantDraft | null>(null);
  const [activeState, setActiveState] = useState<any>(null);
  const isActionFlow = source?.startsWith('strategy-') || source?.startsWith('setup-') || source?.startsWith('bot-');

  const { context, updateContext } = useIntelligenceContext();
  const apiContext = useMemo(() => ({
    page_type: 'FINN',
    symbol: context.asset,
    timeframe: context.timeframe,
  }), [context.asset, context.timeframe]);
  const finnContextLabel = useMemo(
    () => formatFinnContextLabel(context.screen || context.page_type || context.page || 'FINN', context.asset, context.timeframe),
    [context.asset, context.page_type, context.screen, context.timeframe, context.page]
  );
  const finnModeLabel = useMemo(() => deriveFinnModeLabel(source, activeState), [source, activeState]);

  const fetchOverview = useCallback(() => mobileApi.overview(), []);
  const fetchInsight = useCallback(() => assistantApi.insight(apiContext), [apiContext]);
  const overviewResource = useApiResource<MobileOverviewResponse | undefined>({
    fallbackData: undefined,
    fetcher: fetchOverview,
  });
  const insightResource = useApiResource<AssistantInsightResponse | undefined>({
    fallbackData: undefined,
    fetcher: fetchInsight,
  });
  useEffect(() => {
    trackAssistantEvent({
      event_name: 'screen_view',
      page: isOverlay ? 'finn_overlay' : 'finn',
      flow_type: source || 'finn',
      asset: symbol || context.asset || null,
    });
  }, [context.asset, isOverlay, source, symbol]);
  useEffect(() => {
    if (overviewResource.data?.intelligence_events) {
      setLocalEvents(overviewResource.data.intelligence_events);
    }
  }, [overviewResource.data?.intelligence_events]);

  const getMetricTitle = (metric: string) => {
    const titles: Record<string, string> = {
      transition_risk: 'Transition Risk Analysis',
      setup_quality: 'Setup Quality Assessment',
      market_pressure: 'Market Pressure Analysis',
      structural_cycle: 'Structural Cycle Phase',
      position_size: 'Position Size Telemetry',
      trend_strength: 'Trend Strength Evaluation',
    };
    return titles[metric] || 'Contextual Intelligence';
  };

  const getMetricAnalysisText = (metric: string, symbol = 'BTC', tf = '1W') => {
    switch (metric) {
      case 'transition_risk':
        return `FINN detecteert toenemende regime-instabiliteit door afnemende trend strength en hogere volatiliteit voor ${symbol}. Nieuwe agressieve entries worden momenteel niet aanbevolen op het ${tf} timeframe.`;
      case 'setup_quality':
        return `De setup quality score weerspiegelt robuuste confluences en gunstige risk/reward verhoudingen voor ${symbol}. Voldoet momenteel aan alle institutionele instapeisen.`;
      case 'market_pressure':
        return `De verkoopdruk neemt toe in de orderboeken van ${symbol} met dalend volume op stijgingen. FINN adviseert strakkere stop-loss niveaus op ${tf}.`;
      case 'structural_cycle':
        return `De macro-structuur van ${symbol} bevindt zich in een vroege herstelfase (recovery). Accumulatie op belangrijke steunniveaus wordt ondersteund door stabiele kapitaalinstroom.`;
      case 'position_size':
        return `Huidige aanbevolen positiegrootte voor ${symbol} is defensief (50%). Verlaag actieve blootstelling bij verhoogde marktvolatiliteit om kapitaalbehoud te garanderen.`;
      case 'trend_strength':
        return `De trend strength toont zwakke momentum-indicatoren op korte termijn voor ${symbol}. Verwacht verdere consolidatie voordat een duidelijke uitbraak wordt bevestigd.`;
      default:
        return `FINN analyseert momenteel de realtime datastromen voor ${symbol} (${tf}). Alle achtergrondmodellen en risico-parameters draaien binnen normale drempelwaarden.`;
    }
  };

  useEffect(() => {
    const routePrefill = prefill;
    const routeContextMetric = contextMetric;
    const routeSymbol = symbol;

    if (routeSymbol && routeSymbol !== context.asset) {
      updateContext({ asset: routeSymbol, screen: 'FINN' });
    }
    const currentAsset = routeSymbol || context.asset;

    if (routeContextMetric) {
      const autoMessage = `Verklaar de ${getMetricTitle(contextMetric)} voor ${currentAsset}.`;
      setFeedItems((current) => [
        ...current,
        {
          id: `user-${Date.now()}`,
          type: 'message',
          role: 'user',
          text: autoMessage,
        },
      ]);
      
      // Simulate exact desktop behavior
      setTimeout(() => {
        setFeedItems((current) => [
          ...current,
          {
            id: `assistant-${Date.now()}`,
            type: 'message',
            role: 'assistant',
            text: getMetricAnalysisText(contextMetric, currentAsset, context.timeframe),
          },
        ]);
      }, 600);
    } else if (prefill) {
      setQuery(prefill);
      setSending(true);
      setTimeout(() => {
        handleSendPrefill(prefill);
      }, 500);
    }
  }, [prefill, contextMetric, symbol]);

  async function handleSendPrefill(textToSend: string) {
    if (sending) return;
    await triggerHaptic('selection');
    setSending(true);
    setChatError(null);
    setQuery('');

    try {
      const envelope = await assistantApi.chat(textToSend, apiContext);
      setFeedItems((current) => [...current, ...mapAssistantEnvelopeToFeedItems(envelope)]);
      if (envelope.draft) {
        setCurrentDraft(envelope.draft);
      }
      if (envelope.state && envelope.state.status === "collecting" && envelope.state.current_flow !== "none") {
        setActiveState(envelope.state);
      } else {
        setActiveState(null);
      }
    } catch (error) {
      setChatError(error instanceof Error ? error.message : 'FINN chat request failed');
      setFeedItems((current) => [
        ...current,
        {
          id: `error-${Date.now()}`,
          type: 'message',
          role: 'assistant',
          text: 'Kon FINN niet bereiken: ' + (error instanceof Error ? error.message : 'Unknown error'),
        },
      ]);
    } finally {
      setSending(false);
    }
  }

  const handleArchiveEvent = useCallback((eventId: number) => {
    setLocalEvents((prev) => prev.filter((e) => e.id !== eventId));
    apiClient.post(`/api/assistant/events/${eventId}/archive`).catch((err) => {
      console.error(`[FinnScreen] Failed to archive event ${eventId}:`, err);
    });
  }, []);

  const handleDiscussEvent = useCallback((event: MobileIntelligenceEvent) => {
    setQuery(`Bespreek live melding: "${event.title}" - ${event.description}`);
  }, []);

  const insightMatchesActiveAsset = insightResource.data?.context_detected?.symbol === context.asset;
  const activeInsight = insightMatchesActiveAsset ? insightResource.data : undefined;
  const activeBotDecision = mapMobileOverviewBotDecision(overviewResource.data);
  const activeAssetOverview = overviewResource.data?.watchlist.find((asset) => asset.symbol === context.asset);
  const activeBriefingText = buildActiveBriefingText(context.asset, activeInsight, activeAssetOverview);
  
  // Mapping helpers for sheets
  const activeSetup = { macro: 80, market: 75, tech: 60, setup: 70 };
  const mapDecisionState = (data: any, decision: any, colors: any) => ({ color: colors.accent, label: 'BULLISH' });

  async function handleSend() {
    const trimmed = query.trim();
    if (!trimmed || sending) return;

    await triggerHaptic('selection');
    setSending(true);
    setChatError(null);
    setFeedItems((current) => [
      ...current,
      {
        id: `user-${Date.now()}`,
        type: 'message',
        role: 'user',
        text: trimmed,
      },
    ]);
    setQuery('');

    try {
      const envelope = await assistantApi.chat(trimmed, apiContext);
      setFeedItems((current) => [...current, ...mapAssistantEnvelopeToFeedItems(envelope)]);
      if (envelope.draft) {
        setCurrentDraft(envelope.draft);
      }
      if (envelope.state && envelope.state.status === "collecting" && envelope.state.current_flow !== "none") {
        setActiveState(envelope.state);
      } else {
        setActiveState(null);
      }
    } catch (error) {
      setChatError(error instanceof Error ? error.message : 'FINN chat request failed');
      setFeedItems((current) => [
        ...current,
        {
          id: `error-${Date.now()}`,
          type: 'message',
          role: 'assistant',
          text: 'Kon FINN niet bereiken: ' + (error instanceof Error ? error.message : 'Unknown error'),
        },
      ]);
    } finally {
      setSending(false);
    }
  }

  const getFlowProgress = (state: any) => {
    if (!state || !state.current_flow || state.current_flow === "none") return null;
    
    const flowSlots: Record<string, string[]> = {
      user_onboarding: ["experience_level", "risk_profile", "investment_goals"],
      setup_creation: ["symbol", "setup_type", "market_condition", "name"],
      strategy_creation: ["symbol", "setup_type", "base_amount", "risk_profile"],
      bot_creation: ["name", "budget_total_eur", "budget_daily_limit_eur"],
    };

    const slots = flowSlots[state.current_flow] || [];
    if (slots.length === 0) return null;

    const filledSlots = slots.filter(k => state.slots && state.slots[k] !== undefined && state.slots[k] !== null && state.slots[k] !== "");
    
    let totalSlots = slots.length;
    const setupType = state.slots?.setup_type;
    if (state.current_flow === "strategy_creation" && setupType === "dca") {
      totalSlots = 3; // symbol, setup_type, base_amount
    }

    const percentage = Math.min(Math.round((filledSlots.length / totalSlots) * 100), 100);
    return {
      filled: filledSlots.length,
      total: totalSlots,
      percentage,
      flowLabel: state.current_flow.split("_").map((w: string) => w.charAt(0).toUpperCase() + w.slice(1)).join(" ")
    };
  };

  return (
    <View style={{ flex: 1, backgroundColor: colors.background }}>
      {isOverlay && (
        <View style={styles.overlayHeader}>
          <View style={styles.dragHandle} />
          <View style={styles.overlayHeaderRow}>
            <View style={{ gap: 4 }}>
              <Text style={[styles.overlayTitle, { color: colors.text }]}>FINN</Text>
              <View style={styles.headerSubRow}>
                <View style={styles.greenDot} />
                <Text style={[styles.headerContextText, { color: colors.textDim }]}>{finnContextLabel}</Text>
              </View>
            </View>
            <Pressable onPress={onClose} style={({ pressed }) => [styles.closeBtn, pressed && styles.pressed]}>
              <Text style={styles.closeBtnText}>SLUITEN</Text>
            </Pressable>
          </View>
        </View>
      )}
      <KeyboardAvoidingView
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
        style={{ flex: 1 }}
        keyboardVerticalOffset={Platform.OS === 'ios' ? (isOverlay ? 0 : 90) : 0}
      >
        <ScreenContainer
          contentInsetBottom={120}
          refreshing={overviewResource.refreshing || insightResource.refreshing}
          onRefresh={() => {
            overviewResource.refresh();
            insightResource.refresh();
          }}
        >
          <View style={styles.compactHeader}>
            <View style={styles.headerTitleRow}>
              <View style={styles.botIconBox}>
                <Text style={styles.botIconText}>🤖</Text>
              </View>
              <Text style={[styles.headerTitle, { color: colors.text }]}>FINN</Text>
              <View style={styles.headerBadge}>
                <Text style={styles.headerBadgeText}>{finnModeLabel.toUpperCase()}</Text>
              </View>
            </View>
            <View style={styles.headerSubRow}>
              <View style={styles.greenDot} />
              <Text style={[styles.headerContextText, { color: colors.textDim }]}>
                {finnContextLabel}
              </Text>
            </View>
          </View>

          {!isActionFlow && (
            <View style={styles.postureBox}>
              <View style={styles.hudSectionHeader}>
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
                  <Text style={styles.hudSectionIcon}>🛡️</Text>
                  <Text style={[styles.hudSectionTitle, { color: colors.text }]}>ACTIEVE BRIEFING</Text>
                </View>
                <View style={styles.posturePill}>
                  <Text style={styles.posturePillText}>Defensieve Posture</Text>
                </View>
              </View>
              <Text style={[styles.quoteText, { color: colors.text }]}>
                "{activeBriefingText}"
              </Text>
            </View>
          )}

          {!isActionFlow && (
            <MobileFINNFeed
              events={localEvents}
              onArchive={handleArchiveEvent}
              onDiscuss={handleDiscussEvent}
            />
          )}

          <AssistantFeedRenderer
            items={isActionFlow ? feedItems.filter(item => item.type !== 'reasoning') : feedItems}
            onActionPress={() => setSheet('confirm')}
            onDraftPress={() => setSheet('draft')}
            onRiskPress={() => setSheet('risk')}
          />

          {activeState && activeState.current_flow && activeState.current_flow !== "none" && (() => {
            const progress = getFlowProgress(activeState);
            if (!progress) return null;
            return (
              <View style={{ marginHorizontal: 16, marginBottom: 16, padding: 12, backgroundColor: '#F8FAFC', borderRadius: 12, borderLeftWidth: 4, borderLeftColor: '#2563EB' }}>
                <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
                  <Text style={{ fontSize: 11, fontWeight: '900', color: '#0F172A' }}>{progress.flowLabel.toUpperCase()}</Text>
                  <Text style={{ fontSize: 11, fontWeight: 'bold', color: '#2563EB' }}>{progress.percentage}%</Text>
                </View>
                <View style={{ height: 4, backgroundColor: '#E2E8F0', borderRadius: 2, overflow: 'hidden' }}>
                  <View style={{ height: 4, backgroundColor: '#2563EB', width: `${progress.percentage}%` }} />
                </View>
                <Text style={{ fontSize: 10, color: '#64748B', marginTop: 4 }}>
                  {progress.filled} van de {progress.total} stappen voltooid
                </Text>
              </View>
            );
          })()}

          {sending ? <LoadingSkeletonCard /> : null}

          {chatError ? (
            <InsightCard
              label="Chat error"
              title="FINN kon je vraag niet live beantwoorden."
              body={chatError}
              cta="Probeer opnieuw"
              tone="danger"
              onPress={() => setQuery(query || 'Vat mijn huidige context samen')}
            />
          ) : null}
        </ScreenContainer>

        <View style={[styles.composerWrap, { backgroundColor: appearance === 'light' ? '#FFFFFF' : '#020617F2', borderTopColor: colors.border }]}>
          <View style={[styles.composer, { backgroundColor: appearance === 'light' ? '#F1F5F9' : '#1E293B', borderColor: 'transparent' }]}>
            <TextInput
              multiline
              maxLength={240}
              onChangeText={setQuery}
              placeholder="Vraag Finn om context, risico of een volgende stap..."
              placeholderTextColor={colors.textDim}
              style={[styles.input, { color: colors.text }]}
              value={query}
            />
            <Pressable
              disabled={!query.trim() || sending}
              onPress={handleSend}
              style={({ pressed }) => [
                styles.sendButton,
                (!query.trim() || sending) && styles.sendDisabled,
                pressed && styles.pressed,
              ]}
            >
              {sending ? <Text style={styles.sendIcon}>⏳</Text> : <Text style={styles.sendIcon}>➤</Text>}
            </Pressable>
          </View>
        </View>
      </KeyboardAvoidingView>

      <BottomSheet visible={sheet === 'risk'} title="Laat Finn risico uitleggen" onClose={() => setSheet(null)}>
        <RiskExplanationSheetContent />
      </BottomSheet>
      <BottomSheet visible={sheet === 'confirm'} title="Review voorgestelde actie" onClose={() => setSheet(null)}>
        <ConfirmActionSheetContent onDone={() => setSheet(null)} />
      </BottomSheet>
      <BottomSheet visible={sheet === 'draft'} title="Review concept" onClose={() => setSheet(null)}>
        <DraftReviewSheetContent
          draft={currentDraft}
          onConfirm={async () => {
            setSheet(null);
            if (currentDraft && currentDraft.type === 'strategy') {
              try {
                const payload = currentDraft.payload;
                if (payload.strategy_id) {
                  await intelligenceApi.updateStrategy(Number(payload.strategy_id), payload);
                } else {
                  await intelligenceApi.createStrategy(payload);
                }
              } catch (error) {
                console.error('Failed to save strategy:', error);
              }
            }
          }}
        />
      </BottomSheet>
    </View>
  );
}

function buildActiveBriefingText(
  symbol: string,
  insight?: AssistantInsightResponse,
  asset?: MobileOverviewAsset,
) {
  const greeting = withoutSurroundingQuotes(insight?.greeting ?? '');
  const marketInsight = conciseInsightText(insight?.market_insight);
  const botInsight = conciseInsightText(insight?.bot_insight);

  if (greeting || marketInsight || botInsight) {
    return [greeting, marketInsight || botInsight]
      .filter(Boolean)
      .join(' ')
      .trim();
  }

  if (!asset) {
    return `Hoi Henk, ${symbol} is nu de actieve context. Ik laad de briefing opnieuw zodat mijn analyse op deze asset aansluit.`;
  }

  const score = Math.round((asset.macro_score + asset.market_score + asset.technical_score + asset.setup_score) / 4);
  const change =
    typeof asset.change_24h === 'number'
      ? `${asset.change_24h >= 0 ? '+' : ''}${asset.change_24h.toFixed(2)}%`
      : 'n/a';
  const risk =
    asset.setup_score < 45 || asset.technical_score < 45
      ? 'De structuur is nog zwak, dus ik zou wachten op bevestiging.'
      : 'De context is bruikbaar, maar ik blijf risico en setup-validiteit bewaken.';

  return `Hoi Henk, ${symbol} is nu actief. Composite score ${score}, 24h ${change}. ${risk}`;
}

function conciseInsightText(value?: Record<string, string> | null) {
  if (!value) return '';
  return Object.values(value)
    .filter(Boolean)
    .join(' ')
    .replace(/^Hello[^,.]*[,.]\s*/i, '')
    .split(/[.!?]/)
    .map((part) => part.trim())
    .filter(Boolean)
    .slice(0, 2)
    .join('. ');
}

function withoutSurroundingQuotes(value: string) {
  return value.trim().replace(/^["“]+|["”]+$/g, '');
}

const styles = StyleSheet.create({
  hudContainer: {
    gap: theme.spacing.lg,
    paddingVertical: theme.spacing.md,
  },
  quoteBox: {
    backgroundColor: theme.colors.accentSoft,
    borderColor: '#3B82F644',
    borderWidth: 1,
    borderRadius: theme.radius.lg,
    padding: theme.spacing.lg,
  },
  quoteLabel: {
    color: theme.colors.accent,
    fontSize: theme.typography.label,
    fontWeight: '900',
    letterSpacing: 1.5,
    textTransform: 'uppercase',
    marginBottom: theme.spacing.sm,
  },
  quoteText: {
    color: theme.colors.text,
    fontSize: 16,
    fontWeight: '600',
    fontStyle: 'italic',
    lineHeight: 24,
  },
  hudSection: {
    backgroundColor: theme.colors.surfaceMuted,
    borderColor: theme.colors.border,
    borderWidth: 1,
    borderRadius: theme.radius.lg,
    padding: theme.spacing.lg,
  },
  hudSectionHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: theme.spacing.sm,
  },
  hudSectionIcon: {
    fontSize: 14,
  },
  hudSectionTitle: {
    fontSize: 11,
    fontWeight: '900',
    letterSpacing: 1.5,
  },
  hudSectionBody: {
    color: theme.colors.textSoft,
    fontSize: 14,
    fontWeight: '600',
    lineHeight: 22,
    marginBottom: theme.spacing.md,
  },
  hudChip: {
    backgroundColor: theme.colors.surface,
    borderColor: theme.colors.borderStrong,
    borderWidth: 1,
    borderRadius: theme.radius.button,
    paddingVertical: 10,
    paddingHorizontal: theme.spacing.md,
    alignSelf: 'flex-start',
  },
  hudChipText: {
    color: theme.colors.accent,
    fontSize: 12,
    fontWeight: '800',
  },
  actionPillsContainer: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: theme.spacing.sm,
    marginTop: theme.spacing.sm,
  },
  actionPill: {
    backgroundColor: theme.colors.surface,
    borderColor: theme.colors.borderStrong,
    borderWidth: 1,
    borderRadius: theme.radius.button,
    paddingVertical: 10,
    paddingHorizontal: theme.spacing.md,
  },
  actionPillText: {
    color: theme.colors.text,
    fontSize: 12,
    fontWeight: '800',
  },
  compactHeader: {
    paddingVertical: theme.spacing.md,
    paddingHorizontal: theme.spacing.sm,
  },
  headerTitleRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: theme.spacing.sm,
  },
  botIconBox: {
    backgroundColor: theme.colors.accent,
    borderRadius: 8,
    width: 28,
    height: 28,
    justifyContent: 'center',
    alignItems: 'center',
  },
  botIconText: {
    fontSize: 16,
  },
  headerTitle: {
    fontSize: 20,
    fontWeight: '900',
    letterSpacing: -0.5,
  },
  headerBadge: {
    backgroundColor: '#EFF6FF',
    paddingHorizontal: 8,
    paddingVertical: 3,
    borderRadius: 6,
  },
  headerBadgeText: {
    color: '#3B82F6',
    fontSize: 10,
    fontWeight: '900',
    letterSpacing: 0.5,
  },
  headerSubRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    marginTop: 6,
    paddingLeft: 36, // align with text
  },
  greenDot: {
    width: 6,
    height: 6,
    borderRadius: 3,
    backgroundColor: theme.colors.success,
  },
  headerContextText: {
    fontSize: 11,
    fontWeight: '800',
    letterSpacing: 1,
  },
  postureBox: {
    paddingHorizontal: theme.spacing.sm,
    paddingVertical: theme.spacing.xs,
    marginBottom: theme.spacing.md,
  },
  posturePill: {
    backgroundColor: '#ECFDF5', // theme.colors.successSoft
    paddingHorizontal: 8,
    paddingVertical: 4,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: '#A7F3D0',
  },
  posturePillText: {
    color: '#059669', // theme.colors.success
    fontSize: 9,
    fontWeight: '900',
  },
  recentSection: {
    paddingHorizontal: theme.spacing.xs,
    gap: theme.spacing.sm,
  },
  recentHeader: {
    fontSize: theme.typography.label,
    fontWeight: '900',
    letterSpacing: 1.5,
    marginBottom: theme.spacing.xs,
  },
  recentRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: theme.spacing.md,
    borderRadius: theme.radius.lg,
    borderWidth: 1,
  },
  recentRowIcon: {
    fontSize: 16,
    opacity: 0.6,
  },
  recentTitle: {
    fontSize: 13,
    fontWeight: '700',
    flex: 1,
  },
  recentArrow: {
    fontSize: 14,
    fontWeight: '900',
  },
  composer: {
    alignItems: 'flex-end',
    borderRadius: 24,
    flexDirection: 'row',
    padding: 6,
    width: '100%',
  },
  composerWrap: {
    backgroundColor: `${theme.colors.background}F2`,
    borderTopColor: theme.colors.border,
    borderTopWidth: 1,
    bottom: 0,
    left: 0,
    padding: theme.spacing.md,
    position: 'absolute',
    right: 0,
    zIndex: 20,
  },
  input: {
    color: theme.colors.text,
    flex: 1,
    fontSize: 14,
    fontWeight: '500',
    maxHeight: 104,
    minHeight: 36,
    paddingHorizontal: theme.spacing.md,
    paddingVertical: 10,
  },
  keyboard: {
    backgroundColor: theme.colors.background,
    flex: 1,
  },
  pressed: {
    opacity: 0.84,
  },
  sendButton: {
    alignItems: 'center',
    backgroundColor: theme.colors.textDim,
    borderRadius: 20,
    height: 40,
    justifyContent: 'center',
    width: 40,
  },
  sendDisabled: {
    opacity: 0.3,
  },
  sendIcon: {
    color: theme.colors.white,
    fontSize: 16,
  },
  overlayHeader: {
    paddingHorizontal: theme.spacing.lg,
    paddingTop: theme.spacing.md,
    paddingBottom: theme.spacing.sm,
    borderBottomWidth: 1,
    borderBottomColor: theme.colors.border,
  },
  dragHandle: {
    width: 36,
    height: 4,
    backgroundColor: theme.colors.borderStrong,
    borderRadius: 2,
    alignSelf: 'center',
    marginBottom: theme.spacing.md,
  },
  overlayHeaderRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  overlayTitle: {
    fontSize: 18,
    fontWeight: '900',
    letterSpacing: 0.5,
  },
  closeBtn: {
    paddingVertical: 4,
    paddingHorizontal: 12,
    backgroundColor: theme.colors.surfaceMuted,
    borderRadius: theme.radius.pill,
  },
  closeBtnText: {
    color: theme.colors.textSoft,
    fontSize: 10,
    fontWeight: '900',
    letterSpacing: 1,
  },
});
