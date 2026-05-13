import { ReactNode } from 'react';
import { StyleSheet, View } from 'react-native';

import { theme } from '../../constants/theme';

type CardShellProps = {
  children: ReactNode;
  emphasis?: 'primary' | 'standard' | 'muted';
};

export function CardShell({ children, emphasis = 'standard' }: CardShellProps) {
  return (
    <View
      style={[
        styles.card,
        emphasis === 'primary' && styles.primary,
        emphasis === 'muted' && styles.muted,
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
