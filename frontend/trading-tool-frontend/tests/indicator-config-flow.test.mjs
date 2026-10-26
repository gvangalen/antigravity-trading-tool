import assert from "node:assert/strict";
import test from "node:test";

import { persistIndicatorConfiguration, indicatorConfigFailureMessage } from "../lib/indicatorConfigFlow.mjs";

const input = { mode: "add", indicator: "volume", category: "market", assetSymbol: "BTC" };

test("duplicate custom selection is rejected before adding data", async () => {
  const events = [];
  const duplicate = Object.assign(new Error("duplicate"), { status: 409 });
  await assert.rejects(persistIndicatorConfiguration({
    ...input, draft: { score_mode: "custom", weight: 2, rules: [1, 2, 3, 4, 5] },
    onSubmitAction: async () => events.push("unexpected select"),
    saveCustomRules: async () => { events.push("create-only rules"); throw duplicate; },
    updateIndicatorSettings: async () => events.push("settings"),
  }), { status: 409, indicatorCreated: false });
  assert.deepEqual(events, ["create-only rules"]);
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
  assert.deepEqual(events, [{
    category: "market", indicator: "volume", symbol: "BTC", rules, weight: 2, create_only: true,
  }, "select"]);
});

test("custom rules remain available when source data is temporarily missing", async () => {
  const unavailable = Object.assign(new Error("source unavailable"), { status: 503 });
  const error = await persistIndicatorConfiguration({
    ...input, draft: { score_mode: "custom", weight: 1, rules: [1, 2, 3, 4, 5] },
    onSubmitAction: async () => { throw unavailable; },
    saveCustomRules: async () => {},
    updateIndicatorSettings: async () => {},
  }).then(() => null, (caught) => caught);
  assert.equal(error?.configurationSaved, true);
  assert.equal(error?.indicatorCreated, false);
  assert.match(indicatorConfigFailureMessage({
    error, indicatorLabel: "Volume", assetSymbol: "BTC", actionFailed: "Mislukt",
  }), /scoreregels zijn opgeslagen/);
});

test("temporary source limit preserves pending indicator through settings save", async () => {
  const events = [];
  const result = await persistIndicatorConfiguration({
    ...input, indicator: "ma_200", category: "technical",
    draft: { score_mode: "standard", weight: 1.3 },
    onSubmitAction: async () => {
      events.push("configured");
      return { status: "pending_source", value: null, score: null };
    },
    saveCustomRules: async () => events.push("unexpected rules"),
    updateIndicatorSettings: async () => events.push("settings"),
  });
  assert.deepEqual(events, ["configured", "settings"]);
  assert.deepEqual(result, { pendingSource: true });
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
