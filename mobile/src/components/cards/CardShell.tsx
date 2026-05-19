import { ReactNode } from 'react';
import { StyleSheet, View } from 'react-native';

import { theme } from '../../constants/theme';
import { preferenceColors, useAppPreferences } from '../../preferences/AppPreferencesProvider';

type CardShellProps = {
  children: ReactNode;
  emphasis?: 'primary' | 'standard' | 'muted';
  flat?: boolean;
  edgeToEdge?: boolean;
};

export function CardShell({ children, emphasis = 'standard', flat = false, edgeToEdge = false }: CardShellProps) {
  const { appearance } = useAppPreferences();
  const colors = preferenceColors(appearance);

  return (
    <View
      style={[
        styles.card,
        { borderColor: colors.border },
        emphasis === 'primary' && styles.primary,
        emphasis === 'primary' && { borderColor: colors.borderStrong },
        emphasis === 'muted' && styles.muted,
        emphasis === 'muted' && { borderColor: colors.borderSubtle },
        flat && styles.flat,
        edgeToEdge && styles.edgeToEdge,
      ]}
    >
      {children}
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: 'transparent',
    borderColor: theme.colors.border,
    borderRadius: theme.radius.card,
    borderWidth: 0.5,
    padding: theme.spacing.md,
    marginBottom: theme.spacing.md,
  },
  muted: {
    backgroundColor: 'transparent',
  },
  primary: {
    backgroundColor: 'transparent',
    borderColor: theme.colors.border,
    borderWidth: 0.5,
  },
  flat: {
    borderWidth: 0,
    borderRadius: 0,
    backgroundColor: 'transparent',
    paddingHorizontal: 0,
  },
  edgeToEdge: {
    borderRadius: 0,
    borderLeftWidth: 0,
    borderRightWidth: 0,
    paddingHorizontal: theme.spacing.md,
  },
});
