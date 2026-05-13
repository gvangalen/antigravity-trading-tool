import { StyleSheet, Text, View } from 'react-native';

import { theme } from '../../constants/theme';

type AssistantMessageProps = {
  author: string;
  text: string;
  isUser?: boolean;
};

export function AssistantMessage({ author, text, isUser = false }: AssistantMessageProps) {
  return (
    <View style={[styles.message, isUser ? styles.userMessage : styles.aiMessage]}>
      <Text style={styles.messageAuthor}>{author}</Text>
      <Text style={styles.messageText}>{text}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  aiMessage: {
    alignSelf: 'flex-start',
    backgroundColor: theme.colors.surface,
    borderColor: theme.colors.border,
  },
  message: {
    borderRadius: theme.radius.card,
    borderWidth: 1,
    maxWidth: '92%',
    padding: theme.spacing.md,
  },
  messageAuthor: {
    color: theme.colors.textDim,
    fontSize: theme.typography.label,
    fontWeight: '900',
    letterSpacing: 1.4,
    marginBottom: 6,
    textTransform: 'uppercase',
  },
  messageText: {
    color: theme.colors.textSoft,
    fontSize: theme.typography.body,
    fontWeight: '600',
    lineHeight: 22,
  },
  userMessage: {
    alignSelf: 'flex-end',
    backgroundColor: theme.colors.accentSoft,
    borderColor: '#1D4ED880',
  },
});
