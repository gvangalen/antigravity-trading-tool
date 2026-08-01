import { ReactNode } from 'react';
import { StyleProp, StyleSheet, View, ViewStyle } from 'react-native';

import { theme } from '../../constants/theme';
import { preferenceColors, useAppPreferences } from '../../preferences/AppPreferencesProvider';

type CardShellProps = {
  children: ReactNode;
  emphasis?: 'primary' | 'standard' | 'muted';
  flat?: boolean;
  edgeToEdge?: boolean;
  style?: StyleProp<ViewStyle>;
};

export function CardShell({
  children,
  emphasis = 'standard',
  flat = false,
  edgeToEdge = false,
  style,
}: CardShellProps) {
  const { appearance } = useAppPreferences();
  const colors = preferenceColors(appearance);

  return (
    <View
      style={[
        styles.card,
        {
          backgroundColor: colors.surface,
          borderColor: colors.border,
          shadowColor: appearance === 'light' ? '#0F172A' : '#000000',
          shadowOpacity: appearance === 'light' ? 0.035 : 0,
          shadowRadius: appearance === 'light' ? 14 : 0,
          shadowOffset: { width: 0, height: 6 },
          elevation: appearance === 'light' ? 1 : 0,
        },
        emphasis === 'primary' && styles.primary,
        emphasis === 'primary' && { borderColor: colors.borderStrong },
        emphasis === 'muted' && styles.muted,
        emphasis === 'muted' && { borderColor: colors.borderSubtle },
        flat && styles.flat,
        edgeToEdge && styles.edgeToEdge,
        style,
      ]}
    >
      {children}
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    borderColor: theme.colors.border,
    borderRadius: 22,
    borderWidth: 1,
    marginBottom: 12,
    padding: 16,
  },
  muted: {
    backgroundColor: 'transparent',
  },
  primary: {
    borderColor: theme.colors.border,
    borderWidth: 1,
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
