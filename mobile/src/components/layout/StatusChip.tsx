import { StyleSheet, Text, View } from 'react-native';

import { StatusTone, theme } from '../../constants/theme';
import { typography } from '../../constants/typography';
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
  const background = appearance === 'light' ? `${baseColor}08` : `${baseColor}15`;
  const border = appearance === 'light' ? `${baseColor}20` : `${baseColor}30`;

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
    gap: 3,
    maxWidth: '100%',
    minHeight: 26,
    paddingHorizontal: 8,
    paddingVertical: 3,
  },
  compact: {
    minHeight: 22,
    paddingHorizontal: 6,
    paddingVertical: 1,
  },
  dot: {
    borderRadius: theme.radius.pill,
    height: 3,
    width: 3,
  },
  label: {
    ...typography.chipLabelCompact,
  },
});
