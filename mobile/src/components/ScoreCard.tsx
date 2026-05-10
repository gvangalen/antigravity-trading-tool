import { StyleSheet, Text, View } from 'react-native';

import { theme } from '../constants/theme';
import { Score } from '../types/scores';

type ScoreCardProps = {
  score: Score;
};

export function ScoreCard({ score }: ScoreCardProps) {
  return (
    <View style={styles.card}>
      <View style={styles.header}>
        <Text style={styles.label}>{score.label}</Text>
        <Text style={styles.value}>{score.value}</Text>
      </View>
      <View style={styles.track}>
        <View style={[styles.fill, { width: `${score.value}%` }]} />
      </View>
      <Text style={styles.status}>{score.status}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: theme.colors.surface,
    borderColor: theme.colors.border,
    borderRadius: theme.radius.card,
    borderWidth: 1,
    padding: theme.spacing.md,
  },
  fill: {
    backgroundColor: theme.colors.accent,
    borderRadius: 3,
    height: 6,
  },
  header: {
    alignItems: 'center',
    flexDirection: 'row',
    justifyContent: 'space-between',
  },
  label: {
    color: theme.colors.text,
    fontSize: 17,
    fontWeight: '900',
  },
  status: {
    color: theme.colors.textMuted,
    fontSize: 13,
    fontWeight: '600',
    marginTop: theme.spacing.sm,
  },
  track: {
    backgroundColor: '#162235',
    borderRadius: 3,
    height: 6,
    marginTop: theme.spacing.md,
    overflow: 'hidden',
  },
  value: {
    color: theme.colors.accent,
    fontSize: 28,
    fontWeight: '900',
  },
});
