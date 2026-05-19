import { ReactNode, useCallback, useState } from 'react';
import { RefreshControl, ScrollView, StyleSheet, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { theme } from '../../constants/theme';
import { preferenceColors, useAppPreferences } from '../../preferences/AppPreferencesProvider';
import { triggerHaptic } from '../../utils/haptics';

type ScreenContainerProps = {
  children: ReactNode;
  scroll?: boolean;
  refreshingEnabled?: boolean;
  contentInsetBottom?: number;
  refreshing?: boolean;
  onRefresh?: () => Promise<void> | void;
  edgeToEdge?: boolean;
};

export function ScreenContainer({
  children,
  scroll = true,
  refreshingEnabled = true,
  contentInsetBottom = 112,
  refreshing: externalRefreshing,
  onRefresh,
  edgeToEdge = false,
}: ScreenContainerProps) {
  const { appearance } = useAppPreferences();
  const colors = preferenceColors(appearance);
  const [refreshing, setRefreshing] = useState(false);
  const isRefreshing = externalRefreshing ?? refreshing;

  const handleRefresh = useCallback(async () => {
    if (!refreshingEnabled) return;
    if (onRefresh) {
      await triggerHaptic('selection');
      await onRefresh();
      return;
    }
    setRefreshing(true);
    await triggerHaptic('selection');
    setTimeout(() => setRefreshing(false), 700);
  }, [onRefresh, refreshingEnabled]);

  if (!scroll) {
    return (
    <SafeAreaView edges={['top']} style={[styles.safeArea, { backgroundColor: colors.background }]}>
        <View style={[styles.staticContent, { backgroundColor: colors.background }, edgeToEdge && { paddingHorizontal: 0 }]}>{children}</View>
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView edges={['top']} style={[styles.safeArea, { backgroundColor: colors.background }]}>
      <ScrollView
        contentContainerStyle={[styles.content, { paddingBottom: contentInsetBottom }, edgeToEdge && { paddingHorizontal: 0 }]}
        keyboardShouldPersistTaps="handled"
        refreshControl={
          <RefreshControl
            refreshing={isRefreshing}
            tintColor={theme.colors.accent}
            onRefresh={handleRefresh}
          />
        }
        showsVerticalScrollIndicator={false}
      >
        {children}
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  content: {
    gap: theme.spacing.lg,
    paddingHorizontal: theme.spacing.lg,
    paddingTop: theme.spacing.md,
  },
  safeArea: {
    backgroundColor: theme.colors.background,
    flex: 1,
  },
  staticContent: {
    backgroundColor: theme.colors.background,
    flex: 1,
    paddingHorizontal: theme.spacing.lg,
    paddingTop: theme.spacing.md,
  },
});
