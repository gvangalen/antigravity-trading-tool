import type { FinnV2ProposalSummary } from './tradamindApi';

const requiresOwnedTarget = new Set([
  'delete_setup', 'delete_strategy', 'delete_bot', 'deactivate_bot',
  'activate_paper_bot', 'activate_live_bot', 'portfolio_rebalance',
]);

export function proposalHasConfirmableReview(proposal: FinnV2ProposalSummary): boolean {
  const state = proposal.requested_state || {};
  if (proposal.operation_type === 'portfolio_rebalance') return false;
  if (requiresOwnedTarget.has(proposal.operation_type)) {
    const name = proposal.review_target_name;
    return typeof name === 'string' && name.trim().length > 0;
  }
  if (proposal.operation_type === 'manual_order') {
    return typeof state.asset === 'string'
      && ['buy', 'sell'].includes(String(state.side))
      && ['market', 'limit'].includes(String(state.order_type))
      && (state.quantity != null || state.notional != null)
      && (state.order_type !== 'limit' || state.limit_price != null);
  }
  return Object.keys(state).length > 0;
}
