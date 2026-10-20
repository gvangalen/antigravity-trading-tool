import { useCallback, useMemo, useState, useEffect, useRef } from 'react';
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
import { BotDecisionCard } from '../components/cards/BotDecisionCard';
import { InsightCard } from '../components/cards/InsightCard';
import { LoadingSkeletonCard } from '../components/layout/LoadingSkeletonCard';
import { ScreenContainer } from '../components/layout/ScreenContainer';
import { BottomSheet } from '../components/sheets/BottomSheet';
import {
  ConfirmActionSheetContent,
  DraftReviewSheetContent,
  FinnV2ProposalReviewSheetContent,
  RiskExplanationSheetContent,
} from '../components/sheets/SheetContent';
import { theme } from '../constants/theme';
import { useApiResource } from '../hooks/useApiResource';
import { translate } from '../i18n';
import { mapAssistantEnvelopeToFeedItems } from '../services/assistantEnvelopeMapper';
import { canReviewDraft, draftOtherLabel, isDraftCorrectionIntent } from '../services/finnDraftConversation';
import {
  mapMobileOverviewBotDecision,
  mapMobileOverviewDecision,
  mapMobileOverviewMarket,
  mapMobileOverviewPortfolio,
  mapMobileOverviewPrompts,
} from '../services/dataMappers';
import { preferenceColors, useAppPreferences } from '../preferences/AppPreferencesProvider';
import { MobileOverviewAsset, MobileOverviewResponse, MobileCoachFeedItem, FinnV2ProposalSummary, assistantApi, mobileApi, coachFeedApi } from '../services/tradamindApi';
import { apiClient } from '../services/apiClient';
import { AssistantFeedItem, AssistantDraft } from '../types/assistant';
import { triggerHaptic } from '../utils/haptics';
import { useIntelligenceContext } from '../contexts/ActiveIntelligenceContext';
import { useAuth } from '../auth/AuthProvider';
import type { MainTabParamList } from '../navigation/MainTabNavigator';
import { trackAssistantEvent } from '../services/assistantAnalytics';

type SheetType = 'risk' | 'confirm' | 'draft' | 'proposal' | null;
const ACTIVE_FINN_SESSION_ID_KEY = 'active_finn_session_id';

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
  const meta = [lane, symbol || '', timeframe ? timeframe.toUpperCase() : ''].filter(Boolean);
  return meta.join(' · ');
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
  const { appearance, language } = useAppPreferences();
  const colors = preferenceColors(appearance);
  const [query, setQuery] = useState('');
  const composerRef = useRef<TextInput>(null);
  const [sending, setSending] = useState(false);
  const [chatError, setChatError] = useState<string | null>(null);
  const [sheet, setSheet] = useState<SheetType>(null);
  const [localEvents, setLocalEvents] = useState<MobileCoachFeedItem[]>([]);
  const [feedHistory, setFeedHistory] = useState(false);
  const [discussFeedItemId, setDiscussFeedItemId] = useState<string | null>(null);
  const [feedItems, setFeedItems] = useState<AssistantFeedItem[]>([]);
  const [currentDraft, setCurrentDraft] = useState<AssistantDraft | null>(null);
  const [currentProposal, setCurrentProposal] = useState<FinnV2ProposalSummary | null>(null);
  const [activeState, setActiveState] = useState<any>(null);
  const [draftError, setDraftError] = useState<string | null>(null);
  const [proposalError, setProposalError] = useState<string | null>(null);
  const [proposalSaving, setProposalSaving] = useState(false);
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [availableSessions, setAvailableSessions] = useState<Array<{ id: string; title: string; updated_at: string }>>([]);
  const isActionFlow = source?.startsWith('strategy-') || source?.startsWith('setup-') || source?.startsWith('bot-');

  const { context, updateContext } = useIntelligenceContext();
  const apiContext = useMemo(() => ({
    page_type: 'FINN',
    locale: language,
    symbol: context.asset,
    timeframe: context.timeframe,
    feed_item_id: discussFeedItemId,
  }), [context.asset, context.timeframe, discussFeedItemId, language]);
  const finnContextLabel = useMemo(
    () => formatFinnContextLabel(context.screen || context.page_type || context.page || 'FINN', context.asset, context.timeframe),
    [context.asset, context.page_type, context.screen, context.timeframe, context.page]
  );
  const finnModeLabel = useMemo(() => deriveFinnModeLabel(source, activeState), [source, activeState]);

  const fetchOverview = useCallback(() => mobileApi.overview(), []);
  const overviewResource = useApiResource<MobileOverviewResponse | undefined>({
    fallbackData: undefined,
    fetcher: fetchOverview,
  });
  useEffect(() => {
    trackAssistantEvent({
      event_name: 'screen_view',
      page: isOverlay ? 'finn_overlay' : 'finn',
      flow_type: source || 'finn',
      asset: symbol || context.asset || null,
    });
  }, [context.asset, isOverlay, source, symbol]);
  const loadCoachFeed = useCallback(async () => {
    try {
      setLocalEvents(await coachFeedApi.list(feedHistory));
    } catch (error) {
      console.warn('FINN feed temporarily unavailable', error);
    }
  }, [feedHistory]);
  useEffect(() => {
    void loadCoachFeed();
  }, [loadCoachFeed]);

  const persistActiveSessionId = useCallback(async (sessionId: string | null) => {
    if (!sessionId) return;
    setActiveSessionId(sessionId);
    try {
      await assistantApi.updatePreferences({
        [ACTIVE_FINN_SESSION_ID_KEY]: sessionId,
      });
    } catch (error) {
      console.warn('Failed to persist FINN session id', error);
    }
  }, []);

  useEffect(() => {
    let cancelled = false;

    async function loadActiveSession() {
      try {
        const preferencesResponse = await assistantApi.preferences();
        const preferredSessionId = normalizeAssistantSessionId(
          preferencesResponse?.preferences?.[ACTIVE_FINN_SESSION_ID_KEY],
        );
        const sessions = await assistantApi.v2Conversations();
        if (!cancelled) {
          setAvailableSessions(
            Array.isArray(sessions)
              ? sessions.map((session) => ({
                  id: session.id,
                  title: session.title || 'FINN gesprek',
                  updated_at: session.updated_at,
                }))
              : [],
          );
        }
        const fallbackSessionId =
          (preferredSessionId?.startsWith('finn-v2-conv-') ? preferredSessionId : null) ||
          normalizeAssistantSessionId(sessions?.[0]?.id);

        if (!fallbackSessionId) return;

        const detail = await assistantApi.v2ConversationDetail(fallbackSessionId);
        if (cancelled) return;

        setActiveSessionId(fallbackSessionId);
        setFeedItems(mapSessionMessagesToFeedItems(detail?.messages));
      } catch (error) {
        if (!cancelled) {
          console.warn('Failed to load FINN session history', error);
        }
      }
    }

    loadActiveSession();
    return () => {
      cancelled = true;
    };
  }, []);

  const switchToSession = useCallback(async (sessionId: string) => {
    const normalized = normalizeAssistantSessionId(sessionId);
    if (!normalized) return;

    try {
      const detail = await assistantApi.v2ConversationDetail(normalized);
      await persistActiveSessionId(normalized);
      setCurrentDraft(null);
      setCurrentProposal(null);
      setActiveState(null);
      setFeedItems(mapSessionMessagesToFeedItems(detail?.messages));
    } catch (error) {
      console.warn('Failed to switch FINN session', error);
    }
  }, [persistActiveSessionId]);

  const startNewConversation = useCallback(async () => {
    setActiveSessionId(null);
    setCurrentDraft(null);
    setCurrentProposal(null);
    setActiveState(null);
    setChatError(null);
    setFeedItems([]);
    try {
      await assistantApi.updatePreferences({
        [ACTIVE_FINN_SESSION_ID_KEY]: null,
      });
    } catch (error) {
      console.warn('Failed to reset active FINN session id', error);
    }
  }, []);

  const getMetricTitle = (metric: string) => {
    const titles: Record<string, string> = {
      transition_risk: 'Transition Risk Analysis',
      setup_quality: 'Setupmatch',
      market_pressure: 'Market Pressure Analysis',
      structural_cycle: 'Structural Cycle Phase',
      position_size: 'Position Size Telemetry',
      trend_strength: 'Trend Strength Evaluation',
    };
    return titles[metric] || 'Contextual Intelligence';
  };

  const getMetricAnalysisText = (metric: string, symbol = '', tf = '') => {
    const assetLabel = symbol || 'deze asset';
    const timeframeLabel = tf || 'dit timeframe';
    switch (metric) {
      case 'transition_risk':
        return `FINN detecteert toenemende regime-instabiliteit door afnemende trend strength en hogere volatiliteit voor ${assetLabel}. Nieuwe agressieve entries worden momenteel niet aanbevolen op ${timeframeLabel}.`;
      case 'setup_quality':
        return `De setupmatch laat zien hoe dicht de actuele samengestelde benchmarkscore bij de opgeslagen voorwaarde voor ${assetLabel} ligt. Alleen de matchstatus bepaalt of de setup mag meedoen; de strategie en veiligheidslimieten bepalen een eventuele trade.`;
      case 'market_pressure':
        return `De verkoopdruk neemt toe in de orderboeken van ${assetLabel} met dalend volume op stijgingen. FINN adviseert strakkere stop-loss niveaus op ${timeframeLabel}.`;
      case 'structural_cycle':
        return `De macro-structuur van ${assetLabel} bevindt zich in een vroege herstelfase (recovery). Accumulatie op belangrijke steunniveaus wordt ondersteund door stabiele kapitaalinstroom.`;
      case 'position_size':
        return `Huidige aanbevolen positiegrootte voor ${assetLabel} is defensief (50%). Verlaag actieve blootstelling bij verhoogde marktvolatiliteit om kapitaalbehoud te garanderen.`;
      case 'trend_strength':
        return `De trend strength toont zwakke momentum-indicatoren op korte termijn voor ${assetLabel}. Verwacht verdere consolidatie voordat een duidelijke uitbraak wordt bevestigd.`;
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
      const envelope = await assistantApi.chat(textToSend, apiContext, undefined, activeSessionId || 'new');
      setDiscussFeedItemId(null);
      await persistActiveSessionId(normalizeAssistantSessionId(envelope?.session_id));
      setFeedItems((current) => [...current, ...mapAssistantEnvelopeToFeedItems(envelope, language)]);
      if (canReviewDraft(envelope) && envelope.draft) {
        setCurrentDraft(envelope.draft);
      } else {
        setCurrentDraft(null);
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

  function openDraftSheet() {
    setDraftError(null);
    setSheet('draft');
  }

  async function openProposalSheet(proposalId: string) {
    setProposalError(null);
    setCurrentProposal(null);
    setSheet('proposal');
    try {
      const proposal = await assistantApi.v2Proposal(proposalId);
      if (proposal.proposal_id !== proposalId) throw new Error('Voorstelidentiteit klopt niet.');
      setCurrentProposal(proposal);
    } catch (error) {
      setProposalError(error instanceof Error ? error.message : 'Voorstel kon niet worden gelezen.');
    }
  }

  async function confirmProposal() {
    if (!currentProposal || proposalSaving) return;
    setProposalSaving(true);
    setProposalError(null);
    try {
      const result = await assistantApi.confirmAndExecuteV2Proposal(
        currentProposal.proposal_id, currentProposal.review_target_name,
      );
      if (!['succeeded', 'already_executed'].includes(result.status)) {
        throw new Error('FINN kon de wijziging niet bevestigen. Controleer je plan voordat je opnieuw probeert.');
      }
      await Promise.allSettled([overviewResource.refresh(), loadCoachFeed()]);
      setFeedItems((current) => current.filter((item) =>
        item.type !== 'v2_proposal' || item.proposalId !== currentProposal.proposal_id,
      ).concat({
        id: `proposal-result-${currentProposal.proposal_id}`,
        type: 'message', role: 'assistant', text: 'Je bevestigde wijziging is opgeslagen.',
      }));
      setCurrentProposal(null);
      setSheet(null);
      await triggerHaptic('success');
    } catch (error) {
      setProposalError(error instanceof Error ? error.message : 'Bevestigen is mislukt.');
    } finally {
      setProposalSaving(false);
    }
  }

  const handleArchiveEvent = useCallback((eventId: string) => {
    void coachFeedApi.mark(eventId, 'handled').then(loadCoachFeed).catch((err) => {
      console.error(`[FinnScreen] Failed to handle feed item ${eventId}:`, err);
    });
  }, [loadCoachFeed]);

  const handleDiscussEvent = useCallback((event: MobileCoachFeedItem) => {
    setDiscussFeedItemId(event.id);
    setQuery(translate(language, 'finn.feedDiscussQuery'));
    void coachFeedApi.mark(event.id, 'read').then(loadCoachFeed).catch(() => {});
  }, [language, loadCoachFeed]);

  const activeBotDecision = mapMobileOverviewBotDecision(overviewResource.data);
  const activeAssetOverview = overviewResource.data?.watchlist.find((asset) => asset.symbol === context.asset);
  const starterPrompts = useMemo(
    () => [
      `Vat ${context.asset} vandaag samen`,
      `Wat is nu het grootste risico voor ${context.asset}?`,
      `Welke workspace moet ik nu openen voor ${context.asset}?`,
    ],
    [context.asset],
  );
  
  // Mapping helpers for sheets
  const activeSetup = { macro: 80, market: 75, tech: 60, setup: 70 };
  const mapDecisionState = (data: any, decision: any, colors: any) => ({ color: colors.accent, label: 'BULLISH' });

  async function handleSend(directText?: string) {
    const trimmed = (directText ?? query).trim();
    if (!trimmed || sending) return;

    await triggerHaptic('selection');
    setSending(true);
    if (isDraftCorrectionIntent(trimmed)) {
      // A superseded proposal must not remain available if the replacement
      // turn fails before a new review card arrives.
      setCurrentDraft(null);
      setCurrentProposal(null);
      setSheet(null);
    }
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
      const envelope = await assistantApi.chat(trimmed, apiContext, undefined, activeSessionId || 'new');
      setDiscussFeedItemId(null);
      await persistActiveSessionId(normalizeAssistantSessionId(envelope?.session_id));
      setFeedItems((current) => [...current, ...mapAssistantEnvelopeToFeedItems(envelope, language)]);
      if (canReviewDraft(envelope) && envelope.draft) {
        setCurrentDraft(envelope.draft);
      } else {
        setCurrentDraft(null);
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
              <Text style={styles.closeBtnText}>{translate(language, 'finn.close').toUpperCase()}</Text>
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
          refreshing={overviewResource.refreshing}
          onRefresh={() => {
            overviewResource.refresh();
            void loadCoachFeed();
          }}
        >
          <View style={[styles.workspaceHero, { backgroundColor: colors.surface, borderColor: colors.border }]}>
            <View style={styles.compactHeader}>
              <View style={styles.headerTitleRow}>
                <View style={styles.botIconBox}>
                  <Text style={styles.botIconLetter}>F</Text>
                </View>
                <View style={styles.headerCopy}>
                  <View style={styles.headerTitleLine}>
                    <Text style={[styles.headerEyebrow, { color: colors.textDim }]}>FINN</Text>
                    <View style={styles.headerBadge}>
                      <Text style={styles.headerBadgeText}>{finnModeLabel.toUpperCase()}</Text>
                    </View>
                  </View>
                  <Text style={[styles.headerTitle, { color: colors.text }]}>{translate(language, 'finn.askTitle')}</Text>
                </View>
              </View>
              <View style={styles.headerSubRow}>
                <View style={styles.greenDot} />
                <Text style={[styles.headerContextText, { color: colors.textDim }]}>{finnContextLabel}</Text>
              </View>
              <View style={styles.heroMetaRow}>
                <View style={[styles.heroMetaCard, { backgroundColor: colors.backgroundSoft, borderColor: colors.border }]}>
                  <Text style={styles.heroMetaLabel}>{translate(language, 'finn.contextLabel')}</Text>
                  <Text style={[styles.heroMetaValue, { color: colors.text }]}>{context.asset}</Text>
                </View>
                <View style={[styles.heroMetaCard, { backgroundColor: colors.backgroundSoft, borderColor: colors.border }]}>
                  <Text style={styles.heroMetaLabel}>{translate(language, 'finn.workflowLabel')}</Text>
                  <Text style={[styles.heroMetaValue, { color: colors.text }]}>{context.screen || 'FINN'}</Text>
                </View>
                <View style={[styles.heroMetaCard, { backgroundColor: colors.backgroundSoft, borderColor: colors.border }]}>
                  <Text style={styles.heroMetaLabel}>{translate(language, 'finn.modeLabel')}</Text>
                  <Text style={[styles.heroMetaValue, { color: colors.text }]}>{finnModeLabel}</Text>
                </View>
              </View>
              <View style={styles.sessionActionsRow}>
                <Pressable
                  onPress={startNewConversation}
                  style={[styles.sessionActionButton, { borderColor: colors.border, backgroundColor: colors.backgroundSoft }]}
                >
                  <Text style={[styles.sessionActionText, { color: colors.text }]}>Nieuw gesprek</Text>
                </Pressable>
              </View>
            </View>
          </View>

          {availableSessions.length > 0 ? (
            <View style={styles.recentSection}>
              <Text style={[styles.recentHeader, { color: colors.textDim }]}>Recente gesprekken</Text>
              {availableSessions.slice(0, 3).map((session) => {
                const active = session.id === activeSessionId;
                return (
                  <Pressable
                    key={session.id}
                    onPress={() => switchToSession(session.id)}
                    style={[
                      styles.recentRow,
                      {
                        borderColor: active ? colors.accent : colors.border,
                        backgroundColor: active ? colors.backgroundSoft : colors.surface,
                      },
                    ]}
                  >
                    <Text numberOfLines={1} style={[styles.recentTitle, { color: colors.text }]}>{session.title}</Text>
                    <Text style={[styles.recentArrow, { color: colors.textDim }]}>{formatSessionTimestamp(session.updated_at)}</Text>
                  </Pressable>
                );
              })}
            </View>
          ) : null}

          {!isActionFlow && (
            <MobileFINNFeed
              events={feedHistory ? localEvents : localEvents.slice(0, 3)}
              onArchive={handleArchiveEvent}
              onDiscuss={handleDiscussEvent}
              history={feedHistory}
              onToggleHistory={() => setFeedHistory((current) => !current)}
              language={language}
            />
          )}

          <AssistantFeedRenderer
            language={language}
            items={isActionFlow ? feedItems.filter(item => item.type !== 'reasoning') : feedItems}
            onActionPress={() => setSheet('confirm')}
            onDraftPress={openDraftSheet}
            onProposalPress={(proposalId) => { void openProposalSheet(proposalId); }}
            onRiskPress={() => setSheet('risk')}
            onChoicePress={(reply) => { if (!sending) void handleSend(reply); }}
            onOtherPress={() => composerRef.current?.focus()}
            otherLabel={draftOtherLabel(language)}
          />

          {!sending && feedItems.length === 0 ? (
            <View style={styles.promptSection}>
              <Text style={[styles.promptTitle, { color: colors.text }]}>{translate(language, 'finn.startFromWorkspace')}</Text>
              <SuggestedPromptChips prompts={starterPrompts} onSelect={setQuery} />
            </View>
          ) : null}

          {sending ? <LoadingSkeletonCard /> : null}

          {chatError ? (
            <InsightCard
              label={translate(language, 'finn.chatErrorLabel')}
              title={translate(language, 'finn.chatErrorTitle')}
              body={chatError}
              cta={translate(language, 'finn.retry')}
              tone="danger"
              onPress={() => setQuery(query || translate(language, 'finn.summarizeCurrentContext'))}
            />
          ) : null}
        </ScreenContainer>

        <View style={[styles.composerWrap, { backgroundColor: appearance === 'light' ? '#FFFFFF' : '#020617F2', borderTopColor: colors.border }]}>
          <View style={[styles.composer, { backgroundColor: appearance === 'light' ? '#F1F5F9' : '#1E293B', borderColor: 'transparent' }]}>
            <TextInput
              ref={composerRef}
              multiline
              maxLength={240}
              onChangeText={setQuery}
              placeholder={translate(language, 'finn.askPlaceholder')}
              placeholderTextColor={colors.textDim}
              style={[styles.input, { color: colors.text }]}
              value={query}
            />
            <Pressable
              disabled={!query.trim() || sending}
              onPress={() => void handleSend()}
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
      <BottomSheet
        visible={sheet === 'draft'}
        title="Review concept"
        onClose={() => {
          setDraftError(null);
          setSheet(null);
        }}
      >
        <DraftReviewSheetContent
          draft={currentDraft}
          error={draftError}
        />
      </BottomSheet>
      <BottomSheet
        visible={sheet === 'proposal'}
        title={translate(language, 'finn.proposalReview')}
        onClose={() => { if (!proposalSaving) setSheet(null); }}
        allowClose={!proposalSaving}
      >
        <FinnV2ProposalReviewSheetContent
          language={language}
          proposal={currentProposal}
          error={proposalError}
          saving={proposalSaving}
          onConfirm={confirmProposal}
        />
      </BottomSheet>
    </View>
  );
}

function normalizeAssistantSessionId(value: unknown): string | null {
  if (typeof value !== 'string') return null;
  const normalized = value.trim();
  return normalized ? normalized : null;
}

function mapSessionMessagesToFeedItems(messages: Array<{
  role: 'assistant' | 'user'; content: string;
  pending_proposal?: { proposal_id: string };
}> = []): AssistantFeedItem[] {
  return messages.flatMap((message, index): AssistantFeedItem[] => {
    if (typeof message?.content !== 'string' || !message.content.trim()) return [];
    const items: AssistantFeedItem[] = [{
      id: `session-${index}`, type: 'message', role: message.role, text: message.content,
    }];
    const proposalId = message.pending_proposal?.proposal_id;
    if (message.role === 'assistant' && proposalId) {
      items.push({ id: `proposal-${proposalId}`, type: 'v2_proposal', proposalId });
    }
    return items;
  });
}

function formatSessionTimestamp(value?: string) {
  if (!value) return '';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '';
  return `${String(date.getDate()).padStart(2, '0')}-${String(date.getMonth() + 1).padStart(2, '0')} ${String(date.getHours()).padStart(2, '0')}:${String(date.getMinutes()).padStart(2, '0')}`;
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
    gap: theme.spacing.md,
  },
  headerCopy: {
    flex: 1,
    gap: 2,
  },
  headerEyebrow: {
    fontSize: 10,
    fontWeight: '900',
    letterSpacing: 1.2,
    textTransform: 'uppercase',
  },
  headerTitleRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: theme.spacing.sm,
  },
  botIconBox: {
    backgroundColor: theme.colors.accent,
    borderRadius: 14,
    width: 40,
    height: 40,
    justifyContent: 'center',
    alignItems: 'center',
  },
  botIconLetter: {
    color: '#ffffff',
    fontSize: 19,
    fontWeight: '900',
  },
  headerTitle: {
    fontSize: 20,
    fontWeight: '900',
    letterSpacing: -0.5,
  },
  headerTitleLine: {
    alignItems: 'center',
    flexDirection: 'row',
    gap: theme.spacing.sm,
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
  },
  heroMetaCard: {
    borderRadius: theme.radius.lg,
    borderWidth: 1,
    flex: 1,
    gap: 4,
    paddingHorizontal: theme.spacing.md,
    paddingVertical: theme.spacing.sm,
  },
  heroMetaLabel: {
    color: theme.colors.textDim,
    fontSize: 10,
    fontWeight: '900',
    letterSpacing: 0.9,
    textTransform: 'uppercase',
  },
  heroMetaRow: {
    flexDirection: 'row',
    gap: theme.spacing.sm,
  },
  sessionActionsRow: {
    flexDirection: 'row',
    gap: theme.spacing.sm,
  },
  sessionActionButton: {
    borderRadius: theme.radius.button,
    borderWidth: 1,
    paddingHorizontal: theme.spacing.md,
    paddingVertical: 8,
  },
  sessionActionText: {
    fontSize: 11,
    fontWeight: '800',
  },
  heroMetaValue: {
    fontSize: 13,
    fontWeight: '800',
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
    borderRadius: theme.radius.xl,
    borderWidth: 1,
    marginHorizontal: theme.spacing.xs,
    marginBottom: theme.spacing.md,
    paddingHorizontal: theme.spacing.md,
    paddingVertical: theme.spacing.md,
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
  promptSection: {
    gap: theme.spacing.sm,
    marginBottom: theme.spacing.md,
  },
  promptTitle: {
    fontSize: 13,
    fontWeight: '800',
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
  workspaceHero: {
    borderRadius: theme.radius.xl,
    borderWidth: 1,
    marginBottom: theme.spacing.md,
    paddingHorizontal: theme.spacing.md,
    paddingVertical: theme.spacing.md,
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
