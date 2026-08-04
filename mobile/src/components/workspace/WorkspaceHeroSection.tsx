import type { ReactNode } from 'react';
import { StyleSheet, View } from 'react-native';

import { theme } from '../../constants/theme';

type WorkspaceHeroSectionProps = {
  children: ReactNode;
};

export function WorkspaceHeroSection({ children }: WorkspaceHeroSectionProps) {
  return <View style={styles.container}>{children}</View>;
}

const styles = StyleSheet.create({
  container: {
    marginTop: 0,
    paddingHorizontal: 0,
    paddingTop: theme.spacing.xxs,
    width: '100%',
  },
});
