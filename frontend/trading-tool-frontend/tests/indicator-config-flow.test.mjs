import assert from "node:assert/strict";
import test from "node:test";

import { persistIndicatorConfiguration, indicatorConfigFailureMessage } from "../lib/indicatorConfigFlow.mjs";

const input = { mode: "add", indicator: "volume", category: "market", assetSymbol: "BTC" };

test("duplicate selection fails before custom settings change", async () => {
  const events = [];
  const duplicate = Object.assign(new Error("duplicate"), { status: 409 });
  await assert.rejects(persistIndicatorConfiguration({
    ...input, draft: { score_mode: "custom", weight: 2, rules: [1, 2, 3, 4, 5] },
    onSubmitAction: async () => { events.push("select"); throw duplicate; },
    saveCustomRules: async () => events.push("rules"),
    updateIndicatorSettings: async () => events.push("settings"),
  }), { status: 409, indicatorCreated: false });
  assert.deepEqual(events, ["select"]);
});

test("custom settings save all five rules and chosen weight in one request", async () => {
  const events = [];
  const rules = [1, 2, 3, 4, 5];
  await persistIndicatorConfiguration({
    ...input, draft: { score_mode: "custom", weight: 2, rules },
    onSubmitAction: async () => events.push("select"),
    saveCustomRules: async (payload) => events.push(payload),
    updateIndicatorSettings: async () => events.push("unexpected settings call"),
  });
  assert.deepEqual(events, ["select", {
    category: "market", indicator: "volume", symbol: "BTC", rules, weight: 2,
  }]);
});

test("validation error shows server detail; failed settings after add are described accurately", async () => {
  const validation = Object.assign(new Error("invalid"), {
    status: 422, body: JSON.stringify({ detail: "Onvoldoende historische metingen." }),
  });
  assert.equal(indicatorConfigFailureMessage({
    error: validation, indicatorLabel: "Volume", assetSymbol: "BTC", actionFailed: "Mislukt",
  }), "Onvoldoende historische metingen.");

  await assert.rejects(persistIndicatorConfiguration({
    ...input, draft: { score_mode: "standard", weight: 1 },
    onSubmitAction: async () => {},
    saveCustomRules: async () => {},
    updateIndicatorSettings: async () => { throw validation; },
  }), { indicatorCreated: true });
  assert.match(indicatorConfigFailureMessage({
    error: validation, indicatorLabel: "Volume", assetSymbol: "BTC", actionFailed: "Mislukt",
  }), /toegevoegd, maar.*niet opgeslagen/);
});
