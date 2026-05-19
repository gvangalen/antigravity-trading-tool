import { Pressable, StyleSheet, Text, View } from 'react-native';

import { statusTones, theme } from '../../constants/theme';
import { DomainScore } from '../../types/scores';
import { triggerHaptic } from '../../utils/haptics';

type ScoreDomainCardProps = {
  score: DomainScore;
  onPress?: () => void;
};

export function ScoreDomainCard({ score, onPress }: ScoreDomainCardProps) {
  const palette = statusTones[score.tone];

  return (
    <Pressable
      onPress={async () => {
        await triggerHaptic('selection');
        onPress?.();
      }}
      style={({ pressed }) => [
        styles.card,
        { backgroundColor: palette.background, borderColor: palette.border },
        pressed && styles.pressed,
      ]}
    >
      <View style={styles.header}>
        <Text style={styles.label}>{score.label}</Text>
        <Text style={[styles.value, { color: palette.color }]}>{score.score}</Text>
      </View>
      <View style={styles.track}>
        <View style={[styles.fill, { width: `${score.score}%`, backgroundColor: palette.color }]} />
      </View>
      <Text style={[styles.trend, { color: palette.color }]}>{score.trend}</Text>
      <Text style={styles.summary}>{score.summary}</Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  card: {
    borderRadius: theme.radius.card,
    borderWidth: 1,
    flex: 1,
    minWidth: '47%',
    padding: theme.spacing.md,
  },
  fill: {
    borderRadius: theme.radius.pill,
    height: 6,
  },
  header: {
    alignItems: 'center',
    flexDirection: 'row',
    justifyContent: 'space-between',
  },
  label: {
    color: theme.colors.text,
    fontSize: theme.typography.small,
    fontWeight: '900',
  },
  pressed: {
    opacity: 0.86,
  },
  summary: {
    color: theme.colors.textMuted,
    fontSize: 12,
    fontWeight: '600',
    lineHeight: 18,
    marginTop: theme.spacing.xs,
  },
  track: {
    backgroundColor: '#02061755',
    borderRadius: theme.radius.pill,
    height: 6,
    marginTop: theme.spacing.md,
    overflow: 'hidden',
  },
  trend: {
    fontSize: theme.typography.label,
    fontWeight: '900',
    letterSpacing: 1.3,
    marginTop: theme.spacing.sm,
    textTransform: 'uppercase',
  },
  value: {
    fontSize: 24,
    fontWeight: '900',
  },
});
