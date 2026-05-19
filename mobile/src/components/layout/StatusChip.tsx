import { StyleSheet, Text, View } from 'react-native';

import { StatusTone, theme } from '../../constants/theme';
import { preferenceColors, useAppPreferences } from '../../preferences/AppPreferencesProvider';

type StatusChipProps = {
  label: string;
  tone?: StatusTone;
  compact?: boolean;
};

export function StatusChip({ label, tone = 'neutral', compact = false }: StatusChipProps) {
  const { appearance } = useAppPreferences();
  const colors = preferenceColors(appearance);

  // Fallback to textDim if tone is neutral, or accent if tone is not found
  const baseColor = tone === 'neutral' ? colors.textDim : (colors[tone] || colors.accent);
  
  // Create light backgrounds and borders dynamically
  const background = `${baseColor}15`; // ~8% opacity
  const border = `${baseColor}30`; // ~19% opacity

  return (
    <View
      style={[
        styles.chip,
        compact && styles.compact,
        { backgroundColor: background, borderColor: border },
      ]}
    >
      <View style={[styles.dot, { backgroundColor: baseColor }]} />
      <Text style={[styles.label, { color: baseColor }]} numberOfLines={1}>
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
