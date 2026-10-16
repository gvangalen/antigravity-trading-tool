import assert from 'node:assert/strict';
import { test } from 'node:test';

import { notifyAuthSessionInvalidated, subscribeAuthSessionInvalidated } from '../src/services/authSessionEvents.ts';

test('expired native sessions notify the active auth provider once', () => {
  let invalidations = 0;
  const unsubscribe = subscribeAuthSessionInvalidated(() => { invalidations += 1; });
  notifyAuthSessionInvalidated();
  unsubscribe();
  notifyAuthSessionInvalidated();
  assert.equal(invalidations, 1);
});
