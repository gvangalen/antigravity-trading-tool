import { Pressable, StyleSheet, Text, View } from 'react-native';

import { StatusTone, statusTones, theme } from '../../constants/theme';
import { triggerHaptic } from '../../utils/haptics';
import { CardShell } from './CardShell';

type ActionCardProps = {
  title: string;
  reason: string;
  impact: string;
  primaryAction: string;
  secondaryAction?: string;
  tone?: StatusTone;
  onPrimary?: () => void;
  onSecondary?: () => void;
};

export function ActionCard({
  title,
  reason,
  impact,
  primaryAction,
  secondaryAction = 'Ask why',
  tone = 'accent',
  onPrimary,
  onSecondary,
}: ActionCardProps) {
  const palette = statusTones[tone];

  return (
    <CardShell>
      <Text style={[styles.label, { color: palette.color }]}>Suggested action</Text>
      <Text style={styles.title}>{title}</Text>
      <Text style={styles.reason}>{reason}</Text>
      <View style={[styles.impactBox, { backgroundColor: palette.background, borderColor: palette.border }]}>
        <Text style={[styles.impactLabel, { color: palette.color }]}>Impact</Text>
        <Text style={styles.impactText}>{impact}</Text>
      </View>
      <View style={styles.actions}>
        <Pressable
          onPress={async () => {
            await triggerHaptic('impact');
            onPrimary?.();
          }}
          style={({ pressed }) => [styles.primaryButton, { backgroundColor: palette.color }, pressed && styles.pressed]}
        >
          <Text style={styles.primaryText}>{primaryAction}</Text>
        </Pressable>
        <Pressable
          onPress={async () => {
            await triggerHaptic('selection');
            onSecondary?.();
          }}
          style={({ pressed }) => [styles.secondaryButton, pressed && styles.pressed]}
        >
          <Text style={styles.secondaryText}>{secondaryAction}</Text>
        </Pressable>
      </View>
    </CardShell>
  );
}

const styles = StyleSheet.create({
  actions: {
    flexDirection: 'row',
    gap: theme.spacing.sm,
    marginTop: theme.spacing.lg,
  },
  impactBox: {
    borderRadius: theme.radius.md,
    borderWidth: 1,
    marginTop: theme.spacing.md,
    padding: theme.spacing.md,
  },
  impactLabel: {
    fontSize: theme.typography.label,
    fontWeight: '900',
    letterSpacing: 1.5,
    textTransform: 'uppercase',
  },
  impactText: {
    color: theme.colors.textSoft,
    fontSize: theme.typography.small,
    fontWeight: '700',
    lineHeight: 20,
    marginTop: 4,
  },
  label: {
    fontSize: theme.typography.label,
    fontWeight: '900',
    letterSpacing: 1.7,
    textTransform: 'uppercase',
  },
  pressed: {
    opacity: 0.86,
    transform: [{ scale: 0.99 }],
  },
  primaryButton: {
    alignItems: 'center',
    borderRadius: theme.radius.button,
    flex: 1,
    justifyContent: 'center',
    minHeight: 48,
    paddingHorizontal: theme.spacing.md,
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
    marginTop: theme.spacing.sm,
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
  title: {
    color: theme.colors.text,
    fontSize: theme.typography.title,
    fontWeight: '900',
    lineHeight: 27,
    marginTop: theme.spacing.sm,
  },
});
