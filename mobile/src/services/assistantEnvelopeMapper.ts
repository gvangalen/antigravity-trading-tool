import {
  AssistantAction,
  AssistantDraft,
  AssistantEnvelope,
  AssistantFeedItem,
} from '../types/assistant';

export function mapAssistantEnvelopeToFeedItems(envelope: AssistantEnvelope): AssistantFeedItem[] {
  const suffix = envelope.trace_id || Date.now().toString();
  const items: AssistantFeedItem[] = [
    {
      id: `message-${suffix}`,
      type: 'message',
      role: 'assistant',
      text: envelope.response,
      summary: envelope.summary ?? null,
      riskSummary: envelope.risk_summary ?? null,
      nextBestAction: envelope.next_best_action ?? null,
      reviewReason: envelope.review_reason ?? null,
      flow: envelope.flow ?? null,
      intent: envelope.intent ?? null,
    },
  ];

  if (envelope.state && envelope.state.status === 'collecting') {
    items.push({
      id: `state-${suffix}`,
      type: 'state',
      state: envelope.state,
    });
  }

  if (envelope.action) {
    items.push({
      id: `action-${suffix}`,
      type: 'action',
      ...describeAction(envelope.action),
    });
  }

  if (envelope.draft) {
    items.push({
      id: `draft-${suffix}`,
      type: 'draft',
      draft: envelope.draft,
    });
  }

  if (envelope.reasoning?.risk_detected) {
    items.push({
      id: `reasoning-${suffix}`,
      type: 'reasoning',
      reasoning: envelope.reasoning,
    });
  }

  return items;
}

function describeAction(action: AssistantAction) {
  if (action.type === 'bundle') {
    return {
      title: 'Review assistant actions',
      reason: `${action.actions.length} suggested actions are ready for review.`,
      impact: 'Bundled actions are shown for confirmation before anything is applied.',
      primaryAction: 'Review actions',
    };
  }

  const symbol = action.symbol ? ` ${action.symbol}` : '';
  const fallbackDescription = action.description || 'Assistant suggested a safe next step.';

  switch (action.type) {
    case 'add_to_watchlist':
      return {
        title: `Add${symbol} to watchlist`,
        reason: fallbackDescription,
        impact: 'Adds the asset to mobile monitoring. No trading action is executed.',
        primaryAction: 'Add asset',
      };
    case 'remove_from_watchlist':
      return {
        title: `Remove${symbol} from watchlist`,
        reason: fallbackDescription,
        impact: 'Removes this asset from active monitoring only.',
        primaryAction: 'Remove',
      };
    case 'open_setup_page':
      return {
        title: `Open setup context${symbol}`,
        reason: fallbackDescription,
        impact: 'Opens a mobile setup review surface instead of a desktop form.',
        primaryAction: 'Open setup',
      };
    case 'generate_strategy':
      return {
        title: `Prepare strategy context${symbol}`,
        reason: fallbackDescription,
        impact: 'Starts review-first strategy flow. No strategy is saved automatically.',
        primaryAction: 'Review strategy',
      };
    case 'open_bot_draft':
      return {
        title: `Review bot draft${symbol}`,
        reason: fallbackDescription,
        impact: 'Bot drafts stay paper/review-first until confirmed.',
        primaryAction: 'Review bot',
      };
    case 'navigate_to_page':
      return {
        title: 'Open mobile context',
        reason: fallbackDescription,
        impact: 'Routes to a mobile object screen, not a desktop dashboard.',
        primaryAction: 'Open',
      };
  }
}

export function describeDraft(draft: AssistantDraft) {
  const payload = draft.payload || {};
  const symbol = typeof payload.symbol === 'string' ? payload.symbol : 'Asset';
  const title =
    typeof payload.name === 'string'
      ? payload.name
      : `${symbol} ${capitalize(draft.type)} Draft`;

  const parameters = Object.entries(payload)
    .filter(([key]) => ['entry', 'targets', 'stop_loss', 'base_amount', 'mode', 'budget_total_eur'].includes(key))
    .slice(0, 4)
    .map(([key, value]) => `${labelize(key)}: ${formatValue(value)}`);

  return {
    type: `${capitalize(draft.type)} Draft`,
    asset: symbol,
    title,
    purpose: `Assistant prepared a ${draft.type} concept for review.`,
    parameters: parameters.length > 0 ? parameters : ['Review assumptions before saving'],
    risk: 'Values are assistant-prepared and must be reviewed before confirmation.',
  };
}

function capitalize(value: string) {
  return value.charAt(0).toUpperCase() + value.slice(1);
}

function labelize(value: string) {
  return value
    .split('_')
    .map((part) => capitalize(part))
    .join(' ');
}

function formatValue(value: unknown) {
  if (Array.isArray(value)) return value.join(' / ');
  if (typeof value === 'object' && value !== null) return 'Configured';
  return String(value);
}
