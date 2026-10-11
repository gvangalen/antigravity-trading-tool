import assert from "node:assert/strict";
import test from "node:test";

import { hasPartialSetupScoreConditions, hasSetupScoreConditions, setupScorePayload } from "../lib/setup/scoreConditions.mjs";

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
