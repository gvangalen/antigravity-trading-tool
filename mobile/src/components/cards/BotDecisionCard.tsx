import { Pressable, StyleSheet, Text, View } from 'react-native';

import { StatusTone, statusTones, theme } from '../../constants/theme';
import { triggerHaptic } from '../../utils/haptics';
import { StatusChip } from '../layout/StatusChip';
import { CardShell } from './CardShell';

type BotDecisionCardProps = {
  botName: string;
  action: string;
  confidence: number;
  amount: string;
  guardrail: string;
  reason: string;
  tone?: StatusTone;
  onConfirm?: () => void;
};

export function BotDecisionCard({
  botName,
  action,
  confidence,
  amount,
  guardrail,
  reason,
  tone = 'warning',
  onConfirm,
}: BotDecisionCardProps) {
  const palette = statusTones[tone];

  return (
    <CardShell emphasis="primary">
      <View style={styles.header}>
        <View style={styles.heading}>
          <Text style={styles.label}>Bot decision</Text>
          <Text style={styles.botName}>{botName}</Text>
        </View>
        <StatusChip label={action} tone={tone} />
      </View>
      <View style={styles.summaryRow}>
        <Metric label="Confidence" value={`${confidence}`} color={palette.color} />
        <Metric label="Amount" value={amount} color={palette.color} />
      </View>
      <View style={[styles.guardrail, { backgroundColor: palette.background, borderColor: palette.border }]}>
        <Text style={[styles.guardrailLabel, { color: palette.color }]}>Guardrail</Text>
        <Text style={styles.guardrailText}>{guardrail}</Text>
      </View>
      <Text style={styles.reason}>{reason}</Text>
      <View style={styles.actions}>
        <Pressable
          onPress={async () => {
            await triggerHaptic('impact');
            onConfirm?.();
          }}
          style={({ pressed }) => [styles.primaryButton, pressed && styles.pressed]}
        >
          <Text style={styles.primaryText}>Review action</Text>
        </Pressable>
        <Pressable style={({ pressed }) => [styles.secondaryButton, pressed && styles.pressed]}>
          <Text style={styles.secondaryText}>Ask why</Text>
        </Pressable>
      </View>
    </CardShell>
  );
}

function Metric({ label, value, color }: { label: string; value: string; color: string }) {
  return (
    <View style={styles.metric}>
      <Text style={styles.metricLabel}>{label}</Text>
      <Text style={[styles.metricValue, { color }]}>{value}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  actions: {
    flexDirection: 'row',
    gap: theme.spacing.sm,
    marginTop: theme.spacing.lg,
  },
  botName: {
    color: theme.colors.text,
    fontSize: theme.typography.cardTitle,
    fontWeight: '900',
    lineHeight: 22,
    marginTop: 4,
  },
  guardrail: {
    borderRadius: theme.radius.md,
    borderWidth: 1,
    marginTop: theme.spacing.md,
    padding: theme.spacing.md,
  },
  guardrailLabel: {
    fontSize: theme.typography.label,
    fontWeight: '900',
    letterSpacing: 1.5,
    textTransform: 'uppercase',
  },
  guardrailText: {
    color: theme.colors.textSoft,
    fontSize: theme.typography.small,
    fontWeight: '800',
    lineHeight: 20,
    marginTop: 4,
  },
  header: {
    alignItems: 'flex-start',
    flexDirection: 'row',
    gap: theme.spacing.md,
    justifyContent: 'space-between',
  },
  heading: {
    flex: 1,
  },
  label: {
    color: theme.colors.accent,
    fontSize: theme.typography.label,
    fontWeight: '900',
    letterSpacing: 1.7,
    textTransform: 'uppercase',
  },
  metric: {
    backgroundColor: theme.colors.backgroundSoft,
    borderColor: theme.colors.border,
    borderRadius: theme.radius.md,
    borderWidth: 1,
    flex: 1,
    padding: theme.spacing.md,
  },
  metricLabel: {
    color: theme.colors.textDim,
    fontSize: theme.typography.label,
    fontWeight: '900',
    letterSpacing: 1.4,
    textTransform: 'uppercase',
  },
  metricValue: {
    fontSize: 23,
    fontWeight: '900',
    marginTop: 5,
  },
  pressed: {
    opacity: 0.86,
    transform: [{ scale: 0.99 }],
  },
  primaryButton: {
    alignItems: 'center',
    backgroundColor: theme.colors.accent,
    borderRadius: theme.radius.button,
    flex: 1,
    justifyContent: 'center',
    minHeight: 48,
  },
  primaryText: {
    color: theme.colors.white,
    fontSize: 12,
    fontWeight: '900',
    letterSpacing: 1.2,
    textTransform: 'uppercase',
  },
  reason: {
    color: theme.colors.textMuted,
    fontSize: theme.typography.body,
    fontWeight: '600',
    lineHeight: 22,
    marginTop: theme.spacing.md,
  },
  secondaryButton: {
    alignItems: 'center',
    backgroundColor: theme.colors.surfaceMuted,
    borderColor: theme.colors.borderStrong,
    borderRadius: theme.radius.button,
    borderWidth: 1,
    justifyContent: 'center',
    minHeight: 48,
    paddingHorizontal: theme.spacing.md,
  },
  secondaryText: {
    color: theme.colors.textSoft,
    fontSize: 12,
    fontWeight: '900',
  },
  summaryRow: {
    flexDirection: 'row',
    gap: theme.spacing.sm,
    marginTop: theme.spacing.lg,
  },
});
