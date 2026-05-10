import { useEffect, useState } from 'react';
import {
  ActivityIndicator,
  FlatList,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { ChatBubble } from '../components/ChatBubble';
import { theme } from '../constants/theme';
import { getInitialChatMessages, sendAssistantMessage } from '../services/mockDataService';
import { ChatMessage } from '../types/assistant';

export function AssistantScreen() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(true);
  const [isSending, setIsSending] = useState(false);

  useEffect(() => {
    async function loadMessages() {
      const initialMessages = await getInitialChatMessages();
      setMessages(initialMessages);
      setIsLoading(false);
    }

    loadMessages();
  }, []);

  async function handleSend() {
    const content = input.trim();

    if (!content || isSending) {
      return;
    }

    const userMessage: ChatMessage = {
      id: `user-${Date.now()}`,
      role: 'user',
      content,
      createdAt: new Date().toISOString(),
    };

    setMessages((current) => [...current, userMessage]);
    setInput('');
    setIsSending(true);

    const assistantMessage = await sendAssistantMessage(content);
    setMessages((current) => [...current, assistantMessage]);
    setIsSending(false);
  }

  return (
    <SafeAreaView style={styles.safeArea}>
      <KeyboardAvoidingView
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
        keyboardVerticalOffset={Platform.OS === 'ios' ? 8 : 0}
        style={styles.container}
      >
        <View style={styles.header}>
          <Text style={styles.kicker}>AI Trading Assistant</Text>
          <Text style={styles.title}>Tradamind</Text>
          <Text style={styles.subtitle}>Beslis rustiger met context voordat je handelt.</Text>
        </View>

        {isLoading ? (
          <View style={styles.loading}>
            <ActivityIndicator color={theme.colors.accent} />
          </View>
        ) : (
          <FlatList
            contentContainerStyle={styles.messages}
            data={messages}
            keyExtractor={(item) => item.id}
            renderItem={({ item }) => <ChatBubble message={item} />}
          />
        )}

        {isSending ? (
          <View style={styles.sending}>
            <ActivityIndicator color={theme.colors.accent} size="small" />
            <Text style={styles.sendingText}>Tradamind denkt mee...</Text>
          </View>
        ) : null}

        <View style={styles.composer}>
          <TextInput
            multiline
            onChangeText={setInput}
            placeholder="Vraag iets aan de assistant..."
            placeholderTextColor={theme.colors.textMuted}
            style={styles.input}
            value={input}
          />
          <Pressable
            disabled={!input.trim() || isSending}
            onPress={handleSend}
            style={({ pressed }) => [
              styles.sendButton,
              (!input.trim() || isSending) && styles.sendButtonDisabled,
              pressed && styles.sendButtonPressed,
            ]}
          >
            <Text style={styles.sendText}>Send</Text>
          </Pressable>
        </View>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  composer: {
    alignItems: 'flex-end',
    borderTopColor: theme.colors.border,
    borderTopWidth: 1,
    flexDirection: 'row',
    gap: theme.spacing.sm,
    padding: theme.spacing.md,
  },
  container: {
    flex: 1,
  },
  header: {
    paddingHorizontal: theme.spacing.lg,
    paddingTop: theme.spacing.md,
  },
  input: {
    backgroundColor: theme.colors.surface,
    borderColor: theme.colors.border,
    borderRadius: theme.radius.button,
    borderWidth: 1,
    color: theme.colors.text,
    flex: 1,
    fontSize: 15,
    maxHeight: 110,
    minHeight: 48,
    paddingHorizontal: theme.spacing.md,
    paddingVertical: 13,
  },
  kicker: {
    color: theme.colors.accent,
    fontSize: 13,
    fontWeight: '900',
    textTransform: 'uppercase',
  },
  loading: {
    alignItems: 'center',
    flex: 1,
    justifyContent: 'center',
  },
  messages: {
    gap: theme.spacing.md,
    padding: theme.spacing.lg,
  },
  safeArea: {
    backgroundColor: theme.colors.background,
    flex: 1,
  },
  sendButton: {
    alignItems: 'center',
    backgroundColor: theme.colors.accent,
    borderRadius: theme.radius.button,
    height: 48,
    justifyContent: 'center',
    paddingHorizontal: theme.spacing.lg,
  },
  sendButtonDisabled: {
    opacity: 0.45,
  },
  sendButtonPressed: {
    opacity: 0.85,
  },
  sendText: {
    color: theme.colors.text,
    fontSize: 15,
    fontWeight: '900',
  },
  sending: {
    alignItems: 'center',
    flexDirection: 'row',
    gap: theme.spacing.sm,
    paddingHorizontal: theme.spacing.lg,
    paddingVertical: theme.spacing.sm,
  },
  sendingText: {
    color: theme.colors.textMuted,
    fontSize: 13,
    fontWeight: '700',
  },
  subtitle: {
    color: theme.colors.textMuted,
    fontSize: 15,
    lineHeight: 22,
    marginTop: theme.spacing.xs,
  },
  title: {
    color: theme.colors.text,
    fontSize: 36,
    fontWeight: '900',
    letterSpacing: 0,
    marginTop: theme.spacing.xs,
  },
});
