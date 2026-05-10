import { StyleSheet, Text, View } from 'react-native';

import { theme } from '../constants/theme';
import { Strategy } from '../types/strategy';

type StrategyCardProps = {
  strategy: Strategy;
};

export function StrategyCard({ strategy }: StrategyCardProps) {
  return (
    <View style={styles.card}>
      <View style={styles.header}>
        <View>
          <Text style={styles.symbol}>{strategy.symbol}</Text>
          <Text style={styles.bias}>{strategy.bias}</Text>
        </View>
        <View style={styles.confidence}>
          <Text style={styles.confidenceValue}>{strategy.confidenceScore}</Text>
          <Text style={styles.confidenceLabel}>confidence</Text>
        </View>
      </View>

      <View style={styles.divider} />
      <Text style={styles.metaLabel}>Entry zone</Text>
      <Text style={styles.metaValue}>{strategy.entryZone}</Text>

      <Text style={styles.metaLabel}>Targets</Text>
      <Text style={styles.metaValue}>{strategy.targets.join(' / ')}</Text>

      <Text style={styles.metaLabel}>Stop loss</Text>
      <Text style={styles.metaValue}>{strategy.stopLoss}</Text>

      <View style={styles.explanationBox}>
        <Text style={styles.explanationTitle}>AI explanation</Text>
        <Text style={styles.explanation}>{strategy.aiExplanation}</Text>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  bias: {
    color: theme.colors.textMuted,
    fontSize: 15,
    marginTop: 4,
  },
  card: {
    backgroundColor: theme.colors.surface,
    borderColor: theme.colors.border,
    borderRadius: theme.radius.card,
    borderWidth: 1,
    padding: theme.spacing.lg,
  },
  confidence: {
    alignItems: 'center',
    backgroundColor: theme.colors.accentSoft,
    borderColor: theme.colors.accent,
    borderRadius: theme.radius.card,
    borderWidth: 1,
    minWidth: 88,
    padding: theme.spacing.sm,
  },
  confidenceLabel: {
    color: theme.colors.textMuted,
    fontSize: 11,
    fontWeight: '700',
    marginTop: 2,
  },
  confidenceValue: {
    color: theme.colors.text,
    fontSize: 26,
    fontWeight: '900',
  },
  divider: {
    backgroundColor: theme.colors.border,
    height: 1,
    marginVertical: theme.spacing.lg,
  },
  explanation: {
    color: theme.colors.textSoft,
    fontSize: 15,
    lineHeight: 23,
    marginTop: theme.spacing.xs,
  },
  explanationBox: {
    backgroundColor: theme.colors.surfaceElevated,
    borderRadius: theme.radius.card,
    marginTop: theme.spacing.lg,
    padding: theme.spacing.md,
  },
  explanationTitle: {
    color: theme.colors.text,
    fontSize: 15,
    fontWeight: '900',
  },
  header: {
    alignItems: 'flex-start',
    flexDirection: 'row',
    gap: theme.spacing.md,
    justifyContent: 'space-between',
  },
  metaLabel: {
    color: theme.colors.textMuted,
    fontSize: 12,
    fontWeight: '800',
    marginTop: theme.spacing.md,
    textTransform: 'uppercase',
  },
  metaValue: {
    color: theme.colors.text,
    fontSize: 17,
    fontWeight: '800',
    marginTop: 4,
  },
  symbol: {
    color: theme.colors.text,
    fontSize: 28,
    fontWeight: '900',
  },
});
