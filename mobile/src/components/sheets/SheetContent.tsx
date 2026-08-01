import { ActivityIndicator, StyleSheet, Text, View } from 'react-native';

import { theme } from '../../constants/theme';
import { triggerHaptic } from '../../utils/haptics';
import { AppButton } from '../buttons/AppButton';
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
      <StatusChip label="Risicocheck" tone="warning" />
      <Text style={styles.title}>De grootste fout is nu te vroeg achter prijs aan te lopen.</Text>
      <Text style={styles.body}>
        De veiligere route is wachten op bevestiging of de geplande grootte verlagen totdat de setupkwaliteit verbetert.
      </Text>
    </View>
  );
}

export function ConfirmActionSheetContent({ onDone }: { onDone: () => void }) {
  return (
    <View style={styles.block}>
      <StatusChip label="Read-only review" tone="warning" />
      <Text style={styles.title}>Controleer eerst context, impact en risico.</Text>
      <Text style={styles.body}>
        Finn gebruikt deze sheet om gevoelige acties eerst expliciet te laten reviewen. De daadwerkelijke bevestiging blijft gekoppeld aan de concrete flow waarin je werkt.
      </Text>
      <AppButton
        label="Terug naar Finn"
        onPress={async () => {
          await triggerHaptic('success');
          onDone();
        }}
      />
    </View>
  );
}

export function DraftReviewSheetContent({
  draft,
  error,
  onConfirm,
  saving = false,
}: {
  draft: any;
  error?: string | null;
  onConfirm: () => Promise<void> | void;
  saving?: boolean;
}) {
  if (!draft) {
    return (
      <View style={styles.block}>
        <StatusChip label="Concept review" tone="accent" />
        <Text style={styles.title}>Geen concept geladen</Text>
        <Text style={styles.body}>Er is geen concept gevonden om te beoordelen.</Text>
      </View>
    );
  }

  const payload = draft.payload || {};
  const isUpdate = draft.type === 'strategy' && payload.strategy_id;

  return (
    <View style={styles.block}>
      <StatusChip label={isUpdate ? "Update review" : "Concept review"} tone="warning" />
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

      {error ? <Text style={styles.errorText}>{error}</Text> : null}

      <AppButton
        label={isUpdate ? "Sla wijziging op" : "Sla concept op"}
        disabled={saving}
        onPress={async () => {
          if (saving) return;
          await triggerHaptic('success');
          await onConfirm();
        }}
      />
      {saving ? <ActivityIndicator color={theme.colors.accent} /> : null}
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
  errorText: {
    color: theme.colors.danger,
    fontSize: 13,
    fontWeight: '700',
    lineHeight: 18,
  },
  title: {
    color: theme.colors.text,
    fontSize: theme.typography.title,
    fontWeight: '900',
    lineHeight: 27,
  },
});
