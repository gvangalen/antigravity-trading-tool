import assert from "node:assert/strict";
import test from "node:test";

import { restoreOnboardingIndicator } from "../lib/onboardingIndicatorSelection.mjs";
import { classifyOnboardingIndicatorSync, classifyOnboardingWorkspaceChoice } from "../lib/onboardingIndicatorSync.mjs";

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

test("saved choices are checked against their current score and source after reload", () => {
  const snapshot = (row) => ({ categories: { macro: { rows: row ? [row] : [] } } });
  assert.equal(classifyOnboardingWorkspaceChoice(snapshot(null), "macro", "sp500"), "failed");
  assert.equal(classifyOnboardingWorkspaceChoice(snapshot({ name: "sp500", value: 6000, score: null, freshness: { stale: false } }), "macro", "sp500"), "pending_score");
  assert.equal(classifyOnboardingWorkspaceChoice(snapshot({ name: "sp500", value: 6000, score: 50, freshness: { stale: true } }), "macro", "sp500"), "pending_score");
  assert.equal(classifyOnboardingWorkspaceChoice(snapshot({ name: "sp500", value: 6000, score: 50, freshness: { stale: false } }), "macro", "sp500"), "ready");
  assert.equal(classifyOnboardingWorkspaceChoice(null, "macro", "sp500"), "unknown");
});

test("a default or incomplete indicator is never counted as a chosen onboarding step", () => {
  const configured = { scope: "symbol_override", indicators: [{ indicator: "dxy" }] };
  assert.equal(restoreOnboardingIndicator(configured, [], false), null);
  assert.equal(restoreOnboardingIndicator({ ...configured, scope: "empty" }, [], true), null);
  assert.equal(restoreOnboardingIndicator({ scope: "symbol_override", indicators: [] }, [], true), null);
});

test("onboarding does not complete a failed or unscored sync as if it were ready", () => {
  assert.equal(classifyOnboardingIndicatorSync({ synced: [], failed: [{ indicator: "sp500" }] }, "sp500"), "failed");
  assert.equal(classifyOnboardingIndicatorSync({ synced: [{ indicator: "sp500", payload: { value: 5800, score: null } }], failed: [] }, "sp500"), "pending_score");
  assert.equal(classifyOnboardingIndicatorSync({ synced: [{ indicator: "ma_200", payload: { value: 1.03, score: null, uitleg: "Geen vastgelegde scoreregel voor deze indicator." } }], failed: [] }, "ma_200"), "missing_rule");
  assert.equal(classifyOnboardingIndicatorSync({ synced: [{ indicator: "ma_200", payload: { value: 1.03, score: 65 } }], failed: [] }, "ma_200"), "ready");
  assert.equal(classifyOnboardingIndicatorSync({ synced: [{ indicator: "sp500", payload: { status: "pending_source", value: null } }], failed: [] }, "sp500"), "failed");
});
