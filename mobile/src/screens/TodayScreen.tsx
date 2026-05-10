import { useEffect, useState } from 'react';
import { ActivityIndicator, ScrollView, StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { ScoreCard } from '../components/ScoreCard';
import { theme } from '../constants/theme';
import { getTodayScores } from '../services/mockDataService';
import { TodayScores } from '../types/scores';

export function TodayScreen() {
  const [todayScores, setTodayScores] = useState<TodayScores | null>(null);

  useEffect(() => {
    async function loadScores() {
      const scores = await getTodayScores();
      setTodayScores(scores);
    }

    loadScores();
  }, []);

  return (
    <SafeAreaView style={styles.safeArea}>
      <ScrollView contentContainerStyle={styles.content}>
        <Text style={styles.title}>Today</Text>
        <Text style={styles.subtitle}>Compact marktbeeld voor mobiele besluitvorming.</Text>

        {!todayScores ? (
          <View style={styles.loading}>
            <ActivityIndicator color={theme.colors.accent} />
          </View>
        ) : (
          <>
            <View style={styles.scoreGrid}>
              {todayScores.scores.map((score) => (
                <ScoreCard key={score.label} score={score} />
              ))}
            </View>

            <View style={styles.summaryCard}>
              <Text style={styles.summaryTitle}>AI Summary</Text>
              <Text style={styles.summaryText}>{todayScores.aiSummary}</Text>
            </View>
          </>
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
    minHeight: 240,
  },
  safeArea: {
    backgroundColor: theme.colors.background,
    flex: 1,
  },
  scoreGrid: {
    gap: theme.spacing.md,
  },
  subtitle: {
    color: theme.colors.textMuted,
    fontSize: 15,
    lineHeight: 22,
  },
  summaryCard: {
    backgroundColor: theme.colors.surfaceElevated,
    borderColor: theme.colors.border,
    borderRadius: theme.radius.card,
    borderWidth: 1,
    marginTop: theme.spacing.sm,
    padding: theme.spacing.lg,
  },
  summaryText: {
    color: theme.colors.textSoft,
    fontSize: 16,
    lineHeight: 24,
    marginTop: theme.spacing.sm,
  },
  summaryTitle: {
    color: theme.colors.text,
    fontSize: 19,
    fontWeight: '900',
  },
  title: {
    color: theme.colors.text,
    fontSize: 34,
    fontWeight: '900',
    letterSpacing: 0,
  },
});
