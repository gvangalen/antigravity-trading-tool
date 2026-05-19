import { StyleSheet, Text, View } from 'react-native';

import { preferenceColors, useAppPreferences } from '../../preferences/AppPreferencesProvider';
import { theme } from '../../constants/theme';

type AssistantMessageProps = {
  author: string;
  text: string;
  isUser?: boolean;
};

export function AssistantMessage({ author, text, isUser = false }: AssistantMessageProps) {
  const { appearance } = useAppPreferences();
  const colors = preferenceColors(appearance);

  return (
    <View
      style={[
        styles.message,
        isUser ? styles.userMessage : styles.aiMessage,
        { backgroundColor: isUser ? (appearance === 'light' ? '#EFF6FF' : theme.colors.accentSoft) : colors.surface, borderColor: colors.border },
      ]}
    >
      {isUser && <Text style={[styles.messageAuthor, { color: colors.textDim }]}>{author}</Text>}
      <Text style={[styles.messageText, { color: colors.text }]}>{text}</Text>
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
