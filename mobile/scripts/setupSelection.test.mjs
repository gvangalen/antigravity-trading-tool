import assert from 'node:assert/strict';
import { test } from 'node:test';

import { extractOwnedActiveSetup } from '../src/services/setupSelection.ts';

test('a missing active setup wrapper is not converted into a fictional asset plan', () => {
  assert.equal(extractOwnedActiveSetup({ active: null, source_status: 'missing_scores', as_of: '2026-10-16' }), undefined);
});

test('a real owner-scoped active setup remains available', () => {
  assert.deepEqual(extractOwnedActiveSetup({ active: { id: 42, name: 'BTC DCA', symbol: 'BTC' } }), {
    id: 42, name: 'BTC DCA', symbol: 'BTC',
  });
});

test('status-only objects without a persisted setup id are ignored', () => {
  assert.equal(extractOwnedActiveSetup({ source_status: 'missing_scores', symbol: 'BTC' }), undefined);
});
