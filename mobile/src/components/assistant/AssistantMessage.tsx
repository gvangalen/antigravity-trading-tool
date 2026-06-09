import { StyleSheet, Text, View } from 'react-native';

import { preferenceColors, useAppPreferences } from '../../preferences/AppPreferencesProvider';
import { theme } from '../../constants/theme';

type AssistantMessageProps = {
  author: string;
  text: string;
  isUser?: boolean;
  summary?: string | null;
  riskSummary?: string | null;
  nextBestAction?: string | null;
  reviewReason?: string | null;
  flow?: string | null;
  intent?: string | null;
};

export function AssistantMessage({
  author,
  text,
  isUser = false,
  summary,
  riskSummary,
  nextBestAction,
  reviewReason,
  flow,
  intent,
}: AssistantMessageProps) {
  const { appearance } = useAppPreferences();
  const colors = preferenceColors(appearance);
  const shouldRenderOperatorReadout = !isUser && Boolean(
    riskSummary ||
    nextBestAction ||
    reviewReason ||
    (summary && summary !== text)
  ) && !['decision_review', 'plan_adherence_review'].includes(String(intent || flow || ''));

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
      {shouldRenderOperatorReadout && (
        <View style={[styles.operatorCard, { backgroundColor: appearance === 'light' ? '#F8FAFC' : '#0F172A', borderColor: colors.border }]}>
          <Text style={[styles.operatorEyebrow, { color: colors.textDim }]}>Operator readout</Text>
          {summary && summary !== text && (
            <Text style={[styles.operatorHeadline, { color: colors.text }]}>{summary}</Text>
          )}
          {reviewReason ? (
            <Text style={[styles.operatorBody, { color: colors.textSoft }]}>{reviewReason}</Text>
          ) : null}
          {(riskSummary || nextBestAction) && (
            <View style={styles.operatorGrid}>
              {riskSummary ? (
                <View style={[styles.operatorBlock, { borderColor: colors.border }]}>
                  <Text style={[styles.operatorLabel, { color: colors.textDim }]}>Risicoframe</Text>
                  <Text style={[styles.operatorBody, { color: colors.textSoft }]}>{riskSummary}</Text>
                </View>
              ) : null}
              {nextBestAction ? (
                <View style={[styles.operatorBlock, { borderColor: colors.border }]}>
                  <Text style={[styles.operatorLabel, { color: colors.textDim }]}>Volgende stap</Text>
                  <Text style={[styles.operatorBody, { color: colors.textSoft }]}>{nextBestAction}</Text>
                </View>
              ) : null}
            </View>
          )}
        </View>
      )}
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
  operatorBlock: {
    borderRadius: theme.radius.md,
    borderWidth: 1,
    flex: 1,
    gap: 6,
    minWidth: 0,
    padding: theme.spacing.sm,
  },
  operatorBody: {
    fontSize: theme.typography.small,
    fontWeight: '600',
    lineHeight: 18,
  },
  operatorCard: {
    borderRadius: theme.radius.md,
    borderWidth: 1,
    gap: theme.spacing.sm,
    marginTop: theme.spacing.sm,
    padding: theme.spacing.sm,
  },
  operatorEyebrow: {
    fontSize: theme.typography.label,
    fontWeight: '900',
    letterSpacing: 1.2,
    textTransform: 'uppercase',
  },
  operatorGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: theme.spacing.sm,
  },
  operatorHeadline: {
    fontSize: theme.typography.body,
    fontWeight: '800',
    lineHeight: 20,
  },
  operatorLabel: {
    fontSize: theme.typography.label,
    fontWeight: '900',
    letterSpacing: 1,
    textTransform: 'uppercase',
  },
  userMessage: {
    alignSelf: 'flex-end',
    backgroundColor: theme.colors.accentSoft,
    borderColor: '#1D4ED880',
  },
});
