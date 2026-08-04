import { useEffect, useState } from 'react';
import { ActivityIndicator, ScrollView, StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { StrategyCard } from '../components/StrategyCard';
import { theme } from '../constants/theme';
import { useApiResource } from '../hooks/useApiResource';
import { intelligenceApi } from '../services/tradamindApi';
import { mapStrategy } from '../services/dataMappers';
import { useCallback } from 'react';
import { Strategy } from '../types/strategy';
import { trackAssistantEvent } from '../services/assistantAnalytics';

export function StrategyScreen() {
  const fetchStrategy = useCallback(() => intelligenceApi.activeStrategyToday(), []);
  const { data, loading, error } = useApiResource({
    fetcher: fetchStrategy,
    fallbackData: undefined
  });

  useEffect(() => {
    trackAssistantEvent({
      event_name: 'screen_view',
      page: 'strategy',
      flow_type: 'strategy',
    });
  }, []);
  
  const rawStrategy = mapStrategy(data);
  const strategy = data ? {
    symbol: rawStrategy.symbol,
    bias: rawStrategy.bias,
    entryZone: rawStrategy.entryZone,
    targets: rawStrategy.targets,
    stopLoss: rawStrategy.invalidation,
    confidenceScore: rawStrategy.confidence,
    aiExplanation: rawStrategy.explanation
  } : null;

  return (
    <SafeAreaView style={styles.safeArea}>
      <ScrollView contentContainerStyle={styles.content}>
        <Text style={styles.title}>Strategy</Text>
        <Text style={styles.subtitle}>Actieve strategie, samengevat voor mobiel gebruik.</Text>

        {loading || !strategy ? (
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
    fontSize: 26,
    fontWeight: '900',
    letterSpacing: 0,
  },
});
