import assert from "node:assert/strict";
import test from "node:test";
import { setupPatchForOnboarding, strategyPatchForOnboarding } from "../lib/onboarding/planEdits.mjs";

test("editing a saved weekly DCA plan updates its schedule without changing its pair or identity", () => {
  const saved = {
    id: 42, symbol: "ETH", quote_currency: "EUR", setup_type: "dca", timeframe: "1D",
    name: "ETH rustig", dca_frequency: "weekly", dca_day: "1",
    min_benchmark_score: null, max_benchmark_score: null,
  };
  const draft = {
    name: "ETH rustig", setupType: "dca", timeframe: "1D",
    dcaFrequency: "weekly", dcaDay: "friday", dcaMonthDay: "1",
    min_benchmark_score: 46, max_benchmark_score: 60,
  };
  assert.deepEqual(setupPatchForOnboarding(saved, draft, "off"), { dca_day: "friday" });
  assert.deepEqual(setupPatchForOnboarding(saved, { ...draft, dcaDay: "monday" }, "off"), {});
});

test("changing a score condition clears superseded legacy bounds deliberately", () => {
  const saved = {
    name: "BTC plan", timeframe: "1D", setup_type: "dca", dca_frequency: "weekly", dca_day: "1",
    min_market_score: 20, max_market_score: 60, min_benchmark_score: null, max_benchmark_score: null,
  };
  const draft = {
    name: "BTC plan", timeframe: "1D", setupType: "dca", dcaFrequency: "weekly", dcaDay: "monday",
    min_benchmark_score: 46, max_benchmark_score: 60,
  };
  assert.deepEqual(setupPatchForOnboarding(saved, draft, "custom"), {});
  const patch = setupPatchForOnboarding(saved, draft, "heavy_pressure");
  assert.equal(patch.min_benchmark_score, 0);
  assert.equal(patch.max_benchmark_score, 25);
  assert.equal(patch.min_market_score, null);
  assert.equal(patch.max_market_score, null);
});

test("updating a Smart DCA base amount preserves its curve and setup association", () => {
  const saved = {
    id: 15, setup_id: 42, name: "Smart ETH", execution_mode: "custom", base_amount: 80,
    decision_curve: { mode: "step", bands: [50, 100, 150] },
  };
  const patch = strategyPatchForOnboarding(saved, { name: "Smart ETH", baseAmount: "90" }, false);
  assert.deepEqual(patch, { base_amount: 90 });
});
