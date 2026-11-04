import assert from "node:assert/strict";
import test from "node:test";

import { currentIndicatorScore, formatBenchmarkScore, hasCompleteDailyBenchmark, indicatorSourceFreshness, normalizedIndicatorPosition, validatedDayEvidence } from "../lib/workspace/canonicalScorePresentation.mjs";

test("a setup-match card requires the current asset's complete daily benchmark", () => {
  const complete = {
    symbol: "BTC",
    daily: { benchmark_score: 0, market: { score: 0 }, macro: { score: 20 }, technical: { score: 40 } },
  };
  assert.equal(hasCompleteDailyBenchmark(complete, "BTC"), true);
  assert.equal(hasCompleteDailyBenchmark(complete, "AAPL"), false);
  assert.equal(hasCompleteDailyBenchmark({ ...complete, daily: { ...complete.daily, macro: { score: null } } }, "BTC"), false);
  assert.equal(hasCompleteDailyBenchmark({ ...complete, daily: { ...complete.daily, benchmark_score: null } }, "BTC"), false);
});

test("an old row score cannot become a visible current indicator score", () => {
  const evidence = { dxy: { score: 100, source_observed_at: "2026-09-22T00:00:00Z" } };
  assert.equal(validatedDayEvidence(null, evidence, "DXY"), null);
  assert.equal(validatedDayEvidence(100, evidence, "DXY"), null);
  assert.equal(validatedDayEvidence(100, { dxy: { ...evidence.dxy, rule_origin: "generated_fallback" } }, "DXY"), null);
  assert.equal(validatedDayEvidence(100, {}, "DXY"), null);
});

test("validated zero score remains a score and aliases resolve to canonical evidence", () => {
  const row = { score: 0, source_observed_at: "2026-10-06T09:00:00Z", rule_origin: "custom" };
  assert.equal(validatedDayEvidence(0, { sp500: row }, "S&P 500"), row);
});

test("a verified individual score can remain visible while its category is incomplete", () => {
  const row = { score: 65, rule_origin: "system_template" };
  assert.equal(validatedDayEvidence(65, { dxy: row }, "DXY"), row);
  assert.equal(currentIndicatorScore({ score: 65 }, row, true, true), 65);
  assert.equal(validatedDayEvidence(null, { dxy: row }, "DXY"), null);
});

test("source freshness remains current when scoring is unavailable", () => {
  assert.equal(indicatorSourceFreshness({ status: "available", stale: false }), "current");
  assert.equal(indicatorSourceFreshness({ status: "available", stale: true }), "stale");
  assert.equal(indicatorSourceFreshness({ status: "insufficient_data" }), "unavailable");
});

test("individual indicator score follows verified evidence, not an older row score", () => {
  const row = { score: 35 };
  const evidence = { score: 65, normalized_value: 68, rule_origin: "system_template" };
  assert.equal(currentIndicatorScore(row, evidence, true, true), 65);
  assert.equal(normalizedIndicatorPosition(evidence), 68);
  assert.equal(currentIndicatorScore(row, null, true, true), null);
  assert.equal(currentIndicatorScore(row, evidence, false, true), null);
  assert.equal(currentIndicatorScore({ score: 0 }, null, true, false), 0);
  assert.equal(normalizedIndicatorPosition({ normalized_value: null }), null);
  assert.equal(normalizedIndicatorPosition({}), null);
});

test("the stored decimal benchmark is displayed consistently with FINN", () => {
  assert.equal(formatBenchmarkScore(33.333, "nl"), "33,3");
  assert.equal(formatBenchmarkScore(33.333, "en"), "33.3");
  assert.equal(formatBenchmarkScore(40, "de"), "40");
  assert.equal(formatBenchmarkScore(null, "nl"), "—");
});
