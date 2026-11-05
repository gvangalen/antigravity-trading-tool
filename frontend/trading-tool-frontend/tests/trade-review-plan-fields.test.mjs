import assert from 'node:assert/strict';
import test from 'node:test';
import { visiblePlanFields } from '../lib/report/tradeReviewPlanFields.mjs';

test('trade review plan details keep user-facing facts and omit internal market IDs', () => {
  const labels = { market_id: 'Market ID', price_currency: 'Price currency', base_amount: 'Base amount' };
  assert.deepEqual(visiblePlanFields([
    ['market_id', 1],
    ['price_currency', 'EUR'],
    ['base_amount', 100],
    ['unused_internal_field', 'hidden'],
  ], labels), [
    ['price_currency', 'EUR'],
    ['base_amount', 100],
  ]);
});
