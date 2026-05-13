import { useCallback, useState, useEffect } from 'react';
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
import { mockAssistantEnvelope } from '../data/mockAssistantEnvelope';
import { mockBriefing } from '../data/mockFoundation';
import { useApiResource } from '../hooks/useApiResource';
import { mapAssistantEnvelopeToFeedItems } from '../services/assistantEnvelopeMapper';
import {
  mapAssistantInsightCard,
  mapAssistantInsightDetails,
  mapMobileOverviewBotDecision,
  mapMobileOverviewBriefing,
  mapMobileOverviewDecision,
  mapMobileOverviewMarket,
  mapMobileOverviewPortfolio,
  mapMobileOverviewPrompts,
} from '../services/dataMappers';
import { AssistantInsightResponse, MobileOverviewResponse, MobileIntelligenceEvent, assistantApi, mobileApi } from '../services/tradamindApi';
import { apiClient } from '../services/apiClient';
import { AssistantFeedItem } from '../types/assistant';
import { triggerHaptic } from '../utils/haptics';
import { useAuth } from '../auth/AuthProvider';

type SheetType = 'risk' | 'confirm' | 'draft' | null;

export function FinnScreen() {
  const { logout, user } = useAuth();
  const [query, setQuery] = useState('');
  const [sending, setSending] = useState(false);
  const [chatError, setChatError] = useState<string | null>(null);
  const [sheet, setSheet] = useState<SheetType>(null);
  const [localEvents, setLocalEvents] = useState<MobileIntelligenceEvent[]>([]);
  const [feedItems, setFeedItems] = useState<AssistantFeedItem[]>(() => [
    {
      id: 'intro-1',
      type: 'message',
      role: 'assistant',
      text: 'Ik hou de briefing bovenaan vast. Stel je vraag, of kies een prompt om een card-context te openen.',
    },
  ]);

  const context = {
    page_type: 'FINN',
    symbol: mockBriefing.asset,
    timeframe: 'Daily',
  };

  const fetchOverview = useCallback(() => mobileApi.overview(), []);
  const fetchInsight = useCallback(() => assistantApi.insight(context), []);
  const overviewResource = useApiResource<MobileOverviewResponse | undefined>({
    fallbackData: undefined,
    fetcher: fetchOverview,
  });
  const insightResource = useApiResource<AssistantInsightResponse | undefined>({
    fallbackData: undefined,
    fetcher: fetchInsight,
  });
  useEffect(() => {
    if (overviewResource.data?.intelligence_events) {
      setLocalEvents(overviewResource.data.intelligence_events);
    }
  }, [overviewResource.data?.intelligence_events]);

  const handleArchiveEvent = useCallback((eventId: number) => {
    // Optimistic UI updates - remove instantly from view
    setLocalEvents((prev) => prev.filter((e) => e.id !== eventId));
    
    // Background dispatch
    apiClient.post(`/api/assistant/events/${eventId}/archive`).catch((err) => {
      console.error(`[FinnScreen] Failed to archive event ${eventId}:`, err);
    });
  }, []);

  const handleDiscussEvent = useCallback((event: MobileIntelligenceEvent) => {
    // Automatically set query content to trigger an instant chat discussion
    setQuery(`Bespreek live melding: "${event.title}" - ${event.description}`);
  }, []);
  const briefing = mapMobileOverviewBriefing(overviewResource.data, insightResource.data);
  const masterDecision = mapMobileOverviewDecision(overviewResource.data);
  const marketSnapshot = mapMobileOverviewMarket(overviewResource.data, briefing.asset);
  const botDecision = mapMobileOverviewBotDecision(overviewResource.data);
  const portfolio = mapMobileOverviewPortfolio(overviewResource.data);
  const prompts = mapMobileOverviewPrompts(overviewResource.data);
  const watchlistSummary =
    overviewResource.data?.watchlist
      .slice(0, 3)
      .map((asset) => {
        const score = Math.round(
          (asset.macro_score + asset.market_score + asset.technical_score + asset.setup_score) / 4,
        );
        const change =
          typeof asset.change_24h === 'number'
            ? `${asset.change_24h >= 0 ? '+' : ''}${asset.change_24h.toFixed(2)}%`
            : 'n/a';
        return `${asset.symbol}: score ${score}, 24h ${change}`;
      })
      .join(' · ') || '';
  const insightCard = mapAssistantInsightCard(insightResource.data);
  const insightDetails = mapAssistantInsightDetails(insightResource.data);

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
      const envelope = await assistantApi.chat(trimmed, context);
      setFeedItems((current) => [...current, ...mapAssistantEnvelopeToFeedItems(envelope)]);
    } catch (error) {
      setChatError(error instanceof Error ? error.message : 'FINN chat request failed');
      setFeedItems((current) => [
        ...current,
        ...mapAssistantEnvelopeToFeedItems({
          ...mockAssistantEnvelope,
          trace_id: `fallback-${Date.now()}`,
          response:
            'Ik kan de backend nu niet bereiken of de mobiele sessie is nog niet ingelogd. Ik toon tijdelijk een stale voorbeeld-envelope zodat de flow testbaar blijft.',
        }),
      ]);
    } finally {
      setSending(false);
    }
  }

  return (
    <KeyboardAvoidingView
      behavior={Platform.OS === 'ios' ? 'padding' : undefined}
      style={styles.keyboard}
    >
      <ScreenContainer
        contentInsetBottom={260}
        refreshing={overviewResource.refreshing || insightResource.refreshing}
        onRefresh={() => {
          overviewResource.refresh();
          insightResource.refresh();
        }}
      >
        <AssetContextHeader
          asset={briefing.asset}
          context="FINN operating layer"
          updatedAt={overviewResource.updatedAt || insightResource.updatedAt}
        />
        <SectionHeader
          label="FINN"
          title={`AI trading chief of staff${user?.first_name ? ` voor ${user.first_name}` : ''}`}
          description="Live mobile overview, coaching, setup uitleg, risk warnings and desktop continuation in one assistant-first home."
        />

        <MobileFINNFeed
          events={localEvents}
          onArchive={handleArchiveEvent}
          onDiscuss={handleDiscussEvent}
        />

        {overviewResource.loading ? (
          <LoadingSkeletonCard />
        ) : (
          <AssistantBriefingCard
            status={briefing.status}
            summary={briefing.summary}
            risk={briefing.risk}
            nextAction={briefing.nextAction}
          />
        )}

        {overviewResource.isStale ? (
          <InsightCard
            label="Stale fallback"
            title="FINN gebruikt tijdelijk fallback context voor de mobile overview."
            body="De FINN mobile-bundel kon niet live laden. Chat en mock fallback blijven beschikbaar, maar portfolio/watchlist/bot context kan stale zijn."
            cta="Retry mobile overview"
            onPress={overviewResource.refresh}
            tone="warning"
          />
        ) : null}

        <SuggestedPromptChips prompts={prompts} onSelect={setQuery} />

        <MasterDecisionCard
          score={masterDecision.score}
          state={masterDecision.state}
          reason={masterDecision.reason}
        />

        <MarketSnapshotCard
          symbol={marketSnapshot.symbol}
          price={marketSnapshot.price}
          change24h={marketSnapshot.change24h}
          volume={marketSnapshot.volume}
          interpretation={marketSnapshot.interpretation}
          tone={marketSnapshot.tone}
        />

        <InsightCard
          label="FINN insight"
          title={insightCard.title}
          body={insightCard.body}
          cta="Open context"
          tone="accent"
        />

        <BotDecisionCard
          action={botDecision.action}
          amount={botDecision.amount}
          botName={botDecision.botName}
          confidence={botDecision.confidence}
          guardrail={botDecision.guardrail}
          reason={botDecision.reason}
          tone={botDecision.tone}
          onConfirm={() => setSheet('confirm')}
        />

        <InsightCard
          label="Portfolio context"
          title={portfolio.totalValue}
          body={`${portfolio.pnl}. ${portfolio.exposure}. ${portfolio.botStatus}.`}
          tone={overviewResource.data && overviewResource.data.portfolio.total_profit_pct < 0 ? 'warning' : 'accent'}
        />

        {watchlistSummary ? (
          <InsightCard
            label="Watchlist context"
            title="FINN heeft de mobile watchlist geladen"
            body={watchlistSummary}
            tone="neutral"
          />
        ) : null}

        <ActionCard
          title="Continue on desktop"
          reason="FINN heeft je authenticated mobile context geladen. Je kunt dezelfde analyse op desktop verder uitwerken zonder mobile execution."
          impact="Mobile blijft read-only: briefing, chat, risk context en voorbereiden. Desktop blijft de plek voor volledige configuratie en uitvoering."
          primaryAction="Ask FINN"
          secondaryAction="Refresh"
          tone="accent"
          onPrimary={() => setQuery('Maak een korte desktop handoff van mijn huidige FINN context')}
          onSecondary={() => {
            overviewResource.refresh();
            insightResource.refresh();
          }}
        />

        {insightDetails.market ? (
          <InsightCard
            label="Market insight"
            title="Market context from backend"
            body={insightDetails.market}
            tone="accent"
          />
        ) : null}

        {insightDetails.bot ? (
          <InsightCard
            label="Bot insight"
            title="Bot context from backend"
            body={insightDetails.bot}
            tone="warning"
          />
        ) : null}

        {insightResource.error ? (
          <InsightCard
            label="FINN error"
            title="AI insight kon niet live laden."
            body={insightResource.error.message}
            cta="Retry"
            tone="danger"
            onPress={insightResource.refresh}
          />
        ) : null}

        {overviewResource.error ? (
          <InsightCard
            label="Mobile API error"
            title="FINN mobile overview kon niet live laden."
            body={overviewResource.error.message}
            cta="Retry overview"
            tone="danger"
            onPress={overviewResource.refresh}
          />
        ) : null}

        <InsightCard
          label="Session"
          title={`Ingelogd als ${user?.email ?? 'mobile user'}`}
          body="Mobile gebruikt nu bearer auth met secure token storage. De backend blijft tegelijk web-cookie compatible."
          cta="Log out"
          tone="neutral"
          onPress={logout}
        />

        <AssistantFeedRenderer
          items={feedItems}
          onActionPress={() => setSheet('confirm')}
          onDraftPress={() => setSheet('draft')}
          onRiskPress={() => setSheet('risk')}
        />

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

      <View style={styles.composerWrap}>
        <View style={styles.composer}>
          <TextInput
            multiline
            maxLength={240}
            onChangeText={setQuery}
            placeholder="Vraag iets aan Tradamind..."
            placeholderTextColor={theme.colors.textDim}
            style={styles.input}
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
            <Text style={styles.sendText}>{sending ? '...' : 'Send'}</Text>
          </Pressable>
        </View>
      </View>

      <BottomSheet visible={sheet === 'risk'} title="Risk explanation" onClose={() => setSheet(null)}>
        <RiskExplanationSheetContent />
      </BottomSheet>
      <BottomSheet visible={sheet === 'confirm'} title="Confirm action pattern" onClose={() => setSheet(null)}>
        <ConfirmActionSheetContent onDone={() => setSheet(null)} />
      </BottomSheet>
      <BottomSheet visible={sheet === 'draft'} title="Draft review" onClose={() => setSheet(null)}>
        <DraftReviewSheetContent />
      </BottomSheet>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  composer: {
    alignItems: 'flex-end',
    backgroundColor: theme.colors.surface,
    borderColor: theme.colors.border,
    borderRadius: theme.radius.xl,
    borderWidth: 1,
    flexDirection: 'row',
    gap: theme.spacing.sm,
    padding: theme.spacing.sm,
    width: '100%',
  },
  composerWrap: {
    backgroundColor: `${theme.colors.background}F2`,
    borderTopColor: theme.colors.border,
    borderTopWidth: 1,
    bottom: 84,
    left: 0,
    padding: theme.spacing.md,
    position: 'absolute',
    right: 0,
    zIndex: 20,
  },
  input: {
    color: theme.colors.text,
    flex: 1,
    fontSize: theme.typography.body,
    fontWeight: '600',
    maxHeight: 104,
    minHeight: 42,
    paddingHorizontal: theme.spacing.sm,
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
    backgroundColor: theme.colors.accent,
    borderRadius: theme.radius.button,
    height: 42,
    justifyContent: 'center',
    paddingHorizontal: theme.spacing.md,
  },
  sendDisabled: {
    opacity: 0.45,
  },
  sendText: {
    color: theme.colors.white,
    fontSize: 12,
    fontWeight: '900',
    letterSpacing: 1,
    textTransform: 'uppercase',
  },
});
