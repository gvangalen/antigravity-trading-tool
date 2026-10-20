import type { FinnV2ProposalSummary } from './tradamindApi';

// These operations need an owner-verified target name and effect before a
// mobile confirmation can be an informed decision. Until the review contract
// provides both, keep the existing server proposal safe but unconfirmable here.
const requiresFullTargetReview = new Set([
  'delete_setup', 'delete_strategy', 'delete_bot', 'deactivate_bot',
  'activate_paper_bot', 'activate_live_bot', 'portfolio_rebalance',
]);

export function proposalHasConfirmableReview(proposal: FinnV2ProposalSummary): boolean {
  const state = proposal.requested_state || {};
  if (requiresFullTargetReview.has(proposal.operation_type)) return false;
  if (proposal.operation_type === 'manual_order') {
    return typeof state.asset === 'string'
      && ['buy', 'sell'].includes(String(state.side))
      && ['market', 'limit'].includes(String(state.order_type))
      && (state.quantity != null || state.notional != null)
      && (state.order_type !== 'limit' || state.limit_price != null);
  }
  return Object.keys(state).length > 0;
}
