import { StyleSheet, View } from 'react-native';

import { ActionCard } from '../cards/ActionCard';
import { DraftReviewCard } from '../cards/DraftReviewCard';
import { RiskWarningCard } from '../cards/RiskWarningCard';
import { theme } from '../../constants/theme';
import { describeDraft } from '../../services/assistantEnvelopeMapper';
import { AssistantFeedItem } from '../../types/assistant';
import { ActiveFlowStateCard } from './ActiveFlowStateCard';
import { AssistantMessage } from './AssistantMessage';

type AssistantFeedRendererProps = {
  items: AssistantFeedItem[];
  onActionPress?: () => void;
  onDraftPress?: () => void;
  onRiskPress?: () => void;
};

export function AssistantFeedRenderer({
  items,
  onActionPress,
  onDraftPress,
  onRiskPress,
}: AssistantFeedRendererProps) {
  return (
    <View style={styles.container}>
      {items.map((item) => {
        if (item.type === 'message') {
          return (
            <AssistantMessage
              key={item.id}
              author={item.role === 'user' ? 'You' : 'Tradamind AI'}
              text={item.text}
              isUser={item.role === 'user'}
            />
          );
        }

        if (item.type === 'state') {
          return <ActiveFlowStateCard key={item.id} state={item.state} />;
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
  container: {
    gap: theme.spacing.md,
  },
});
