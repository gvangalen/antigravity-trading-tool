import { Pressable, StyleSheet, Text, View } from 'react-native';

import { StatusTone, theme } from '../../constants/theme';
import { preferenceColors, useAppPreferences } from '../../preferences/AppPreferencesProvider';
import { CardShell } from '../cards/CardShell';
import { StatusChip } from '../layout/StatusChip';
import { triggerHaptic } from '../../utils/haptics';

type WorkspaceBriefingCardProps = {
  lane: string;
  headline: string;
  summary: string;
  statusLabel: string;
  statusTone?: StatusTone;
  primaryActionLabel?: string;
  onPrimaryAction?: () => void;
  metrics?: Array<{ label: string; value: string }>;
};

export function WorkspaceBriefingCard({
  lane,
  headline,
  summary,
  statusLabel,
  statusTone = 'accent',
  primaryActionLabel,
  onPrimaryAction,
  metrics = [],
}: WorkspaceBriefingCardProps) {
  const { appearance } = useAppPreferences();
  const colors = preferenceColors(appearance);

  return (
    <CardShell emphasis="primary" edgeToEdge={true}>
      <View style={styles.topRow}>
        <View style={styles.copyBlock}>
          <Text style={styles.kicker}>FINN WORKSPACE</Text>
          <Text style={[styles.lane, { color: colors.text }]}>{lane}</Text>
        </View>
        <StatusChip compact label={statusLabel} tone={statusTone} />
      </View>

      <Text style={[styles.headline, { color: colors.text }]}>{headline}</Text>
      <Text style={[styles.summary, { color: colors.textMuted }]}>{summary}</Text>

      {metrics.length > 0 ? (
        <View style={styles.metricRow}>
          {metrics.slice(0, 3).map((metric) => (
            <View
              key={`${metric.label}-${metric.value}`}
              style={[styles.metricCard, { borderColor: colors.border, backgroundColor: colors.backgroundSoft }]}
            >
              <Text style={styles.metricLabel}>{metric.label}</Text>
              <Text style={[styles.metricValue, { color: colors.text }]}>{metric.value}</Text>
            </View>
          ))}
        </View>
      ) : null}

      {primaryActionLabel && onPrimaryAction ? (
        <Pressable
          onPress={async () => {
            await triggerHaptic('impact');
            onPrimaryAction();
          }}
          style={({ pressed }) => [
            styles.primaryButton,
            { backgroundColor: theme.colors.accent },
            pressed && styles.pressed,
          ]}
        >
          <Text style={styles.primaryButtonText}>{primaryActionLabel}</Text>
        </Pressable>
      ) : null}
    </CardShell>
  );
}

const styles = StyleSheet.create({
  copyBlock: {
    flex: 1,
    gap: 3,
  },
  headline: {
    fontSize: 18,
    fontWeight: '900',
    letterSpacing: -0.3,
    lineHeight: 23,
    marginTop: theme.spacing.md,
  },
  kicker: {
    color: theme.colors.accent,
    fontSize: theme.typography.label,
    fontWeight: '900',
    letterSpacing: 1.8,
    textTransform: 'uppercase',
  },
  lane: {
    fontSize: 14,
    fontWeight: '800',
  },
  metricCard: {
    borderRadius: theme.radius.md,
    borderWidth: 0.5,
    flex: 1,
    gap: 3,
    paddingHorizontal: theme.spacing.md,
    paddingVertical: theme.spacing.sm,
  },
  metricLabel: {
    color: theme.colors.textDim,
    fontSize: 10,
    fontWeight: '800',
    letterSpacing: 0.8,
    textTransform: 'uppercase',
  },
  metricRow: {
    flexDirection: 'row',
    gap: theme.spacing.sm,
    marginTop: theme.spacing.lg,
  },
  metricValue: {
    fontSize: 14,
    fontWeight: '800',
  },
  pressed: {
    opacity: 0.86,
    transform: [{ scale: 0.99 }],
  },
  primaryButton: {
    alignItems: 'center',
    borderRadius: theme.radius.pill,
    justifyContent: 'center',
    marginTop: theme.spacing.lg,
    paddingHorizontal: 16,
    paddingVertical: 11,
  },
  primaryButtonText: {
    color: '#ffffff',
    fontSize: 11,
    fontWeight: '900',
    letterSpacing: 0.8,
    textTransform: 'uppercase',
  },
  summary: {
    fontSize: theme.typography.body,
    fontWeight: '600',
    lineHeight: 22,
    marginTop: theme.spacing.sm,
  },
  topRow: {
    alignItems: 'center',
    flexDirection: 'row',
    gap: theme.spacing.md,
    justifyContent: 'space-between',
  },
});
