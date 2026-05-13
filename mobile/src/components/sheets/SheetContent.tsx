import { Pressable, StyleSheet, Text, View } from 'react-native';

import { theme } from '../../constants/theme';
import { triggerHaptic } from '../../utils/haptics';
import { StatusChip } from '../layout/StatusChip';

export function ScoreDetailSheetContent() {
  return (
    <View style={styles.block}>
      <StatusChip label="Score detail" tone="accent" />
      <Text style={styles.title}>Setup score is waiting for cleaner entry.</Text>
      <Text style={styles.body}>
        Market and technical context are constructive. The setup score lags because entry quality is
        still close to resistance.
      </Text>
    </View>
  );
}

export function RiskExplanationSheetContent() {
  return (
    <View style={styles.block}>
      <StatusChip label="Caution" tone="warning" />
      <Text style={styles.title}>The main risk is chasing price near resistance.</Text>
      <Text style={styles.body}>
        The safer alternative is to wait for confirmation or reduce planned size until setup quality
        improves.
      </Text>
    </View>
  );
}

export function ConfirmActionSheetContent({ onDone }: { onDone: () => void }) {
  return (
    <View style={styles.block}>
      <StatusChip label="Confirmation" tone="warning" />
      <Text style={styles.title}>Review before marking this action.</Text>
      <Text style={styles.body}>
        This foundation does not execute trades. It only demonstrates the confirmation pattern that
        will protect live actions later.
      </Text>
      <Pressable
        onPress={async () => {
          await triggerHaptic('success');
          onDone();
        }}
        style={({ pressed }) => [styles.button, pressed && styles.pressed]}
      >
        <Text style={styles.buttonText}>Confirm mock action</Text>
      </Pressable>
    </View>
  );
}

export function DraftReviewSheetContent() {
  return (
    <View style={styles.block}>
      <StatusChip label="Draft review" tone="accent" />
      <Text style={styles.title}>Assistant drafts stay review-first.</Text>
      <Text style={styles.body}>
        Future API drafts will map into this sheet for confirm, edit, cancel, and ask-why flows.
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  block: {
    gap: theme.spacing.md,
  },
  body: {
    color: theme.colors.textMuted,
    fontSize: theme.typography.body,
    fontWeight: '600',
    lineHeight: 22,
  },
  button: {
    alignItems: 'center',
    backgroundColor: theme.colors.accent,
    borderRadius: theme.radius.button,
    minHeight: 50,
    justifyContent: 'center',
    marginTop: theme.spacing.sm,
  },
  buttonText: {
    color: theme.colors.white,
    fontSize: 12,
    fontWeight: '900',
    letterSpacing: 1.3,
    textTransform: 'uppercase',
  },
  pressed: {
    opacity: 0.86,
  },
  title: {
    color: theme.colors.text,
    fontSize: theme.typography.title,
    fontWeight: '900',
    lineHeight: 27,
  },
});
