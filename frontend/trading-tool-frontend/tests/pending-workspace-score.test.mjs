import assert from "node:assert/strict";
import test from "node:test";

import { workspaceScoreNeedsRefresh } from "../lib/workspace/pendingWorkspaceScore.mjs";
import { oldestScoredEvidenceSource } from "../lib/workspace/canonicalScorePresentation.mjs";

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

test("daily benchmark source comes from its saved scored evidence", () => {
  const evidence = {
    market: { volume: { score: 50, source_observed_at: "2026-11-24T10:06:00Z" } },
    macro: {
      sp500: { score: 60, source_observed_at: "2026-11-23T00:00:00Z" },
      dxy: { score: 45, source_observed_at: "2026-11-23T23:59:00Z" },
    },
    technical: { rsi: { score: 40, source_observed_at: "2026-11-23T23:59:00Z" } },
  };
  assert.equal(oldestScoredEvidenceSource(evidence), "2026-11-23T00:00:00.000Z");
  assert.equal(oldestScoredEvidenceSource({ market: {
    unscored: { score: null, source_observed_at: "2026-11-22T23:00:00Z" },
    volume: { score: 0, source_observed_at: "2026-11-24T10:06:00" },
  } }), "2026-11-24T10:06:00.000Z");
  assert.equal(oldestScoredEvidenceSource({ macro: {
    sp500: { score: 60, source_observed_at: null },
  } }), null);
});
