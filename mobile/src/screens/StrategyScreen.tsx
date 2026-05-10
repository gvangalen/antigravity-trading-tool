import { useEffect, useState } from 'react';
import { ActivityIndicator, ScrollView, StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { StrategyCard } from '../components/StrategyCard';
import { theme } from '../constants/theme';
import { getActiveStrategy } from '../services/mockDataService';
import { Strategy } from '../types/strategy';

export function StrategyScreen() {
  const [strategy, setStrategy] = useState<Strategy | null>(null);

  useEffect(() => {
    async function loadStrategy() {
      const activeStrategy = await getActiveStrategy();
      setStrategy(activeStrategy);
    }

    loadStrategy();
  }, []);

  return (
    <SafeAreaView style={styles.safeArea}>
      <ScrollView contentContainerStyle={styles.content}>
        <Text style={styles.title}>Strategy</Text>
        <Text style={styles.subtitle}>Actieve strategie, samengevat voor mobiel gebruik.</Text>

        {!strategy ? (
          <View style={styles.loading}>
            <ActivityIndicator color={theme.colors.accent} />
          </View>
        ) : (
          <StrategyCard strategy={strategy} />
        )}
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  content: {
    gap: theme.spacing.md,
    padding: theme.spacing.lg,
    paddingBottom: theme.spacing.xl,
  },
  loading: {
    alignItems: 'center',
    justifyContent: 'center',
    minHeight: 260,
  },
  safeArea: {
    backgroundColor: theme.colors.background,
    flex: 1,
  },
  subtitle: {
    color: theme.colors.textMuted,
    fontSize: 15,
    lineHeight: 22,
  },
  title: {
    color: theme.colors.text,
    fontSize: 34,
    fontWeight: '900',
    letterSpacing: 0,
  },
});
