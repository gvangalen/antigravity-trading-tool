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
  if (proposal.operation_type === 'create_manual_trade_plan') {
    const positive = (value: unknown) => typeof value === 'string' && Number.isFinite(Number(value)) && Number(value) > 0;
    return state.executable === false
      && typeof state.asset === 'string' && state.asset.length > 0
      && ['EUR', 'USDT', 'USD'].includes(String(state.quote_currency))
      && ['long', 'short'].includes(String(state.direction))
      && state.entry_type === 'limit'
      && positive(state.entry_price) && positive(state.quantity)
      && positive(state.stop_loss) && positive(state.max_loss_quote)
      && positive(state.position_value_quote) && positive(state.risk_per_unit_quote)
      && positive(state.risk_pct_of_position)
      && Array.isArray(state.targets) && state.targets.length > 0
      && state.targets.every(positive)
      && Array.isArray(state.reward_risk_by_target)
      && state.reward_risk_by_target.length === state.targets.length;
  }
  return Object.keys(state).length > 0;
}
