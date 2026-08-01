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
    <SafeAreaView edges={[]} style={[styles.safeArea, { backgroundColor: colors.background }]}>
        <View
          style={[
            styles.staticContent,
            { backgroundColor: colors.background },
            edgeToEdge && { paddingHorizontal: 0 },
          ]}
        >
          {children}
        </View>
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView edges={[]} style={[styles.safeArea, { backgroundColor: colors.background }]}>
      <ScrollView
        automaticallyAdjustContentInsets={false}
        contentInsetAdjustmentBehavior="never"
        contentContainerStyle={[
          styles.content,
          { paddingBottom: contentInsetBottom },
          edgeToEdge && { paddingHorizontal: 0 },
        ]}
        keyboardShouldPersistTaps="handled"
        style={styles.scroll}
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
    alignItems: 'stretch',
    gap: 8,
    minWidth: '100%',
    width: '100%',
    paddingHorizontal: 0,
    paddingTop: 0,
  },
  scroll: {
    marginTop: 0,
  },
  safeArea: {
    backgroundColor: theme.colors.background,
    flex: 1,
  },
  staticContent: {
    alignItems: 'stretch',
    backgroundColor: theme.colors.background,
    flex: 1,
    minWidth: '100%',
    width: '100%',
    paddingHorizontal: 0,
    paddingTop: 0,
  },
});
