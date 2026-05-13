import { StyleSheet, Text, View } from 'react-native';

import { StatusTone, theme } from '../../constants/theme';
import { StatusChip } from './StatusChip';

type DataFreshnessIndicatorProps = {
  updatedAt: string;
  state?: 'live' | 'syncing' | 'stale';
};

const toneByState: Record<NonNullable<DataFreshnessIndicatorProps['state']>, StatusTone> = {
  live: 'success',
  syncing: 'accent',
  stale: 'warning',
};

export function DataFreshnessIndicator({ updatedAt, state = 'live' }: DataFreshnessIndicatorProps) {
  return (
    <View style={styles.container}>
      <StatusChip compact label={state} tone={toneByState[state]} />
      <Text style={styles.text}>Updated {updatedAt}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    alignItems: 'center',
    flexDirection: 'row',
    gap: theme.spacing.sm,
  },
  text: {
    color: theme.colors.textDim,
    fontSize: theme.typography.small,
    fontWeight: '700',
  },
});
