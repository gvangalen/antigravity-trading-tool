import assert from "node:assert/strict";
import test from "node:test";
import { readCoachFeedWithRetry } from "../lib/finnCoachFeedRead.mjs";

test("feed recovers from a short backend restart without changing stored items", async () => {
  let calls = 0;
  const delays = [];
  const rows = [{ id: "same-owner-item" }];
  const result = await readCoachFeedWithRetry(async () => {
    calls += 1;
    if (calls < 6) throw Object.assign(new Error("gateway unavailable"), { status: 502 });
    return rows;
  }, { wait: async (ms) => { delays.push(ms); } });
  assert.equal(result, rows);
  assert.equal(calls, 6);
  assert.deepEqual(delays, [1000, 2000, 4000, 8000, 16000]);
});

test("feed does not retry authentication or application errors", async () => {
  for (const status of [401, 403, 404, 500]) {
    let calls = 0;
    await assert.rejects(readCoachFeedWithRetry(async () => {
      calls += 1;
      throw Object.assign(new Error("not transient"), { status });
    }, { wait: async () => { throw new Error("unexpected retry"); } }), { status });
    assert.equal(calls, 1);
  }
});

test("feed stops retrying when its owner or view changes", async () => {
  let calls = 0;
  let current = true;
  const result = await readCoachFeedWithRetry(async () => {
    calls += 1;
    throw Object.assign(new Error("gateway unavailable"), { status: 502 });
  }, { isCurrent: () => current, wait: async () => { current = false; } });
  assert.equal(result, null);
  assert.equal(calls, 1);
});

test("feed reports a persistent gateway outage after bounded retries", async () => {
  let calls = 0;
  const delays = [];
  await assert.rejects(readCoachFeedWithRetry(async () => {
    calls += 1;
    throw Object.assign(new Error("gateway unavailable"), { status: 502 });
  }, { wait: async (ms) => { delays.push(ms); } }), { status: 502 });
  assert.equal(calls, 6);
  assert.deepEqual(delays, [1000, 2000, 4000, 8000, 16000]);
});
