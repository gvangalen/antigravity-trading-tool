import { StyleSheet, Text, View } from 'react-native';

import { StatusTone, statusTones, theme } from '../../constants/theme';

type StatusChipProps = {
  label: string;
  tone?: StatusTone;
  compact?: boolean;
};

export function StatusChip({ label, tone = 'neutral', compact = false }: StatusChipProps) {
  const palette = statusTones[tone];

  return (
    <View
      style={[
        styles.chip,
        compact && styles.compact,
        { backgroundColor: palette.background, borderColor: palette.border },
      ]}
    >
      <View style={[styles.dot, { backgroundColor: palette.color }]} />
      <Text style={[styles.label, { color: palette.color }]} numberOfLines={1}>
        {label}
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  chip: {
    alignItems: 'center',
    alignSelf: 'flex-start',
    borderRadius: theme.radius.pill,
    borderWidth: 1,
    flexDirection: 'row',
    gap: theme.spacing.xs,
    maxWidth: '100%',
    paddingHorizontal: theme.spacing.sm,
    paddingVertical: 7,
  },
  compact: {
    paddingHorizontal: 8,
    paddingVertical: 5,
  },
  dot: {
    borderRadius: theme.radius.pill,
    height: 6,
    width: 6,
  },
  label: {
    fontSize: theme.typography.label,
    fontWeight: '900',
    letterSpacing: 1,
    textTransform: 'uppercase',
  },
});
