import assert from 'node:assert/strict';
import test from 'node:test';
import { readFileSync } from 'node:fs';
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

test('trade review exposes original source levels and FX provenance in each locale', () => {
  for (const locale of ['nl', 'en', 'de']) {
    const dictionary = JSON.parse(readFileSync(new URL(`../dictionaries/${locale}.json`, import.meta.url)));
    const copy = dictionary.pages?.report?.finn?.tradeReviews;
    assert.ok(copy, `${locale} trade review copy`);
    const planFields = copy.planFields;
    const fields = visiblePlanFields(Object.entries({
      price_currency: 'EUR', source_price_currency: 'USD',
      source_levels: { stop_loss: 342, targets: [357.42] },
      fx_eur_per_unit: 0.9, fx_as_of: '2026-11-10T14:45:00Z',
    }), planFields);
    assert.deepEqual(fields.map(([key]) => key), [
      'price_currency', 'source_price_currency', 'source_levels',
      'fx_eur_per_unit', 'fx_as_of',
    ]);
    assert.ok(copy.planCurrencyNote);
    assert.ok(copy.paperExitDecisionEvidence);
    const exitCopy = dictionary.botPage?.history?.exitEvidence;
    assert.ok(exitCopy?.savedTarget);
    assert.ok(exitCopy?.decisionFx);
    assert.ok(exitCopy?.conversion);
    assert.ok(exitCopy?.marketMeasurement);
  }
});
