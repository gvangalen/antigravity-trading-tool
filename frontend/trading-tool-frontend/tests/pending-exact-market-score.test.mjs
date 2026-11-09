import assert from "node:assert/strict";
import test from "node:test";

import { exactMarketScoreNeedsRefresh } from "../lib/workspace/pendingExactMarketScore.mjs";

test("a selected pair with pending market or macro evidence bypasses the workspace cache", () => {
  const marketPending = { daily: { market: { source_status: "score_rebuild_pending" } } };
  const macroPending = { daily: {
    market: { source_status: "fresh" }, macro: { source_status: "missing_score" },
  } };
  assert.equal(exactMarketScoreNeedsRefresh(marketPending, "EUR"), true);
  assert.equal(exactMarketScoreNeedsRefresh(macroPending, "USDT"), true);
  assert.equal(exactMarketScoreNeedsRefresh({ daily: {
    market: { source_status: "fresh" }, macro: { source_status: "stale_source" },
  } }, "USDT"), false);
  assert.equal(exactMarketScoreNeedsRefresh(marketPending, null), false);
  assert.equal(exactMarketScoreNeedsRefresh({ daily: {
    market: { source_status: "fresh" }, macro: { source_status: "fresh" },
    technical: { source_status: "fresh" },
  } }, "EUR"), false);
});
