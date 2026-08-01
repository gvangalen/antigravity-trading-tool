import { useEffect, useMemo, useState } from 'react';
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
  onClose: () => void;
  prefill?: string;
  source?: string;
  symbol?: string;
};

export function FinnOverlaySheet({ contextMetric, onClose, prefill, source, symbol }: FinnOverlaySheetProps) {
  const { appearance } = useAppPreferences();
  const colors = preferenceColors(appearance);
  const { context, updateContext } = useIntelligenceContext();
  const [query, setQuery] = useState(prefill ?? '');
  const [sending, setSending] = useState(false);
  const [chatError, setChatError] = useState<string | null>(null);
  const [menuOpen, setMenuOpen] = useState(false);
  const [messages, setMessages] = useState<AssistantFeedItem[]>([]);

  const activeSymbol = symbol || context.asset;
  const activeTimeframe = String(context.timeframe || '1D').toUpperCase();
  const activeWorkspace = context.screen || context.page || 'Analysis';
  const contextLine = `${activeWorkspace} · ${activeSymbol}`;

  const apiContext = useMemo(
    () => ({
      page_type: 'FINN',
      symbol: activeSymbol,
      timeframe: activeTimeframe,
    }),
    [activeSymbol, activeTimeframe],
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
  }, [activeSymbol, contextMetric, prefill]);

  const visibleMessages = messages.filter((item) => item.type === 'message');

  async function handleSend() {
    const trimmed = query.trim();
    if (!trimmed || sending) return;

    await triggerHaptic('selection');
    setSending(true);
    setChatError(null);
    setMenuOpen(false);
    setMessages((current) => [
      ...current,
      {
        id: `user-${Date.now()}`,
        role: 'user',
        text: trimmed,
        type: 'message',
      },
    ]);
    setQuery('');

    try {
      const envelope = await assistantApi.chat(trimmed, apiContext);
      const mapped = mapAssistantEnvelopeToFeedItems(envelope).filter((item) => item.type === 'message');
      setMessages((current) => [...current, ...mapped]);
    } catch (error) {
      setChatError(error instanceof Error ? error.message : 'FINN chat request failed');
    } finally {
      setSending(false);
    }
  }

  function applyQuickAction(kind: 'asset' | 'indicator') {
    setMenuOpen(false);
    setQuery(
      kind === 'asset'
        ? `Add an asset to my ${activeWorkspace.toLowerCase()} workspace.`
        : `Add an indicator to my ${activeWorkspace.toLowerCase()} workspace.`,
    );
  }

  return (
    <SafeAreaView style={[styles.safeArea, { backgroundColor: 'rgba(15, 23, 42, 0.22)' }]}>
      <KeyboardAvoidingView
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
        style={styles.flex}
      >
        <Pressable onPress={onClose} style={styles.backdrop} />

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
              <Pressable onPress={onClose} style={({ pressed }) => [styles.iconBtn, pressed && styles.pressed]}>
                <Feather color={colors.text} name="x" size={28} />
              </Pressable>
            </View>

            <View style={styles.body}>
              {menuOpen ? (
                <View style={[styles.menu, { backgroundColor: colors.surface, borderColor: colors.border }]}>
                  <Pressable
                    onPress={() => applyQuickAction('asset')}
                    style={({ pressed }) => [styles.menuItem, pressed && styles.menuItemPressed]}
                  >
                    <Feather color={colors.textDim} name="search" size={20} />
                    <Text style={[styles.menuText, { color: colors.text }]}>Add asset</Text>
                  </Pressable>
                  <Pressable
                    onPress={() => applyQuickAction('indicator')}
                    style={({ pressed }) => [styles.menuItem, pressed && styles.menuItemPressed]}
                  >
                    <Feather color={colors.textDim} name="sliders" size={20} />
                    <Text style={[styles.menuText, { color: colors.text }]}>Add indicator</Text>
                  </Pressable>
                </View>
              ) : null}

              <View style={[styles.composer, { backgroundColor: colors.backgroundSoft, borderColor: colors.border }]}>
                <Pressable
                  onPress={() => setMenuOpen((current) => !current)}
                  style={({ pressed }) => [styles.leadingAction, pressed && styles.pressed]}
                >
                  <Feather color={colors.textDim} name={menuOpen ? 'x' : 'plus'} size={22} />
                </Pressable>
                <TextInput
                  multiline
                  onChangeText={setQuery}
                  placeholder="Ask FINN or give an instruction..."
                  placeholderTextColor={colors.textDim}
                  style={[styles.input, { color: colors.text }]}
                  value={query}
                />
                <Pressable
                  disabled={!query.trim() || sending}
                  onPress={handleSend}
                  style={({ pressed }) => [
                    styles.sendBtn,
                    {
                      backgroundColor: query.trim() && !sending ? colors.textDim : colors.border,
                    },
                    pressed && styles.pressed,
                  ]}
                >
                  <Feather color="#ffffff" name="send" size={18} />
                </Pressable>
              </View>

              {visibleMessages.length > 0 ? (
                <ScrollView
                  contentContainerStyle={styles.feed}
                  keyboardShouldPersistTaps="handled"
                  showsVerticalScrollIndicator={false}
                >
                  {visibleMessages.map((item) => {
                    const isUser = item.role === 'user';
                    return (
                      <View
                        key={item.id}
                        style={[
                          styles.message,
                          {
                            alignSelf: isUser ? 'flex-end' : 'stretch',
                            backgroundColor: isUser ? colors.backgroundSoft : colors.surfaceElevated,
                            borderColor: colors.border,
                          },
                        ]}
                      >
                        <Text style={[styles.messageText, { color: colors.text }]}>{item.text}</Text>
                      </View>
                    );
                  })}
                </ScrollView>
              ) : null}

              {chatError ? (
                <Text style={[styles.errorText, { color: theme.colors.danger }]}>
                  FINN kon je vraag niet beantwoorden: {chatError}
                </Text>
              ) : null}
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
    paddingBottom: 4,
  },
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
    marginBottom: 2,
    marginLeft: 6,
    minWidth: 188,
    overflow: 'hidden',
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
    borderRadius: 20,
    borderWidth: 1,
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
    borderRadius: 28,
    borderWidth: 1,
    maxHeight: '62%',
    overflow: 'hidden',
    shadowColor: '#0F172A',
    shadowOffset: { height: 18, width: 0 },
    shadowOpacity: 0.15,
    shadowRadius: 32,
  },
  sheetWrap: {
    flex: 1,
    justifyContent: 'center',
    paddingHorizontal: 22,
  },
});
