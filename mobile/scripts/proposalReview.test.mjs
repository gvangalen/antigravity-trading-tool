import assert from 'node:assert/strict';
import { test } from 'node:test';

import { proposalHasConfirmableReview } from '../src/services/proposalReview.ts';

const proposal = (operation_type, requested_state) => ({ operation_type, requested_state });

test('mobile cannot confirm destructive or activation proposals from an ID-only review', () => {
  for (const operation of [
    'delete_setup', 'delete_strategy', 'delete_bot', 'deactivate_bot',
    'activate_paper_bot', 'activate_live_bot', 'portfolio_rebalance',
  ]) {
    assert.equal(proposalHasConfirmableReview(proposal(operation, { bot_id: 12 })), false, operation);
  }
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
