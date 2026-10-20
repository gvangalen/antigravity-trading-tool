import assert from "node:assert/strict";
import test from "node:test";

import { restoreOnboardingIndicator } from "../lib/onboardingIndicatorSelection.mjs";

test("completed onboarding restores the saved indicator by stable name across languages", () => {
  const preference = {
    scope: "symbol_override",
    indicators: [{ indicator: "price", priority: 1 }],
  };
  const catalog = [{ name: "price", display_name: "Price" }];

  assert.deepEqual(restoreOnboardingIndicator(preference, catalog, true), catalog[0]);
  assert.deepEqual(restoreOnboardingIndicator(preference, [], true), {
    name: "price",
    display_name: "price",
  });
});

test("a default or incomplete indicator is never counted as a chosen onboarding step", () => {
  const configured = { scope: "symbol_override", indicators: [{ indicator: "dxy" }] };
  assert.equal(restoreOnboardingIndicator(configured, [], false), null);
  assert.equal(restoreOnboardingIndicator({ ...configured, scope: "empty" }, [], true), null);
  assert.equal(restoreOnboardingIndicator({ scope: "symbol_override", indicators: [] }, [], true), null);
});
