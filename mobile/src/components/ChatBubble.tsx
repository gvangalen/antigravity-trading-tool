import { StyleSheet, Text, View } from 'react-native';

import { theme } from '../constants/theme';
import { ChatMessage } from '../types/assistant';

type ChatBubbleProps = {
  message: ChatMessage;
};

export function ChatBubble({ message }: ChatBubbleProps) {
  const isUser = message.role === 'user';

  return (
    <View style={[styles.bubble, isUser ? styles.userBubble : styles.assistantBubble]}>
      <Text style={styles.label}>{isUser ? 'You' : 'Tradamind AI'}</Text>
      <Text style={styles.content}>{message.content}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  assistantBubble: {
    alignSelf: 'flex-start',
    backgroundColor: theme.colors.surfaceElevated,
    borderColor: theme.colors.border,
  },
  bubble: {
    borderRadius: theme.radius.card,
    borderWidth: 1,
    maxWidth: '92%',
    padding: theme.spacing.md,
  },
  content: {
    color: theme.colors.text,
    fontSize: 15,
    lineHeight: 22,
  },
  label: {
    color: theme.colors.textMuted,
    fontSize: 12,
    fontWeight: '800',
    marginBottom: theme.spacing.xs,
  },
  userBubble: {
    alignSelf: 'flex-end',
    backgroundColor: theme.colors.accentSoft,
    borderColor: theme.colors.accent,
  },
});
