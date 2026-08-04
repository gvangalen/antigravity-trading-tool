import { StyleSheet, Text, View } from 'react-native';

import { theme } from '../../constants/theme';
import { StatusChip } from '../layout/StatusChip';
import { CardShell } from './CardShell';

type MasterDecisionCardProps = {
  score: number;
  state: string;
  reason: string;
};

export function MasterDecisionCard({ score, state, reason }: MasterDecisionCardProps) {
  return (
    <CardShell emphasis="primary">
      <View style={styles.header}>
        <View>
          <Text style={styles.label}>Master decision state</Text>
          <Text style={styles.state}>{state}</Text>
        </View>
        <View style={styles.scoreBox}>
          <Text style={styles.score}>{score}</Text>
          <Text style={styles.scoreLabel}>score</Text>
        </View>
      </View>
      <Text style={styles.reason}>{reason}</Text>
      <View style={styles.footer}>
        <StatusChip compact label="Selective" tone="accent" />
        <StatusChip compact label="No rush" tone="warning" />
      </View>
    </CardShell>
  );
}

const styles = StyleSheet.create({
  footer: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: theme.spacing.sm,
    marginTop: theme.spacing.lg,
  },
  header: {
    alignItems: 'flex-start',
    flexDirection: 'row',
    gap: theme.spacing.md,
    justifyContent: 'space-between',
  },
  label: {
    color: theme.colors.accent,
    fontSize: theme.typography.label,
    fontWeight: '900',
    letterSpacing: 1.7,
    textTransform: 'uppercase',
  },
  reason: {
    color: theme.colors.textMuted,
    fontSize: theme.typography.body,
    fontWeight: '600',
    lineHeight: 22,
    marginTop: theme.spacing.md,
  },
  score: {
    color: theme.colors.text,
    fontSize: 22,
    fontWeight: '900',
  },
  scoreBox: {
    alignItems: 'center',
    backgroundColor: theme.colors.accentSoft,
    borderColor: '#1D4ED880',
    borderRadius: theme.radius.md,
    borderWidth: 1,
    minWidth: 68,
    padding: theme.spacing.sm,
  },
  scoreLabel: {
    color: theme.colors.textDim,
    fontSize: 10,
    fontWeight: '900',
    textTransform: 'uppercase',
  },
  state: {
    color: theme.colors.text,
    fontSize: 20,
    fontWeight: '900',
    lineHeight: 24,
    marginTop: 5,
    maxWidth: 210,
  },
});
