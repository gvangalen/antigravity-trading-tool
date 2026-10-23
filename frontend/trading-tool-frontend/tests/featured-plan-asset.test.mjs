import assert from "node:assert/strict";
import test from "node:test";
import { getFeaturedPlanMessage, resolvePlanWorkspaceSymbol, selectFeaturedPlan } from "../lib/setup/selectFeaturedPlan.mjs";

test("featured plan and best-match badge stay on the selected asset", () => {
  const plans = [
    { setup: { id: 1, symbol: "BTC" }, match: { is_active: true, score: 90 }, bot: { is_active: true } },
    { setup: { id: 2, symbol: "AAPL" }, match: { status: "insufficient_data", is_active: false } },
  ];
  const result = selectFeaturedPlan(plans, "AAPL", 1);
  assert.equal(result.best, null);
  assert.equal(result.featured.setup.id, 2);
  assert.equal(selectFeaturedPlan(plans, "MSFT", 1).featured, null);
});

test("plan page follows the selected asset when navigation has no symbol", () => {
  assert.equal(resolvePlanWorkspaceSymbol({ selectedAsset: "AAPL", fallbackSymbol: "BTC" }), "AAPL");
  assert.equal(resolvePlanWorkspaceSymbol({ routeSymbol: "ETH", selectedAsset: "AAPL" }), "ETH");
});

test("switching to an asset without a plan leaves a safe empty coach state", () => {
  const plans = [{ setup: { id: 1, symbol: "BTC" }, hasStrategy: true }];
  const { featured } = selectFeaturedPlan(plans, "AAPL", 1);
  assert.equal(featured, null);
  assert.equal(getFeaturedPlanMessage({ noPlansBody: "Geen plan voor deze asset." }, featured), "Geen plan voor deze asset.");
});
