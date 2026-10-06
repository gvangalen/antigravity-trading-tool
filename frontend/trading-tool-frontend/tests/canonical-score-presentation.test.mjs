import assert from "node:assert/strict";
import test from "node:test";

import { validatedDayEvidence } from "../lib/workspace/canonicalScorePresentation.mjs";

test("an old row score cannot become a visible current indicator score", () => {
  const evidence = { dxy: { score: 100, source_observed_at: "2026-09-22T00:00:00Z" } };
  assert.equal(validatedDayEvidence(null, evidence, "DXY"), null);
  assert.equal(validatedDayEvidence(100, {}, "DXY"), null);
});

test("validated zero score remains a score and aliases resolve to canonical evidence", () => {
  const row = { score: 0, source_observed_at: "2026-10-06T09:00:00Z" };
  assert.equal(validatedDayEvidence(0, { sp500: row }, "S&P 500"), row);
});
