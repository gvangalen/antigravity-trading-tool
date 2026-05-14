import { ReactNode } from 'react';
import { StyleSheet, View } from 'react-native';

import { theme } from '../../constants/theme';
import { preferenceColors, useAppPreferences } from '../../preferences/AppPreferencesProvider';

type CardShellProps = {
  children: ReactNode;
  emphasis?: 'primary' | 'standard' | 'muted';
};

export function CardShell({ children, emphasis = 'standard' }: CardShellProps) {
  const { appearance } = useAppPreferences();
  const colors = preferenceColors(appearance);

  return (
    <View
      style={[
        styles.card,
        { backgroundColor: colors.surface, borderColor: colors.border },
        emphasis === 'primary' && styles.primary,
        emphasis === 'primary' && { backgroundColor: colors.surfaceElevated, borderColor: colors.borderStrong },
        emphasis === 'muted' && styles.muted,
        emphasis === 'muted' && { backgroundColor: colors.backgroundSoft },
      ]}
    >
      {children}
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: theme.colors.surface,
    borderColor: theme.colors.border,
    borderRadius: theme.radius.card,
    borderWidth: 1,
    padding: theme.spacing.lg,
  },
  muted: {
    backgroundColor: theme.colors.backgroundSoft,
  },
  primary: {
    backgroundColor: theme.colors.surfaceElevated,
    borderColor: theme.colors.borderStrong,
    borderWidth: 1.5,
  },
});
