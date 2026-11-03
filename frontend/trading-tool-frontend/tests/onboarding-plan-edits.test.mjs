import assert from "node:assert/strict";
import test from "node:test";
import { resolveOnboardingStrategyDetails, resolveSavedOnboardingPlan, setupPatchForOnboarding, strategyPatchForOnboarding } from "../lib/onboarding/planEdits.mjs";

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

test("returning from Automation selects the exact strategy among plans for one asset", () => {
  const setups = [
    { id: 41, symbol: "BTC", quote_currency: "EUR" },
    { id: 42, symbol: "BTC", quote_currency: "USDT" },
  ];
  const strategies = [
    { id: 10, setup_id: 41, name: "EUR plan" },
    { id: 11, setup_id: 42, name: "USDT plan" },
  ];
  const chosen = resolveSavedOnboardingPlan({
    symbol: "BTC", setups, strategies, fallbackSetup: setups[0], setupId: 42, strategyId: 11,
  });
  assert.equal(chosen.setup.id, 42);
  assert.equal(chosen.strategy.id, 11);
  assert.equal(chosen.invalid, false);
  assert.equal(resolveSavedOnboardingPlan({
    symbol: "BTC", setups, strategies, fallbackSetup: setups[0], setupId: 41, strategyId: 11,
  }).invalid, true);
  assert.equal(resolveSavedOnboardingPlan({
    symbol: "BTC", setups, strategies, fallbackSetup: setups[0], setupId: 42, strategyId: 99,
  }).invalid, true);
});

test("onboarding hydrates a Smart DCA curve from the detailed strategy list", () => {
  const bySetup = { id: 17, setup_id: 42, execution_mode: "custom", base_amount: 10, decision_curve_id: 8, decision_curve: null };
  const detailed = { ...bySetup, decision_curve: { interpolation: "linear", points: [
    { x: 10, y: 1.5 }, { x: 80, y: 0.5 },
  ] } };
  assert.deepEqual(resolveOnboardingStrategyDetails(bySetup, [detailed], 42), { invalid: false, strategy: detailed });
  assert.equal(resolveOnboardingStrategyDetails(bySetup, [bySetup], 42).invalid, true);
  assert.equal(resolveOnboardingStrategyDetails(bySetup, [detailed], 41).invalid, true);
  assert.equal(resolveOnboardingStrategyDetails(bySetup, [], 42).invalid, true);
});
