import { StyleSheet, Text, View } from 'react-native';

import { theme } from '../../constants/theme';

type SectionHeaderProps = {
  label: string;
  title?: string;
  description?: string;
};

export function SectionHeader({ label, title, description }: SectionHeaderProps) {
  return (
    <View style={styles.container}>
      <View style={styles.labelRow}>
        <View style={styles.marker} />
        <Text style={styles.label}>{label}</Text>
      </View>
      {title ? <Text style={styles.title}>{title}</Text> : null}
      {description ? <Text style={styles.description}>{description}</Text> : null}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    gap: theme.spacing.xs,
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
  title: {
    color: theme.colors.text,
    fontSize: theme.typography.screenTitle,
    fontWeight: '900',
    letterSpacing: 0,
    lineHeight: 36,
  },
});
