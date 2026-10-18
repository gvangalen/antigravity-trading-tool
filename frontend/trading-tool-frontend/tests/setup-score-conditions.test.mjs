import assert from "node:assert/strict";
import test from "node:test";
import { MARKET_CONDITIONS, editedCustomScorePayload, hasPartialSetupScoreConditions, hasSetupScoreConditions, marketConditionChoiceFromSetup, marketConditionPayload, mayKeepUnfilteredTrade, setupScoreOriginKey } from "../lib/setup/scoreConditions.mjs";

test("five cards store disjoint bounds on the combined benchmark only", () => {
  assert.equal(MARKET_CONDITIONS.length, 5);
  assert.equal(MARKET_CONDITIONS[0].min, 0);
  assert.equal(MARKET_CONDITIONS.at(-1).max, 100);
  MARKET_CONDITIONS.forEach((band, index) => {
    if (index) assert.equal(MARKET_CONDITIONS[index - 1].max + 1, band.min);
    const payload = marketConditionPayload(band.id);
    assert.equal(payload.min_benchmark_score, band.min);
    assert.equal(payload.max_benchmark_score, band.max);
    for (const category of ["market", "macro", "technical"]) {
      assert.equal(payload[`min_${category}_score`], null);
      assert.equal(payload[`max_${category}_score`], null);
    }
    assert.equal(marketConditionChoiceFromSetup(payload), band.id);
  });
});

test("custom stores only a chosen benchmark range", () => {
  const payload = editedCustomScorePayload({}, [18, 47]);
  assert.equal(payload.min_benchmark_score, 18);
  assert.equal(payload.max_benchmark_score, 47);
  assert.equal(marketConditionChoiceFromSetup(payload), "custom");
  assert.equal(hasPartialSetupScoreConditions(payload), false);
});

test("off clears all bounds and legacy fields are not silently re-saved", () => {
  const off = marketConditionPayload("off");
  assert.equal(hasSetupScoreConditions(off), false);
  assert.equal(marketConditionChoiceFromSetup(off), "off");
  assert.equal(marketConditionChoiceFromSetup({ min_market_score: 26, max_market_score: 45 }), "custom");
  const rewritten = marketConditionPayload("custom", { min_benchmark_score: 26, max_benchmark_score: 45 });
  assert.equal(rewritten.min_market_score, null);
  assert.equal(rewritten.max_market_score, null);
});

test("saved and partial benchmark bounds keep their provenance", () => {
  const complete = { min_benchmark_score: 20, max_benchmark_score: 60 };
  assert.equal(setupScoreOriginKey(false, null, false), "scoreDefaultOrigin");
  assert.equal(setupScoreOriginKey(true, complete, false), "scoreSavedOrigin");
  assert.equal(setupScoreOriginKey(true, complete, true), "scoreEditedOrigin");
  assert.equal(setupScoreOriginKey(true, { min_benchmark_score: 20 }, false), "scorePartialOrigin");
});

test("only an existing unfiltered trade may retain Off", () => {
  assert.equal(mayKeepUnfilteredTrade(false, { setup_type: "trade" }), false);
  assert.equal(mayKeepUnfilteredTrade(true, { setup_type: "dca" }), false);
  assert.equal(mayKeepUnfilteredTrade(true, { setup_type: "trade" }), true);
  assert.equal(mayKeepUnfilteredTrade(true, { setup_type: "trade", min_benchmark_score: 0, max_benchmark_score: 25 }), false);
});
