import assert from 'node:assert/strict';
import { test } from 'node:test';

import { proposalHasConfirmableReview } from '../src/services/proposalReview.ts';

const proposal = (operation_type, requested_state) => ({ operation_type, requested_state });

test('mobile requires an owner-verified name for destructive and activation proposals', () => {
  for (const operation of [
    'delete_setup', 'delete_strategy', 'delete_bot', 'deactivate_bot',
    'activate_paper_bot', 'activate_live_bot',
  ]) {
    assert.equal(proposalHasConfirmableReview(proposal(operation, { bot_id: 12 })), false, operation);
    assert.equal(proposalHasConfirmableReview({
      ...proposal(operation, { bot_id: 12 }), review_target_name: 'BTC Paper bot',
    }), true, operation);
  }
  assert.equal(proposalHasConfirmableReview(proposal('portfolio_rebalance', { BTC: 50, ETH: 50 })), false);
});

test('manual orders require side, size, type and limit price when relevant', () => {
  assert.equal(proposalHasConfirmableReview(proposal('manual_order', { asset: 'ETH' })), false);
  assert.equal(proposalHasConfirmableReview(proposal('manual_order', {
    asset: 'ETH', side: 'buy', order_type: 'market', notional: '100',
  })), true);
  assert.equal(proposalHasConfirmableReview(proposal('manual_order', {
    asset: 'ETH', side: 'sell', order_type: 'limit', quantity: '0.5',
  })), false);
  assert.equal(proposalHasConfirmableReview(proposal('manual_order', {
    asset: 'ETH', side: 'sell', order_type: 'limit', quantity: '0.5', limit_price: '3000',
  })), true);
});

test('manual trade plan review needs complete risk and cannot execute', () => {
  const plan = {
    asset: 'BTC', quote_currency: 'EUR', direction: 'long', entry_type: 'limit',
    entry_price: '70000', quantity: '0.001', stop_loss: '65000',
    targets: ['80000', '85000'], max_loss_quote: '5',
    position_value_quote: '70', risk_per_unit_quote: '5000', risk_pct_of_position: '7.14',
    reward_risk_by_target: ['2', '3'], executable: false,
  };
  assert.equal(proposalHasConfirmableReview(proposal('create_manual_trade_plan', plan)), true);
  assert.equal(proposalHasConfirmableReview(proposal('create_manual_trade_plan', { ...plan, executable: true })), false);
  assert.equal(proposalHasConfirmableReview(proposal('create_manual_trade_plan', { ...plan, targets: [] })), false);
  assert.equal(proposalHasConfirmableReview(proposal('create_manual_trade_plan', { ...plan, max_loss_quote: null })), false);
});
