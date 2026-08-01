import { Pressable, StyleSheet, Text, View } from 'react-native';

import { preferenceColors, useAppPreferences } from '../../preferences/AppPreferencesProvider';
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
  onAskWhy?: () => void;
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
  onAskWhy,
}: BotDecisionCardProps) {
  const { appearance } = useAppPreferences();
  const colors = preferenceColors(appearance);
  const palette = statusTones[tone];

  return (
    <View style={{ paddingVertical: theme.spacing.md, paddingHorizontal: theme.spacing.lg }}>
      <CardShell emphasis="standard">
        <View style={styles.header}>
          <View style={styles.heading}>
            <Text style={styles.label}>Automation review</Text>
            <Text style={[styles.botName, { color: colors.text }]}>{botName}</Text>
          </View>
          <StatusChip label={action} tone={tone} />
        </View>
        <View style={styles.summaryRow}>
          <Metric label="Confidence" value={`${confidence}`} color={palette.color} colors={colors} />
          <Metric label="Amount" value={amount} color={palette.color} colors={colors} />
        </View>
        <View style={[styles.guardrailPanel, { borderColor: colors.border, backgroundColor: colors.surfaceMuted }]}>
          <Text style={[styles.guardrailKicker, { color: palette.color }]}>Guardrail</Text>
          <Text style={[styles.guardrailValue, { color: colors.text }]}>{guardrail}</Text>
          <Text style={[styles.reason, { color: colors.textMuted }]}>{reason}</Text>
        </View>
        <View style={styles.actions}>
          <Pressable
            onPress={async () => {
              await triggerHaptic('impact');
              onConfirm?.();
            }}
            style={({ pressed }) => [styles.primaryButton, { backgroundColor: colors.surfaceMuted, borderColor: colors.borderStrong }, pressed && styles.pressed]}
          >
            <Text style={styles.primaryText}>Review action</Text>
          </Pressable>
          {onAskWhy ? (
            <Pressable
              onPress={async () => {
                await triggerHaptic('selection');
                onAskWhy();
              }}
              style={({ pressed }) => [styles.secondaryButton, { borderColor: colors.borderStrong }, pressed && styles.pressed]}
            >
              <Text style={[styles.secondaryText, { color: colors.textSoft }]}>Ask why</Text>
            </Pressable>
          ) : null}
        </View>
      </CardShell>
    </View>
  );
}

function Metric({ label, value, colors }: { label: string; value: string; color: string; colors: ReturnType<typeof preferenceColors> }) {
  return (
    <View style={{ flex: 1, gap: 2 }}>
      <Text style={{ fontSize: 11, color: colors.textDim, fontWeight: '700', letterSpacing: 0.5 }}>{label.toUpperCase()}</Text>
      <Text style={{ fontSize: 16, color: colors.text, fontWeight: '700' }}>{value}</Text>
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
    fontWeight: '700',
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
  guardrailKicker: {
    fontSize: 11,
    fontWeight: '800',
    letterSpacing: 0.6,
    textTransform: 'uppercase',
  },
  guardrailPanel: {
    borderRadius: theme.radius.md,
    borderWidth: 0.5,
    gap: theme.spacing.xs,
    marginTop: theme.spacing.md,
    padding: theme.spacing.md,
  },
  guardrailValue: {
    fontSize: 15,
    fontWeight: '800',
    lineHeight: 20,
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
    justifyContent: 'center',
    paddingVertical: 8,
    paddingHorizontal: 16,
    borderRadius: theme.radius.pill,
    borderWidth: 0.5,
    borderColor: theme.colors.border,
    backgroundColor: 'transparent',
    flex: 1,
  },
  primaryText: {
    color: theme.colors.accent,
    fontSize: 12,
    fontWeight: '700',
    letterSpacing: 0.5,
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
    justifyContent: 'center',
    paddingVertical: 8,
    paddingHorizontal: 16,
    borderRadius: theme.radius.pill,
    borderWidth: 0.5,
    borderColor: theme.colors.border,
    backgroundColor: 'transparent',
  },
  secondaryText: {
    color: theme.colors.textSoft,
    fontSize: 12,
    fontWeight: '700',
  },
  summaryRow: {
    flexDirection: 'row',
    gap: theme.spacing.sm,
    marginTop: theme.spacing.lg,
  },
});
