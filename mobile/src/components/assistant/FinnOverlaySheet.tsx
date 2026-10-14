import { Dispatch, SetStateAction, useEffect, useMemo, useRef, useState } from 'react';
import {
  KeyboardAvoidingView,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';
import { Feather } from '@expo/vector-icons';
import { SafeAreaView } from 'react-native-safe-area-context';

import { theme } from '../../constants/theme';
import { useIntelligenceContext } from '../../contexts/ActiveIntelligenceContext';
import { preferenceColors, useAppPreferences } from '../../preferences/AppPreferencesProvider';
import { mapAssistantEnvelopeToFeedItems } from '../../services/assistantEnvelopeMapper';
import { assistantApi } from '../../services/tradamindApi';
import type { AssistantFeedItem } from '../../types/assistant';
import { triggerHaptic } from '../../utils/haptics';

type FinnOverlaySheetProps = {
  contextMetric?: string;
  feedItemId?: string;
  onClose: () => void;
  prefill?: string;
  source?: string;
  symbol?: string;
  query: string;
  onQueryChange: Dispatch<SetStateAction<string>>;
  messages: AssistantFeedItem[];
  onMessagesChange: Dispatch<SetStateAction<AssistantFeedItem[]>>;
  sessionId: string | null;
  onSessionIdChange: Dispatch<SetStateAction<string | null>>;
  onNewConversation: () => void;
};

export function FinnOverlaySheet({ contextMetric, feedItemId, onClose, prefill, source, symbol, query, onQueryChange: setQuery, messages, onMessagesChange: setMessages, sessionId, onSessionIdChange: setSessionId, onNewConversation }: FinnOverlaySheetProps) {
  const { appearance, language } = useAppPreferences();
  const colors = preferenceColors(appearance);
  const { context, updateContext } = useIntelligenceContext();
  const [sending, setSending] = useState(false);
  const [chatError, setChatError] = useState<string | null>(null);
  const [menuOpen, setMenuOpen] = useState(false);
  const [pendingFeedItemId, setPendingFeedItemId] = useState(feedItemId);
  const requestSequence = useRef(0);
  const activeRequest = useRef<AbortController | null>(null);
  const copy = language === 'nl'
    ? { placeholder: 'Vraag FINN wat dit betekent voor jouw plan...', addAsset: 'Asset toevoegen', addIndicator: 'Indicator toevoegen', addAssetPrompt: 'Help me een asset toe te voegen.', addIndicatorPrompt: 'Help me een indicator toe te voegen.', newConversation: 'Nieuw gesprek', error: 'FINN kon je vraag niet beantwoorden', retry: 'Opnieuw', working: 'FINN verwerkt je vraag...', stopped: 'Antwoord gestopt.', starters: ['Controleer mijn plan', 'Wat vraagt mijn aandacht?', 'Leg mijn score uit'], prompts: ['Controleer mijn huidige plan.', 'Wat vraagt nu mijn aandacht op basis van mijn plannen?', 'Leg de huidige score voor deze asset uit.'] }
    : language === 'de'
      ? { placeholder: 'Frag FINN, was das für deinen Plan bedeutet...', addAsset: 'Asset hinzufügen', addIndicator: 'Indikator hinzufügen', addAssetPrompt: 'Hilf mir, ein Asset hinzuzufügen.', addIndicatorPrompt: 'Hilf mir, einen Indikator hinzuzufügen.', newConversation: 'Neues Gespräch', error: 'FINN konnte deine Frage nicht beantworten', retry: 'Erneut versuchen', working: 'FINN verarbeitet deine Frage...', stopped: 'Antwort gestoppt.', starters: ['Meinen Plan prüfen', 'Was braucht Aufmerksamkeit?', 'Meinen Score erklären'], prompts: ['Prüfe meinen aktuellen Plan.', 'Was braucht jetzt meine Aufmerksamkeit in meinen Plänen?', 'Erkläre den aktuellen Score für dieses Asset.'] }
      : { placeholder: 'Ask FINN what this means for your plan...', addAsset: 'Add asset', addIndicator: 'Add indicator', addAssetPrompt: 'Help me add an asset.', addIndicatorPrompt: 'Help me add an indicator.', newConversation: 'New conversation', error: 'FINN could not answer your question', retry: 'Retry', working: 'FINN is working on your question...', stopped: 'Response stopped.', starters: ['Review my plan', 'What needs my attention?', 'Explain my score'], prompts: ['Review my current plan.', 'What needs my attention in my plans now?', 'Explain the current score for this asset.'] };

  useEffect(() => {
    setPendingFeedItemId(feedItemId);
  }, [feedItemId]);

  const activeSymbol = symbol || context.asset;
  const activeTimeframe = String(context.timeframe || '1D').toUpperCase();
  const activeWorkspace = context.screen || context.page || 'Analysis';
  const contextLine = `${activeWorkspace} · ${activeSymbol}`;

  const apiContext = useMemo(
    () => ({
      page_type: 'FINN',
      symbol: activeSymbol,
      timeframe: activeTimeframe,
      ...(pendingFeedItemId ? { feed_item_id: pendingFeedItemId } : {}),
    }),
    [activeSymbol, activeTimeframe, pendingFeedItemId],
  );

  useEffect(() => {
    if (symbol && symbol !== context.asset) {
      updateContext({ asset: symbol, screen: activeWorkspace });
    }
  }, [activeWorkspace, context.asset, symbol, updateContext]);

  useEffect(() => {
    if (prefill) {
      setQuery(prefill);
      return;
    }
    if (contextMetric) {
      setQuery(`Explain ${contextMetric} for ${activeSymbol}.`);
    }
  }, [activeSymbol, contextMetric, prefill, setQuery]);

  const visibleMessages = messages.filter((item) => item.type === 'message');

  async function handleSend(prompt?: string, retry = false) {
    const trimmed = (prompt ?? query).trim();
    if (!trimmed || sending) return;
    const requestId = ++requestSequence.current;
    const controller = new AbortController();
    activeRequest.current = controller;

    await triggerHaptic('selection');
    setSending(true);
    setChatError(null);
    setMenuOpen(false);
    setMessages((current) => [
      ...(retry ? current.slice(0, -1) : current),
      {
        id: `user-${Date.now()}`,
        role: 'user',
        text: trimmed,
        type: 'message',
      },
    ]);
    setQuery('');

    try {
      const history = (retry ? messages.slice(0, -1) : messages)
        .filter((item): item is Extract<AssistantFeedItem, { type: 'message' }> => item.type === 'message')
        .map((item) => ({ role: item.role, text: item.text }));
      const envelope = await assistantApi.chat(trimmed, apiContext, history, sessionId, controller.signal);
      if (requestId !== requestSequence.current) return;
      const mapped = mapAssistantEnvelopeToFeedItems(envelope).filter((item) => item.type === 'message');
      setMessages((current) => [...current, ...mapped]);
      if (envelope.session_id) setSessionId(envelope.session_id);
      setPendingFeedItemId(undefined);
    } catch (error) {
      if (requestId !== requestSequence.current) return;
      setChatError(error instanceof Error ? error.message : 'FINN chat request failed');
    } finally {
      if (activeRequest.current === controller) activeRequest.current = null;
      if (requestId === requestSequence.current) setSending(false);
    }
  }

  function stopResponse() {
    requestSequence.current += 1;
    activeRequest.current?.abort();
    activeRequest.current = null;
    setSending(false);
    setChatError(null);
    setMessages((current) => [...current, { id: `stopped-${Date.now()}`, role: 'assistant', text: copy.stopped, type: 'message' }]);
  }

  function applyQuickAction(kind: 'asset' | 'indicator') {
    setMenuOpen(false);
    setQuery(kind === 'asset' ? copy.addAssetPrompt : copy.addIndicatorPrompt);
  }

  return (
    <SafeAreaView style={[styles.safeArea, { backgroundColor: colors.surface }]}>
      <KeyboardAvoidingView
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
        style={styles.flex}
      >
        <View style={styles.sheetWrap} pointerEvents="box-none">
          <View style={[styles.sheet, { backgroundColor: colors.surface, borderColor: colors.border }]}>
            <View style={[styles.header, { borderBottomColor: colors.borderSubtle }]}>
              <View style={styles.headerIdentity}>
                <View style={styles.logo}>
                  <Text style={styles.logoText}>F</Text>
                </View>
                <View style={styles.headerCopy}>
                  <Text style={[styles.headerTitle, { color: colors.text }]}>FINN</Text>
                  <Text style={[styles.headerContext, { color: colors.textMuted }]}>{contextLine}</Text>
                </View>
              </View>
              <View style={styles.headerActions}>
                <Pressable accessibilityLabel={copy.newConversation} onPress={() => {
                  requestSequence.current += 1;
                  activeRequest.current?.abort();
                  activeRequest.current = null;
                  setSending(false);
                  setChatError(null);
                  setPendingFeedItemId(undefined);
                  onNewConversation();
                }} style={({ pressed }) => [styles.iconBtn, pressed && styles.pressed]}>
                  <Feather color={colors.text} name="plus" size={22} />
                </Pressable>
                <Pressable onPress={onClose} style={({ pressed }) => [styles.iconBtn, pressed && styles.pressed]}>
                  <Feather color={colors.text} name="x" size={26} />
                </Pressable>
              </View>
            </View>

            <View style={styles.body}>
              {menuOpen ? (
                <View style={[styles.menu, { backgroundColor: colors.surface, borderColor: colors.border }]}>
                  <Pressable
                    onPress={() => applyQuickAction('asset')}
                    style={({ pressed }) => [styles.menuItem, pressed && styles.menuItemPressed]}
                  >
                    <Feather color={colors.textDim} name="search" size={20} />
                    <Text style={[styles.menuText, { color: colors.text }]}>{copy.addAsset}</Text>
                  </Pressable>
                  <Pressable
                    onPress={() => applyQuickAction('indicator')}
                    style={({ pressed }) => [styles.menuItem, pressed && styles.menuItemPressed]}
                  >
                    <Feather color={colors.textDim} name="sliders" size={20} />
                    <Text style={[styles.menuText, { color: colors.text }]}>{copy.addIndicator}</Text>
                  </Pressable>
                </View>
              ) : null}

              <ScrollView
                  style={styles.messages}
                  contentContainerStyle={styles.feed}
                  keyboardShouldPersistTaps="handled"
                  showsVerticalScrollIndicator={false}
                >
                  {visibleMessages.length === 0 ? copy.starters.map((label, index) => (
                    <Pressable key={label} onPress={() => void handleSend(copy.prompts[index])}
                      style={[styles.starter, { borderColor: colors.border }]}>
                      <Text style={[styles.messageText, { color: colors.text }]}>{label}</Text>
                    </Pressable>
                  )) : null}
                  {visibleMessages.map((item) => {
                    const isUser = item.role === 'user';
                    return (
                      <View
                        key={item.id}
                        style={[
                          styles.message,
                          {
                            alignSelf: isUser ? 'flex-end' : 'stretch',
                            backgroundColor: isUser ? colors.backgroundSoft : colors.surface,
                            borderColor: isUser ? colors.border : 'transparent',
                          },
                        ]}
                      >
                        <Text style={[styles.messageText, { color: colors.text }]}>{item.text}</Text>
                      </View>
                    );
                  })}
                </ScrollView>

              {sending ? <Text style={[styles.progress, { color: colors.textMuted }]}>{copy.working}</Text> : null}

              {chatError ? (
                <Pressable onPress={() => {
                  const lastUser = [...visibleMessages].reverse().find((item) => item.role === 'user');
                  if (lastUser) void handleSend(lastUser.text, true);
                }}>
                  <Text style={[styles.errorText, { color: theme.colors.danger }]}>{copy.error}: {chatError} · {copy.retry}</Text>
                </Pressable>
              ) : null}

              <View style={[styles.composer, { backgroundColor: colors.backgroundSoft, borderColor: colors.border }]}>
                <Pressable onPress={() => setMenuOpen((current) => !current)}
                  style={({ pressed }) => [styles.leadingAction, pressed && styles.pressed]}>
                  <Feather color={colors.textDim} name={menuOpen ? 'x' : 'plus'} size={22} />
                </Pressable>
                <TextInput multiline onChangeText={setQuery} placeholder={copy.placeholder}
                  placeholderTextColor={colors.textDim} style={[styles.input, { color: colors.text }]} value={query} />
                <Pressable disabled={!sending && !query.trim()}
                  onPress={() => sending ? stopResponse() : void handleSend()}
                  style={({ pressed }) => [styles.sendBtn, {
                    backgroundColor: sending || query.trim() ? theme.colors.accent : colors.border,
                  }, pressed && styles.pressed]}>
                  <Feather color="#ffffff" name={sending ? 'square' : 'send'} size={18} />
                </Pressable>
              </View>
            </View>
          </View>
        </View>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  backdrop: {
    ...StyleSheet.absoluteFillObject,
  },
  body: {
    flex: 1,
    gap: 12,
    padding: 14,
  },
  composer: {
    alignItems: 'center',
    borderRadius: 24,
    borderWidth: 1,
    flexDirection: 'row',
    gap: 10,
    minHeight: 56,
    paddingHorizontal: 12,
    paddingVertical: 8,
  },
  errorText: {
    fontSize: 13,
    fontWeight: '600',
    lineHeight: 18,
  },
  feed: {
    gap: 10,
    paddingBottom: 20,
  },
  messages: { flex: 1 },
  progress: { fontSize: 12, paddingHorizontal: 4 },
  starter: { borderRadius: 16, borderWidth: 1, paddingHorizontal: 16, paddingVertical: 14 },
  flex: {
    flex: 1,
  },
  header: {
    alignItems: 'center',
    borderBottomWidth: 1,
    flexDirection: 'row',
    justifyContent: 'space-between',
    paddingHorizontal: 16,
    paddingVertical: 12,
  },
  headerContext: {
    fontSize: 10,
    fontWeight: '700',
  },
  headerCopy: {
    gap: 2,
  },
  headerActions: { flexDirection: 'row', alignItems: 'center' },
  headerIdentity: {
    alignItems: 'center',
    flexDirection: 'row',
    gap: 12,
  },
  headerTitle: {
    fontSize: 16,
    fontWeight: '900',
  },
  iconBtn: {
    alignItems: 'center',
    borderRadius: 18,
    height: 40,
    justifyContent: 'center',
    width: 40,
  },
  input: {
    flex: 1,
    fontSize: 13,
    lineHeight: 18,
    maxHeight: 84,
    paddingVertical: 0,
  },
  leadingAction: {
    alignItems: 'center',
    borderRadius: 16,
    height: 32,
    justifyContent: 'center',
    width: 32,
  },
  logo: {
    alignItems: 'center',
    backgroundColor: theme.colors.accent,
    borderRadius: 14,
    height: 40,
    justifyContent: 'center',
    width: 40,
  },
  logoText: {
    color: '#ffffff',
    fontSize: 20,
    fontWeight: '900',
  },
  menu: {
    alignSelf: 'flex-start',
    borderRadius: 18,
    borderWidth: 1,
    bottom: 85,
    left: 20,
    minWidth: 188,
    overflow: 'hidden',
    position: 'absolute',
    zIndex: 2,
    shadowColor: '#0F172A',
    shadowOffset: { height: 8, width: 0 },
    shadowOpacity: 0.1,
    shadowRadius: 18,
  },
  menuItem: {
    alignItems: 'center',
    flexDirection: 'row',
    gap: 12,
    paddingHorizontal: 16,
    paddingVertical: 14,
  },
  menuItemPressed: {
    opacity: 0.82,
  },
  menuText: {
    fontSize: 15,
    fontWeight: '700',
  },
  message: {
    borderRadius: 18,
    borderWidth: 0,
    paddingHorizontal: 16,
    paddingVertical: 14,
  },
  messageText: {
    fontSize: 14,
    fontWeight: '500',
    lineHeight: 20,
  },
  pressed: {
    opacity: 0.86,
    transform: [{ scale: 0.99 }],
  },
  safeArea: {
    flex: 1,
  },
  sendBtn: {
    alignItems: 'center',
    borderRadius: 18,
    height: 40,
    justifyContent: 'center',
    width: 40,
  },
  sheet: {
    borderRadius: 0,
    borderWidth: 0,
    flex: 1,
    overflow: 'hidden',
    shadowColor: '#0F172A',
    shadowOffset: { height: 18, width: 0 },
    shadowOpacity: 0.15,
    shadowRadius: 32,
  },
  sheetWrap: {
    flex: 1,
  },
});
