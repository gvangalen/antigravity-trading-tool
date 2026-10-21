import assert from "node:assert/strict";
import test from "node:test";

import { formatBenchmarkScore, indicatorSourceFreshness, validatedDayEvidence } from "../lib/workspace/canonicalScorePresentation.mjs";

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

test("source freshness remains current when scoring is unavailable", () => {
  assert.equal(indicatorSourceFreshness({ status: "available", stale: false }), "current");
  assert.equal(indicatorSourceFreshness({ status: "available", stale: true }), "stale");
  assert.equal(indicatorSourceFreshness({ status: "insufficient_data" }), "unavailable");
});

test("the stored decimal benchmark is displayed consistently with FINN", () => {
  assert.equal(formatBenchmarkScore(33.333, "nl"), "33,3");
  assert.equal(formatBenchmarkScore(33.333, "en"), "33.3");
  assert.equal(formatBenchmarkScore(40, "de"), "40");
  assert.equal(formatBenchmarkScore(null, "nl"), "—");
});
