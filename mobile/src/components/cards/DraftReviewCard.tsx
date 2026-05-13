import { Pressable, StyleSheet, Text, View } from 'react-native';

import { theme } from '../../constants/theme';
import { triggerHaptic } from '../../utils/haptics';
import { StatusChip } from '../layout/StatusChip';
import { CardShell } from './CardShell';

type DraftReviewCardProps = {
  type: string;
  asset: string;
  title: string;
  purpose: string;
  parameters: string[];
  risk: string;
  onReview?: () => void;
};

export function DraftReviewCard({
  type,
  asset,
  title,
  purpose,
  parameters,
  risk,
  onReview,
}: DraftReviewCardProps) {
  return (
    <CardShell>
      <View style={styles.topRow}>
        <StatusChip label={type} tone="accent" />
        <Text style={styles.asset}>{asset}</Text>
      </View>
      <Text style={styles.title}>{title}</Text>
      <Text style={styles.purpose}>{purpose}</Text>
      <View style={styles.params}>
        {parameters.map((item) => (
          <View key={item} style={styles.paramPill}>
            <Text style={styles.paramText}>{item}</Text>
          </View>
        ))}
      </View>
      <View style={styles.riskBox}>
        <Text style={styles.riskLabel}>Review note</Text>
        <Text style={styles.risk}>{risk}</Text>
      </View>
      <View style={styles.actions}>
        <Pressable
          onPress={async () => {
            await triggerHaptic('selection');
            onReview?.();
          }}
          style={({ pressed }) => [styles.confirmButton, pressed && styles.pressed]}
        >
          <Text style={styles.confirmText}>Review draft</Text>
        </Pressable>
        <Pressable style={({ pressed }) => [styles.ghostButton, pressed && styles.pressed]}>
          <Text style={styles.ghostText}>Ask why</Text>
        </Pressable>
      </View>
    </CardShell>
  );
}

const styles = StyleSheet.create({
  actions: {
    flexDirection: 'row',
    gap: theme.spacing.sm,
    marginTop: theme.spacing.lg,
  },
  asset: {
    color: theme.colors.text,
    fontSize: 15,
    fontWeight: '900',
  },
  confirmButton: {
    alignItems: 'center',
    backgroundColor: theme.colors.accent,
    borderRadius: theme.radius.button,
    flex: 1,
    justifyContent: 'center',
    minHeight: 48,
  },
  confirmText: {
    color: theme.colors.white,
    fontSize: 12,
    fontWeight: '900',
    letterSpacing: 1.2,
    textTransform: 'uppercase',
  },
  ghostButton: {
    alignItems: 'center',
    backgroundColor: theme.colors.surfaceMuted,
    borderColor: theme.colors.borderStrong,
    borderRadius: theme.radius.button,
    borderWidth: 1,
    justifyContent: 'center',
    minHeight: 48,
    paddingHorizontal: theme.spacing.md,
  },
  ghostText: {
    color: theme.colors.textSoft,
    fontSize: 12,
    fontWeight: '900',
  },
  paramPill: {
    backgroundColor: theme.colors.backgroundSoft,
    borderColor: theme.colors.border,
    borderRadius: theme.radius.pill,
    borderWidth: 1,
    paddingHorizontal: theme.spacing.sm,
    paddingVertical: 7,
  },
  paramText: {
    color: theme.colors.textMuted,
    fontSize: theme.typography.small,
    fontWeight: '800',
  },
  params: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: theme.spacing.sm,
    marginTop: theme.spacing.md,
  },
  pressed: {
    opacity: 0.86,
  },
  purpose: {
    color: theme.colors.textMuted,
    fontSize: theme.typography.body,
    fontWeight: '600',
    lineHeight: 22,
    marginTop: theme.spacing.sm,
  },
  risk: {
    color: theme.colors.textSoft,
    fontSize: theme.typography.small,
    fontWeight: '700',
    lineHeight: 20,
    marginTop: 4,
  },
  riskBox: {
    backgroundColor: theme.colors.warningSoft,
    borderColor: '#F59E0B55',
    borderRadius: theme.radius.md,
    borderWidth: 1,
    marginTop: theme.spacing.md,
    padding: theme.spacing.md,
  },
  riskLabel: {
    color: theme.colors.warning,
    fontSize: theme.typography.label,
    fontWeight: '900',
    letterSpacing: 1.5,
    textTransform: 'uppercase',
  },
  title: {
    color: theme.colors.text,
    fontSize: theme.typography.title,
    fontWeight: '900',
    lineHeight: 27,
    marginTop: theme.spacing.md,
  },
  topRow: {
    alignItems: 'center',
    flexDirection: 'row',
    justifyContent: 'space-between',
  },
});
