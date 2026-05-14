import { useCallback, useState, useEffect } from 'react';
import { useRoute } from '@react-navigation/native';
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
import { preferenceColors, useAppPreferences } from '../preferences/AppPreferencesProvider';
import { AssistantInsightResponse, MobileOverviewResponse, MobileIntelligenceEvent, assistantApi, mobileApi } from '../services/tradamindApi';
import { apiClient } from '../services/apiClient';
import { AssistantFeedItem } from '../types/assistant';
import { triggerHaptic } from '../utils/haptics';
import { useAuth } from '../auth/AuthProvider';
import type { MainTabParamList } from '../navigation/MainTabNavigator';

type SheetType = 'risk' | 'confirm' | 'draft' | null;

export function FinnScreen() {
  const route = useRoute<RouteProp<MainTabParamList, 'FINN'>>();
  const { logout, user } = useAuth();
  const { appearance } = useAppPreferences();
  const colors = preferenceColors(appearance);
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

  useEffect(() => {
    const prefill = route.params?.prefill;
    if (prefill) {
      setQuery(prefill);
    }
  }, [route.params?.prefill]);

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
        contentInsetBottom={120}
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
          <View style={styles.hudContainer}>
            {/* PERSONALIZED GREETING */}
            <View style={[styles.greetingBox, { backgroundColor: appearance === 'light' ? '#EFF6FF' : theme.colors.accentSoft, borderColor: appearance === 'light' ? '#BFDBFE' : '#3B82F644' }]}>
              <Text style={[styles.quoteText, { color: colors.text }]}>
                "{(insightResource.data as any)?.greeting || `Hallo ${user?.first_name || 'Henk'}, alle ${briefing.asset} feeds en portfolio operaties draaien stabiel.`}"
              </Text>
            </View>

            {/* Section 3 — FINN Briefing */}
            <View style={[styles.briefingBox, { backgroundColor: colors.surface, borderColor: colors.borderStrong }]}>
              <View style={styles.hudSectionHeader}>
                <Text style={styles.hudSectionIcon}>🛡️</Text>
                <Text style={[styles.hudSectionTitle, { color: colors.textDim }]}>FINN BRIEFING</Text>
              </View>
              <Text style={[styles.quoteText, { color: colors.text }]}>
                "{briefing.summary || insightCard.body || 'BTC bevindt zich momenteel in een consolidatiefase met verhoogd correctierisico zolang volume achterblijft. FINN handhaaft een defensieve posture.'}"
              </Text>
            </View>

            {/* Section 4 — Recent Conversations */}
            <View style={[styles.recentSection, { backgroundColor: colors.surface, borderColor: colors.border }]}>
              <Text style={[styles.recentHeader, { color: colors.textDim }]}>RECENT CONVERSATIONS</Text>
              {[
                { id: 1, title: 'BTC correction review', query: 'Vat de laatste BTC correctie en steunniveaus samen' },
                { id: 2, title: 'Weekly portfolio report', query: 'Analyseer de wekelijkse portfolio prestaties en allocatierisico' },
                { id: 3, title: 'SOL setup analysis', query: 'Beoordeel de huidige SOL setup en DCA drempelwaarden' },
                { id: 4, title: 'Macro contraction discussion', query: 'Bespreek de macro contractie en impact op liquiditeit' },
              ].map((conv) => (
                <Pressable
                  key={conv.id}
                  onPress={() => setQuery(conv.query)}
                  style={({ pressed }) => [
                    styles.recentRow,
                    { backgroundColor: colors.surfaceMuted, borderColor: colors.border },
                    pressed && { opacity: 0.7 },
                  ]}
                >
                  <Text style={[styles.recentTitle, { color: colors.text }]} numberOfLines={1}>
                    💬 {conv.title}
                  </Text>
                  <Text style={[styles.recentArrow, { color: theme.colors.accent }]}>→</Text>
                </Pressable>
              ))}
            </View>
          </View>
        )}

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

      <View style={[styles.composerWrap, { backgroundColor: appearance === 'light' ? '#FFFFFF' : '#020617F2', borderTopColor: colors.border }]}>
        <View style={[styles.composer, { backgroundColor: colors.surface, borderColor: colors.border }]}>
          <TextInput
            multiline
            maxLength={240}
            onChangeText={setQuery}
            placeholder="Vraag iets aan Tradamind..."
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
    gap: theme.spacing.sm,
    marginBottom: theme.spacing.sm,
  },
  hudSectionIcon: {
    fontSize: 16,
  },
  hudSectionTitle: {
    color: theme.colors.textDim,
    fontSize: theme.typography.label,
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
  briefingBox: {
    borderWidth: 1,
    borderRadius: theme.radius.lg,
    padding: theme.spacing.lg,
    marginBottom: theme.spacing.sm,
  },
  greetingBox: {
    borderWidth: 1,
    borderRadius: theme.radius.lg,
    padding: theme.spacing.lg,
    marginBottom: theme.spacing.sm,
  },
  recentSection: {
    borderWidth: 1,
    borderRadius: theme.radius.lg,
    padding: theme.spacing.lg,
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
    borderRadius: theme.radius.md,
    borderWidth: 1,
  },
  recentTitle: {
    fontSize: 13,
    fontWeight: '700',
    flex: 1,
    marginRight: theme.spacing.sm,
  },
  recentArrow: {
    fontSize: 14,
    fontWeight: '900',
  },
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
