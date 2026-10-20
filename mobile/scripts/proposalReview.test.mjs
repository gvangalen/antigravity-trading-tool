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
