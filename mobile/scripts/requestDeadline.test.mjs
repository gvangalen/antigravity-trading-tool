import assert from 'node:assert/strict';
import test from 'node:test';

import { withRequestDeadline } from '../src/services/requestDeadline.ts';

test('a native request that ignores abort still reaches a terminal timeout', async () => {
  await assert.rejects(
    withRequestDeadline(new Promise(() => {}), 5, () => new Error('Request timed out')),
    /Request timed out/,
  );
});

test('a completed request returns its response before the deadline', async () => {
  assert.equal(await withRequestDeadline(Promise.resolve('ready'), 100, () => new Error('timeout')), 'ready');
});
