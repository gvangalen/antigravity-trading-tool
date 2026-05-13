import { Animated, StyleSheet, View } from 'react-native';

import { theme } from '../../constants/theme';

export function LoadingSkeletonCard() {
  return (
    <View style={styles.card}>
      <Animated.View style={[styles.line, styles.short]} />
      <Animated.View style={[styles.line, styles.long]} />
      <Animated.View style={[styles.line, styles.medium]} />
      <View style={styles.row}>
        <View style={styles.block} />
        <View style={styles.block} />
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  block: {
    backgroundColor: theme.colors.surfaceMuted,
    borderRadius: theme.radius.md,
    flex: 1,
    height: 46,
  },
  card: {
    backgroundColor: theme.colors.surface,
    borderColor: theme.colors.border,
    borderRadius: theme.radius.card,
    borderWidth: 1,
    gap: theme.spacing.md,
    overflow: 'hidden',
    padding: theme.spacing.lg,
  },
  line: {
    backgroundColor: theme.colors.surfaceMuted,
    borderRadius: theme.radius.pill,
    height: 12,
  },
  long: {
    width: '88%',
  },
  medium: {
    width: '62%',
  },
  row: {
    flexDirection: 'row',
    gap: theme.spacing.md,
    marginTop: theme.spacing.xs,
  },
  short: {
    width: '34%',
  },
});
