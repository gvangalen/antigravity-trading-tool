import { StyleSheet, Text, View } from 'react-native';

import { preferenceColors, useAppPreferences } from '../../preferences/AppPreferencesProvider';
import { theme } from '../../constants/theme';

type SectionHeaderProps = {
  label: string;
  title?: string;
  description?: string;
  compact?: boolean;
};

export function SectionHeader({ label, title, description, compact = false }: SectionHeaderProps) {
  const { appearance } = useAppPreferences();
  const colors = preferenceColors(appearance);

  return (
    <View style={[styles.container, compact && styles.compactContainer]}>
      <View style={styles.labelRow}>
        <View style={[styles.marker, compact && styles.compactMarker]} />
        <Text style={[styles.label, compact && styles.compactLabel]}>{label}</Text>
      </View>
      {title ? <Text style={[styles.title, { color: colors.text }, compact && styles.compactTitle]}>{title}</Text> : null}
      {description && !compact ? <Text style={styles.description}>{description}</Text> : null}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    gap: theme.spacing.xs,
    marginBottom: theme.spacing.md,
    paddingHorizontal: theme.spacing.lg,
  },
  compactContainer: {
    gap: 2,
    marginBottom: theme.spacing.sm,
  },
  description: {
    color: theme.colors.textDim,
    fontSize: theme.typography.body,
    fontWeight: '600',
    lineHeight: 22,
  },
  label: {
    color: theme.colors.textDim,
    fontSize: theme.typography.label,
    fontWeight: '900',
    letterSpacing: 2,
    textTransform: 'uppercase',
  },
  compactLabel: {
    fontSize: 10,
    letterSpacing: 1.5,
  },
  labelRow: {
    alignItems: 'center',
    flexDirection: 'row',
    gap: theme.spacing.sm,
  },
  marker: {
    backgroundColor: theme.colors.accent,
    borderRadius: theme.radius.pill,
    height: 16,
    width: 4,
  },
  compactMarker: {
    height: 12,
    width: 3,
  },
  title: {
    color: theme.colors.text,
    fontSize: theme.typography.screenTitle,
    fontWeight: '900',
    letterSpacing: 0,
    lineHeight: 36,
  },
  compactTitle: {
    fontSize: 20,
    lineHeight: 26,
  },
});
