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

export function DraftReviewSheetContent({ draft, onConfirm }: { draft: any; onConfirm: () => void }) {
  if (!draft) {
    return (
      <View style={styles.block}>
        <StatusChip label="Draft review" tone="accent" />
        <Text style={styles.title}>Geen concept geladen</Text>
        <Text style={styles.body}>Er is geen concept gevonden om te beoordelen.</Text>
      </View>
    );
  }

  const payload = draft.payload || {};
  const isUpdate = draft.type === 'strategy' && payload.strategy_id;

  return (
    <View style={styles.block}>
      <StatusChip label={isUpdate ? "Update Review" : "Draft Review"} tone="warning" />
      <Text style={styles.title}>{payload.name || `${draft.type} Concept`}</Text>
      
      <View style={{ gap: 8, marginTop: theme.spacing.sm }}>
        {Object.entries(payload).map(([key, value]) => {
          if (['name', 'strategy_id'].includes(key)) return null;
          return (
            <View key={key} style={{ flexDirection: 'row', justifyContent: 'space-between' }}>
              <Text style={{ color: theme.colors.textDim, fontSize: 13 }}>{key}</Text>
              <Text style={{ color: theme.colors.text, fontWeight: '600', fontSize: 13 }}>{String(value)}</Text>
            </View>
          );
        })}
      </View>

      <Pressable
        onPress={async () => {
          await triggerHaptic('success');
          onConfirm();
        }}
        style={({ pressed }) => [styles.button, pressed && styles.pressed]}
      >
        <Text style={styles.buttonText}>{isUpdate ? "Bevestig Update" : "Bevestig Opslaan"}</Text>
      </Pressable>
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
