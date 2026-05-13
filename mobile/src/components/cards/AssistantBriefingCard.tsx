import { Pressable, StyleSheet, Text, View } from 'react-native';

import { theme } from '../../constants/theme';
import { triggerHaptic } from '../../utils/haptics';
import { StatusChip } from '../layout/StatusChip';
import { CardShell } from './CardShell';

type AssistantBriefingCardProps = {
  status: string;
  summary: string;
  risk: string;
  nextAction: string;
};

export function AssistantBriefingCard({
  status,
  summary,
  risk,
  nextAction,
}: AssistantBriefingCardProps) {
  return (
    <CardShell emphasis="primary">
      <View style={styles.header}>
        <StatusChip label="AI briefing" tone="accent" />
        <Text style={styles.kicker}>Operating layer</Text>
      </View>
      <Text style={styles.status}>{status}</Text>
      <Text style={styles.summary}>{summary}</Text>
      <View style={styles.riskBox}>
        <Text style={styles.riskLabel}>Risk</Text>
        <Text style={styles.riskText}>{risk}</Text>
      </View>
      <Pressable
        onPress={() => triggerHaptic('selection')}
        style={({ pressed }) => [styles.button, pressed && styles.pressed]}
      >
        <Text style={styles.buttonText}>{nextAction}</Text>
      </Pressable>
    </CardShell>
  );
}

const styles = StyleSheet.create({
  button: {
    alignItems: 'center',
    backgroundColor: theme.colors.accent,
    borderRadius: theme.radius.button,
    marginTop: theme.spacing.lg,
    paddingVertical: 14,
  },
  buttonText: {
    color: theme.colors.white,
    fontSize: 12,
    fontWeight: '900',
    letterSpacing: 1.5,
    textTransform: 'uppercase',
  },
  header: {
    alignItems: 'center',
    flexDirection: 'row',
    justifyContent: 'space-between',
  },
  kicker: {
    color: theme.colors.textDim,
    fontSize: theme.typography.label,
    fontWeight: '900',
    letterSpacing: 1.5,
    textTransform: 'uppercase',
  },
  pressed: {
    opacity: 0.86,
    transform: [{ scale: 0.99 }],
  },
  riskBox: {
    backgroundColor: theme.colors.warningSoft,
    borderColor: '#F59E0B55',
    borderRadius: theme.radius.md,
    borderWidth: 1,
    marginTop: theme.spacing.md,
    padding: theme.spacing.md,
  },
  riskLabel: {
    color: theme.colors.warning,
    fontSize: theme.typography.label,
    fontWeight: '900',
    letterSpacing: 1.5,
    textTransform: 'uppercase',
  },
  riskText: {
    color: theme.colors.textSoft,
    fontSize: theme.typography.body,
    fontWeight: '700',
    lineHeight: 22,
    marginTop: 5,
  },
  status: {
    color: theme.colors.text,
    fontSize: 25,
    fontWeight: '900',
    letterSpacing: 0,
    lineHeight: 30,
    marginTop: theme.spacing.lg,
  },
  summary: {
    color: theme.colors.textMuted,
    fontSize: theme.typography.body,
    fontWeight: '600',
    lineHeight: 23,
    marginTop: theme.spacing.sm,
  },
});
