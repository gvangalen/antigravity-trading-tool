import assert from 'node:assert/strict';
import test from 'node:test';

import { pollFinnRun, proposalActionFromRun } from '../src/services/finnRunPolling.ts';

test('only a completed, confirmable V2 run exposes its owner-bound proposal', () => {
  const response = { proposal_id: 'proposal-123', confirmation_required: true, mode: 'action' };
  assert.deepEqual(proposalActionFromRun({ run_id: 'run-1', status: 'completed', response }), {
    type: 'v2_proposal', proposal_id: 'proposal-123', requires_confirmation: true, mode: 'action',
  });
  assert.equal(proposalActionFromRun({ run_id: 'run-1', status: 'running', response }), null);
  assert.equal(proposalActionFromRun({ run_id: 'run-1', status: 'completed', response: {
    ...response, confirmation_required: false,
  } }), null);
});

test('processing turns are read until their owner-scoped run completes', async () => {
  const statuses = ['created', 'running', 'completed'];
  const result = await pollFinnRun('run-1', async (id) => ({
    run_id: id,
    status: statuses.shift(),
    response: { content: 'Geen updates voor je plan.' },
  }), undefined, 3, 0);
  assert.equal(result.status, 'completed');
  assert.equal(result.response.content, 'Geen updates voor je plan.');
});

test('a run-id mismatch cannot become another conversation answer', async () => {
  await assert.rejects(
    pollFinnRun('run-1', async () => ({ run_id: 'run-2', status: 'completed' }), undefined, 1, 0),
    /identity changed/,
  );
});

test('an unresolved run ends with a retryable error', async () => {
  await assert.rejects(
    pollFinnRun('run-1', async (id) => ({ run_id: id, status: 'running' }), undefined, 2, 0),
    /niet afronden/,
  );
});

test('temporary polling transport failures are retried without resubmitting chat', async () => {
  let reads = 0;
  const run = await pollFinnRun('run-1', async (id) => {
    reads += 1;
    if (reads === 1) throw Object.assign(new Error('temporary gateway error'), { status: 503 });
    return { run_id: id, status: 'completed', response: { content: 'Klaar.' } };
  }, undefined, 2, 0);
  assert.equal(reads, 2);
  assert.equal(run.response.content, 'Klaar.');
});

test('stopping a run interrupts the polling delay', async () => {
  const controller = new AbortController();
  const pending = pollFinnRun('run-1', async (id) => ({ run_id: id, status: 'running' }), controller.signal, 4, 1000);
  controller.abort();
  await assert.rejects(pending, /canceled/);
});
