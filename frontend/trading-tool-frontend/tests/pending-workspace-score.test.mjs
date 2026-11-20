import assert from "node:assert/strict";
import test from "node:test";

import { workspaceScoreNeedsRefresh } from "../lib/workspace/pendingWorkspaceScore.mjs";

test("a newly copied asset bypasses the cache while one category score is missing", () => {
  const pending = { daily: {
    benchmark_score: null,
    market: { source_status: "fresh" },
    macro: { source_status: "missing_score" },
    technical: { source_status: "fresh" },
  } };
  assert.equal(workspaceScoreNeedsRefresh(pending, null), true);
  assert.equal(workspaceScoreNeedsRefresh({ ...pending, daily: {
    ...pending.daily, macro: { source_status: "stale_source" },
  } }, null), true);
});

test("pending indicator evidence refreshes an asset even before a score exists", () => {
  assert.equal(workspaceScoreNeedsRefresh({
    daily: { benchmark_score: null },
    categories: { macro: { rows: [
      { name: "dxy", value: null, data_status: "pending_refresh" },
    ] } },
  }, null), true);
});

test("a complete asset uses the normal cache and pairs retain their retry rules", () => {
  assert.equal(workspaceScoreNeedsRefresh({ daily: {
    benchmark_score: 56,
    macro: { source_status: "stale_source" },
  } }, null), false);
  assert.equal(workspaceScoreNeedsRefresh({ daily: {
    macro: { source_status: "missing_score" },
  } }, "USDT"), true);
  assert.equal(workspaceScoreNeedsRefresh({ daily: {
    macro: { source_status: "stale_source" },
  } }, "USDT"), false);
  assert.equal(workspaceScoreNeedsRefresh(null, null), false);
});
