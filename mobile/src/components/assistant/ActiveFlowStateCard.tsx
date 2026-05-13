import { StyleSheet, Text, View } from 'react-native';

import { theme } from '../../constants/theme';
import { AssistantConversationState } from '../../types/assistant';
import { StatusChip } from '../layout/StatusChip';
import { CardShell } from '../cards/CardShell';

type ActiveFlowStateCardProps = {
  state: AssistantConversationState;
};

export function ActiveFlowStateCard({ state }: ActiveFlowStateCardProps) {
  const filledSlots = Object.entries(state.slots).filter(([, value]) => value !== undefined && value !== null && value !== '');
  const missingSlots = state.missing_slots || [];
  const total = filledSlots.length + missingSlots.length || 1;
  const progress = Math.round((filledSlots.length / total) * 100);

  return (
    <CardShell>
      <View style={styles.header}>
        <StatusChip label="Active flow" tone="accent" />
        <Text style={styles.progress}>{progress}%</Text>
      </View>
      <Text style={styles.title}>{formatFlow(state.current_flow)}</Text>
      <Text style={styles.body}>
        {state.asset || 'Asset'} context is being collected. Drafts stay blocked until the
        required information is complete.
      </Text>
      <View style={styles.track}>
        <View style={[styles.fill, { width: `${progress}%` }]} />
      </View>
      {missingSlots.length > 0 ? (
        <Text style={styles.missing}>Missing: {missingSlots.join(', ')}</Text>
      ) : null}
    </CardShell>
  );
}

function formatFlow(flow: string) {
  return flow
    .split('_')
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(' ');
}

const styles = StyleSheet.create({
  body: {
    color: theme.colors.textMuted,
    fontSize: theme.typography.body,
    fontWeight: '600',
    lineHeight: 22,
    marginTop: theme.spacing.sm,
  },
  fill: {
    backgroundColor: theme.colors.accent,
    borderRadius: theme.radius.pill,
    height: 6,
  },
  header: {
    alignItems: 'center',
    flexDirection: 'row',
    justifyContent: 'space-between',
  },
  missing: {
    color: theme.colors.textDim,
    fontSize: theme.typography.small,
    fontWeight: '800',
    marginTop: theme.spacing.sm,
  },
  progress: {
    color: theme.colors.accent,
    fontSize: theme.typography.cardTitle,
    fontWeight: '900',
  },
  title: {
    color: theme.colors.text,
    fontSize: theme.typography.title,
    fontWeight: '900',
    marginTop: theme.spacing.md,
  },
  track: {
    backgroundColor: theme.colors.backgroundSoft,
    borderRadius: theme.radius.pill,
    height: 6,
    marginTop: theme.spacing.md,
    overflow: 'hidden',
  },
});
