import { Pressable, StyleSheet, Text, View } from 'react-native';

import { ActionCard } from '../cards/ActionCard';
import { DraftReviewCard } from '../cards/DraftReviewCard';
import { RiskWarningCard } from '../cards/RiskWarningCard';
import { theme } from '../../constants/theme';
import { describeDraft } from '../../services/assistantEnvelopeMapper';
import { AssistantFeedItem } from '../../types/assistant';
import { ActiveFlowStateCard } from './ActiveFlowStateCard';
import { AssistantMessage } from './AssistantMessage';
import type { AppLanguage } from '../../preferences/AppPreferencesProvider';
import { translate } from '../../i18n';

type AssistantFeedRendererProps = {
  language: AppLanguage;
  items: AssistantFeedItem[];
  onActionPress?: () => void;
  onDraftPress?: () => void;
  onProposalPress?: (proposalId: string) => void;
  onRiskPress?: () => void;
  onChoicePress?: (reply: string) => void;
  onOtherPress?: () => void;
  otherLabel?: string;
};

export function AssistantFeedRenderer({
  language,
  items,
  onActionPress,
  onDraftPress,
  onProposalPress,
  onRiskPress,
  onChoicePress,
  onOtherPress,
  otherLabel = 'Anders · typ in de chat',
}: AssistantFeedRendererProps) {
  return (
    <View style={styles.container}>
      {items.map((item, index) => {
        if (item.type === 'message') {
          return (
            <AssistantMessage
              key={item.id}
              author={item.role === 'user' ? 'You' : 'Tradamind AI'}
              text={item.text}
              isUser={item.role === 'user'}
              summary={item.summary}
              riskSummary={item.riskSummary}
              nextBestAction={item.nextBestAction}
              reviewReason={item.reviewReason}
              flow={item.flow}
              intent={item.intent}
            />
          );
        }

        if (item.type === 'state') {
          return <ActiveFlowStateCard key={item.id} state={item.state} />;
        }

        if (item.type === 'choices') {
          if (items.slice(index + 1).some((later) => later.type === 'message' && later.role === 'user')) return null;
          return <View key={item.id} style={styles.choices}>{item.choices.map((choice) => (
            <Pressable key={choice.reply} accessibilityRole="button" onPress={() => onChoicePress?.(choice.reply)} style={styles.choice}>
              <Text style={styles.choiceLabel}>{choice.label}</Text>
            </Pressable>
          ))}<Pressable accessibilityRole="button" onPress={onOtherPress} style={styles.otherChoice}>
            <Text style={styles.otherLabel}>{otherLabel}</Text>
          </Pressable></View>;
        }

        if (item.type === 'action') {
          return (
            <ActionCard
              key={item.id}
              title={item.title}
              reason={item.reason}
              impact={item.impact}
              primaryAction={item.primaryAction}
              tone="accent"
              onPrimary={onActionPress}
            />
          );
        }

        if (item.type === 'draft') {
          return (
            <DraftReviewCard
              key={item.id}
              {...describeDraft(item.draft)}
              onReview={onDraftPress}
            />
          );
        }

        if (item.type === 'v2_proposal') {
          return (
            <ActionCard
              key={item.id}
              title={translate(language, 'finn.proposalTitle')}
              reason={translate(language, 'finn.proposalCardReason')}
              impact={translate(language, 'finn.proposalCardImpact')}
              primaryAction={translate(language, 'finn.proposalCardAction')}
              tone="accent"
              onPrimary={() => onProposalPress?.(item.proposalId)}
            />
          );
        }

        return (
          <RiskWarningCard
            key={item.id}
            severity="Risk detected"
            title="Assistant detected a risk signal"
            body={item.reasoning.reasons.join('. ')}
            nextStep="Ask why before confirming any action."
            onExplain={onRiskPress}
          />
        );
      })}
    </View>
  );
}

const styles = StyleSheet.create({
  choices: { gap: theme.spacing.sm },
  choice: { minHeight: 48, justifyContent: 'center', paddingHorizontal: theme.spacing.md, backgroundColor: theme.colors.surface, borderColor: theme.colors.border, borderWidth: 1, borderRadius: theme.radius.md },
  choiceLabel: { color: theme.colors.text, fontSize: theme.typography.body, fontWeight: '700' },
  otherChoice: { minHeight: 48, justifyContent: 'center', paddingHorizontal: theme.spacing.md, borderColor: theme.colors.border, borderWidth: 1, borderRadius: theme.radius.md },
  otherLabel: { color: theme.colors.textMuted, fontSize: theme.typography.body, fontWeight: '600' },
  container: {
    gap: theme.spacing.md,
  },
});
