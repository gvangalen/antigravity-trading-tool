import { Pressable, StyleSheet, Text, View } from 'react-native';

import { preferenceColors, useAppPreferences } from '../../preferences/AppPreferencesProvider';
import { theme } from '../../constants/theme';
import { triggerHaptic } from '../../utils/haptics';
import { StatusChip } from '../layout/StatusChip';
import { CardShell } from './CardShell';

type StrategyStatusCardProps = {
  symbol: string;
  bias: string;
  confidence: number;
  status: string;
  entryZone: string;
  targets: string[];
  invalidation: string;
  explanation: string;
  onPress?: () => void;
};

export function StrategyStatusCard({
  symbol,
  bias,
  confidence,
  status,
  entryZone,
  targets,
  invalidation,
  explanation,
  onPress,
}: StrategyStatusCardProps) {
  const { appearance } = useAppPreferences();
  const colors = preferenceColors(appearance);

  return (
    <Pressable
      onPress={async () => {
        await triggerHaptic('selection');
        onPress?.();
      }}
      style={({ pressed }) => pressed && styles.pressed}
    >
      <CardShell>
        <View style={styles.header}>
          <View>
            <Text style={styles.label}>Active strategy</Text>
            <Text style={[styles.symbol, { color: colors.text }]}>{symbol}</Text>
            <Text style={[styles.bias, { color: colors.textDim }]}>{bias}</Text>
          </View>
          <View style={[styles.confidence, { backgroundColor: appearance === 'light' ? '#EFF6FF' : theme.colors.accentSoft }]}>
            <Text style={[styles.confidenceValue, { color: colors.text }]}>{confidence}</Text>
            <Text style={[styles.confidenceLabel, { color: colors.textDim }]}>confidence</Text>
          </View>
        </View>
        <View style={styles.statusRow}>
          <StatusChip label={status} tone="warning" />
        </View>
        <View style={styles.grid}>
          <Metric label="Entry" value={entryZone} colors={colors} />
          <Metric label="Targets" value={targets.join(' / ')} colors={colors} />
          <Metric label="Invalidation" value={invalidation} colors={colors} />
        </View>
        <Text style={[styles.explanation, { color: colors.textMuted }]}>{explanation}</Text>
      </CardShell>
    </Pressable>
  );
}

function Metric({ label, value, colors }: { label: string; value: string; colors: ReturnType<typeof preferenceColors> }) {
  return (
    <View style={[styles.metric, { backgroundColor: colors.backgroundSoft, borderColor: colors.border }]}>
      <Text style={[styles.metricLabel, { color: colors.textDim }]}>{label}</Text>
      <Text style={[styles.metricValue, { color: colors.text }]}>{value}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  bias: {
    color: theme.colors.textDim,
    fontSize: theme.typography.small,
    fontWeight: '700',
    marginTop: 4,
  },
  confidence: {
    alignItems: 'center',
    backgroundColor: theme.colors.accentSoft,
    borderColor: '#1D4ED880',
    borderRadius: theme.radius.md,
    borderWidth: 1,
    minWidth: 82,
    padding: theme.spacing.sm,
  },
  confidenceLabel: {
    color: theme.colors.textDim,
    fontSize: 10,
    fontWeight: '900',
    marginTop: 2,
  },
  confidenceValue: {
    color: theme.colors.text,
    fontSize: 27,
    fontWeight: '900',
  },
  explanation: {
    color: theme.colors.textMuted,
    fontSize: theme.typography.body,
    fontWeight: '600',
    lineHeight: 22,
    marginTop: theme.spacing.md,
  },
  grid: {
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
  metric: {
    backgroundColor: theme.colors.backgroundSoft,
    borderColor: theme.colors.border,
    borderRadius: theme.radius.md,
    borderWidth: 1,
    padding: theme.spacing.md,
  },
  metricLabel: {
    color: theme.colors.textDim,
    fontSize: theme.typography.label,
    fontWeight: '900',
    letterSpacing: 1.5,
    textTransform: 'uppercase',
  },
  metricValue: {
    color: theme.colors.text,
    fontSize: theme.typography.body,
    fontWeight: '900',
    marginTop: 5,
  },
  pressed: {
    opacity: 0.86,
  },
  statusRow: {
    marginTop: theme.spacing.md,
  },
  symbol: {
    color: theme.colors.text,
    fontSize: 28,
    fontWeight: '900',
    marginTop: 5,
  },
});
