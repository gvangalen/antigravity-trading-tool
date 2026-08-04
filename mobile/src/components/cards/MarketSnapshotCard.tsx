import { StyleSheet, Text, View } from 'react-native';

import { StatusTone, statusTones, theme } from '../../constants/theme';
import { StatusChip } from '../layout/StatusChip';
import { CardShell } from './CardShell';

type MarketSnapshotCardProps = {
  symbol: string;
  price: string;
  change24h: string;
  volume: string;
  interpretation: string;
  tone?: StatusTone;
};

export function MarketSnapshotCard({
  symbol,
  price,
  change24h,
  volume,
  interpretation,
  tone = 'neutral',
}: MarketSnapshotCardProps) {
  const palette = statusTones[tone];

  return (
    <CardShell>
      <View style={styles.header}>
        <View>
          <Text style={styles.label}>Market snapshot</Text>
          <Text style={styles.symbol}>{symbol}</Text>
        </View>
        <StatusChip compact label={change24h} tone={tone} />
      </View>
      <Text style={[styles.price, { color: palette.color }]}>{price}</Text>
      <View style={styles.row}>
        <Text style={styles.metaLabel}>Volume</Text>
        <Text style={styles.metaValue}>{volume}</Text>
      </View>
      <Text style={styles.interpretation}>{interpretation}</Text>
    </CardShell>
  );
}

const styles = StyleSheet.create({
  header: {
    alignItems: 'flex-start',
    flexDirection: 'row',
    justifyContent: 'space-between',
  },
  interpretation: {
    color: theme.colors.textMuted,
    fontSize: theme.typography.body,
    fontWeight: '600',
    lineHeight: 22,
    marginTop: theme.spacing.md,
  },
  label: {
    color: theme.colors.textDim,
    fontSize: theme.typography.label,
    fontWeight: '900',
    letterSpacing: 1.6,
    textTransform: 'uppercase',
  },
  metaLabel: {
    color: theme.colors.textDim,
    fontSize: theme.typography.label,
    fontWeight: '900',
    letterSpacing: 1.4,
    textTransform: 'uppercase',
  },
  metaValue: {
    color: theme.colors.text,
    fontSize: theme.typography.small,
    fontWeight: '900',
  },
  price: {
    fontSize: 22,
    fontWeight: '900',
    letterSpacing: 0,
    marginTop: theme.spacing.md,
  },
  row: {
    alignItems: 'center',
    borderTopColor: theme.colors.border,
    borderTopWidth: 1,
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginTop: theme.spacing.md,
    paddingTop: theme.spacing.md,
  },
  symbol: {
    color: theme.colors.text,
    fontSize: theme.typography.cardTitle,
    fontWeight: '900',
    marginTop: 4,
  },
});
