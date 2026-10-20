import { ActivityIndicator, StyleSheet, Text, View } from 'react-native';

import { theme } from '../../constants/theme';
import { triggerHaptic } from '../../utils/haptics';
import { AppButton } from '../buttons/AppButton';
import { StatusChip } from '../layout/StatusChip';
import type { FinnV2ProposalSummary } from '../../services/tradamindApi';
import type { AppLanguage } from '../../preferences/AppPreferencesProvider';
import { translate } from '../../i18n';
import { proposalHasConfirmableReview } from '../../services/proposalReview';

export function ScoreDetailSheetContent() {
  return (
    <View style={styles.block}>
      <StatusChip compact label="Score detail" tone="accent" />
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
      <StatusChip compact label="Risicocheck" tone="warning" />
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
      <StatusChip compact label="Read-only review" tone="warning" />
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

export function FinnV2ProposalReviewSheetContent({
  proposal, error, onConfirm, saving, language,
}: {
  proposal: FinnV2ProposalSummary | null;
  error?: string | null;
  onConfirm: () => Promise<void> | void;
  saving: boolean;
  language: AppLanguage;
}) {
  if (!proposal) {
    return <View style={styles.block}><Text style={error ? styles.errorText : styles.body}>
      {error || translate(language, 'finn.proposalLoading')}
    </Text></View>;
  }
  const fields = Object.entries(proposal.requested_state || {});
  const namedTargetAction = ['delete_setup', 'delete_strategy', 'delete_bot', 'deactivate_bot', 'activate_paper_bot', 'activate_live_bot']
    .includes(proposal.operation_type);
  const visibleFields = namedTargetAction ? []
    : proposal.operation_type === 'manual_order'
      ? fields.filter(([key]) => ['asset', 'side', 'order_type', 'quantity', 'notional', 'limit_price'].includes(key))
      : fields;
  const reviewReady = proposalHasConfirmableReview(proposal);
  const active = reviewReady && ['draft', 'pending_confirmation'].includes(proposal.status)
    && Date.parse(proposal.expires_at) > Date.now();
  const setup = proposal.requested_state?.setup;
  const strategy = proposal.requested_state?.strategy;
  const name = proposal.review_target_name
    || proposal.requested_state?.name
    || proposal.before_state?.name
    || (setup && typeof setup === 'object' && 'name' in setup ? setup.name : null)
    || (strategy && typeof strategy === 'object' && 'name' in strategy ? strategy.name : null)
    || proposal.target?.asset
    || proposal.operation_type;
  return (
    <View style={styles.block}>
      <StatusChip compact label={translate(language, 'finn.proposalReview')} tone="warning" />
      <Text style={styles.title}>{String(name)}</Text>
      {proposal.review_target_name && namedTargetAction
        ? <Text style={styles.body}>{translate(language, 'finn.proposalEffect', {
          action: translate(language, proposal.operation_type === 'delete_setup' || proposal.operation_type === 'delete_strategy' || proposal.operation_type === 'delete_bot'
            ? 'finn.proposalEffectDelete'
            : proposal.operation_type === 'deactivate_bot'
              ? 'finn.proposalEffectDeactivate'
              : proposal.operation_type === 'activate_live_bot'
                ? 'finn.proposalEffectActivateLive'
                : 'finn.proposalEffectActivatePaper'),
          name: proposal.review_target_name,
        })}</Text>
        : null}
      {visibleFields.map(([key, value]) => <View key={key} style={{ gap: 4 }}>
        <Text style={styles.body}>{proposal.operation_type === 'manual_order'
          ? translate(language, key === 'asset' ? 'finn.proposalAsset'
            : key === 'side' ? 'finn.proposalSide'
              : key === 'order_type' ? 'finn.proposalOrderType'
                : key === 'quantity' ? 'finn.proposalQuantity'
                  : key === 'notional' ? 'finn.proposalNotional'
                    : 'finn.proposalLimitPrice')
          : key.replace(/_/g, ' ')}</Text>
        <Text style={styles.title}>{proposal.operation_type === 'manual_order' && key === 'side'
          ? translate(language, value === 'buy' ? 'finn.proposalBuy' : 'finn.proposalSell')
          : proposal.operation_type === 'manual_order' && key === 'order_type'
            ? translate(language, value === 'limit' ? 'finn.proposalLimit' : 'finn.proposalMarket')
            : typeof value === 'object' ? JSON.stringify(value) : String(value)}</Text>
      </View>)}
      <Text style={styles.body}>{translate(language, 'finn.proposalReviewBody')}</Text>
      {!reviewReady ? <Text style={styles.errorText}>{translate(language, 'finn.proposalDetailsMissing')}</Text> : null}
      {reviewReady && !active ? <Text style={styles.errorText}>{translate(language, 'finn.proposalExpired')}</Text> : null}
      {error ? <Text style={styles.errorText}>{error}</Text> : null}
      <AppButton label={translate(language, 'finn.proposalConfirm')} disabled={!active || saving} onPress={onConfirm} />
      {saving ? <ActivityIndicator color={theme.colors.accent} /> : null}
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
  onConfirm?: () => Promise<void> | void;
  saving?: boolean;
}) {
  if (!draft) {
    return (
      <View style={styles.block}>
        <StatusChip compact label="Concept review" tone="accent" />
        <Text style={styles.title}>Geen concept geladen</Text>
        <Text style={styles.body}>Er is geen concept gevonden om te beoordelen.</Text>
      </View>
    );
  }

  const payload = draft.payload || {};
  const isUpdate = draft.type === 'strategy' && payload.strategy_id;

  return (
    <View style={styles.block}>
      <StatusChip compact label={isUpdate ? "Update review" : "Concept review"} tone="warning" />
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

      {onConfirm ? <AppButton
        label={isUpdate ? "Sla wijziging op" : "Sla concept op"}
        disabled={saving}
        onPress={async () => {
          if (saving) return;
          await triggerHaptic('success');
          await onConfirm();
        }}
      /> : <Text style={styles.body}>Dit oudere concept kan niet meer worden bevestigd. Vraag FINN om een nieuw voorstel.</Text>}
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
