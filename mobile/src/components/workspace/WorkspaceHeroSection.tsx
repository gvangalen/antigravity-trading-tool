import type { ReactNode } from 'react';
import { StyleSheet, View } from 'react-native';

type WorkspaceHeroSectionProps = {
  children: ReactNode;
};

export function WorkspaceHeroSection({ children }: WorkspaceHeroSectionProps) {
  return <View style={styles.container}>{children}</View>;
}

const styles = StyleSheet.create({
  container: {
    marginTop: 0,
    paddingHorizontal: 8,
    paddingTop: 8,
    width: '100%',
  },
});
