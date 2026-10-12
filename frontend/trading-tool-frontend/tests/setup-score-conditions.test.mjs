import assert from "node:assert/strict";
import test from "node:test";

import { hasPartialSetupScoreConditions, hasSetupScoreConditions, setupScoreOriginKey, setupScorePayload } from "../lib/setup/scoreConditions.mjs";

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
