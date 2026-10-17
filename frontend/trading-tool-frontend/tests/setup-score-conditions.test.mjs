import assert from "node:assert/strict";
import test from "node:test";

import { MARKET_CONDITIONS, editedCustomScorePayload, hasPartialSetupScoreConditions, hasSetupScoreConditions, marketConditionChoiceFromSetup, marketConditionPayload, scoreRangeTouchedFields, setupScoreOriginKey, setupScorePayload } from "../lib/setup/scoreConditions.mjs";

test("saved or duplicated score limits are not labeled as product defaults", () => {
  const copied = {
    min_macro_score: 0, max_macro_score: 70,
    min_technical_score: 40, max_technical_score: 80,
    min_market_score: 20, max_market_score: 60,
  };
  assert.equal(setupScoreOriginKey(false, null, false), "scoreDefaultOrigin");
  assert.equal(setupScoreOriginKey(true, copied, false), "scoreSavedOrigin");
  assert.equal(setupScoreOriginKey(true, copied, true), "scoreEditedOrigin");
  assert.equal(setupScoreOriginKey(true, { min_macro_score: 0 }, false), "scorePartialOrigin");
});

test("five market cards save exact non-overlapping matcher bounds without hidden macro or technical filters", () => {
  assert.equal(MARKET_CONDITIONS.length, 5);
  assert.equal(MARKET_CONDITIONS[0].min, 0);
  assert.equal(MARKET_CONDITIONS.at(-1).max, 100);
  for (let index = 0; index < MARKET_CONDITIONS.length; index += 1) {
    const band = MARKET_CONDITIONS[index];
    if (index) assert.equal(MARKET_CONDITIONS[index - 1].max + 1, band.min);
    const payload = marketConditionPayload(band.id);
    assert.equal(payload.min_market_score, band.min);
    assert.equal(payload.max_market_score, band.max);
    assert.equal(payload.min_macro_score, null);
    assert.equal(payload.max_macro_score, null);
    assert.equal(payload.min_technical_score, null);
    assert.equal(payload.max_technical_score, null);
    assert.equal(marketConditionChoiceFromSetup(payload), band.id);
  }
});

test("no condition and saved custom bounds round-trip without changing older setups", () => {
  const unbounded = marketConditionPayload("off");
  assert.equal(marketConditionChoiceFromSetup(unbounded), "off");
  assert.equal(hasSetupScoreConditions(unbounded), false);
  const legacy = { min_market_score: 20, max_market_score: 60, min_macro_score: 30, max_macro_score: 70 };
  assert.equal(marketConditionChoiceFromSetup(legacy), "custom");
  assert.deepEqual(marketConditionPayload("custom", legacy), {
    min_macro_score: 30, max_macro_score: 70,
    min_technical_score: null, max_technical_score: null,
    min_market_score: 20, max_market_score: 60,
  });
});

test("changing one custom slider handle leaves every other absent limit absent", () => {
  const existing = { min_market_score: 20, max_market_score: null, min_macro_score: null, max_macro_score: 70 };
  assert.deepEqual(editedCustomScorePayload(existing, [30, 70], [40, 80], [20, 60]), {
    min_macro_score: null, max_macro_score: 70,
    min_technical_score: null, max_technical_score: null,
    min_market_score: 20, max_market_score: null,
  });
  assert.deepEqual(editedCustomScorePayload(existing, [30, 70], [40, 80], [15, 60], { min_market_score: true }), {
    min_macro_score: null, max_macro_score: 70,
    min_technical_score: null, max_technical_score: null,
    min_market_score: 15, max_market_score: null,
  });
  // A handle moved 30 → 31 → 30 is still intentionally set to 30.
  const moved = scoreRangeTouchedFields("macro", [30, 70], [31, 70]);
  const returned = scoreRangeTouchedFields("macro", [31, 70], [30, 70], moved);
  assert.deepEqual(returned, { min_macro_score: true });
  assert.deepEqual(editedCustomScorePayload(existing, [30, 70], [40, 80], [20, 60], returned), {
    min_macro_score: 30, max_macro_score: 70,
    min_technical_score: null, max_technical_score: null,
    min_market_score: 20, max_market_score: null,
  });
});

test("a fixed DCA can be saved without score limits, while an existing bounded setup retains its limits", () => {
  const unbounded = setupScorePayload(false, [30, 70], [40, 80], [20, 60]);
  assert.equal(hasSetupScoreConditions(unbounded), false);
  assert.deepEqual(Object.values(unbounded), [null, null, null, null, null, null]);

  const bounded = setupScorePayload(true, [25, 75], [35, 85], [15, 65]);
  assert.equal(hasSetupScoreConditions(bounded), true);
  assert.deepEqual(bounded, {
    min_macro_score: 25, max_macro_score: 75,
    min_technical_score: 35, max_technical_score: 85,
    min_market_score: 15, max_market_score: 65,
  });

  const partialExisting = { min_macro_score: 30 };
  assert.equal(hasPartialSetupScoreConditions(partialExisting), true);
  assert.deepEqual(
    setupScorePayload(true, [30, 70], [40, 80], [20, 60], partialExisting),
    {
      min_macro_score: 30, max_macro_score: null,
      min_technical_score: null, max_technical_score: null,
      min_market_score: null, max_market_score: null,
    }
  );
});
