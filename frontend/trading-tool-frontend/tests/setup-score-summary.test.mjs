import assert from "node:assert/strict";
import test from "node:test";

import { formatSetupScoreConditions } from "../lib/setup/scoreConditionSummary.mjs";

const copy = {
  notReady: "Nog niet compleet",
  noScoreConditions: "Geen scorevoorwaarden",
  noLimit: "geen grens",
  from: "vanaf",
  through: "tot en met",
  market: "markt",
  macro: "macro",
  technical: "technisch",
};

test("a market preset does not invent macro or technical score limits", () => {
  const setup = {
    min_market_score: 26,
    max_market_score: 45,
    min_macro_score: null,
    max_macro_score: null,
    min_technical_score: null,
    max_technical_score: null,
  };
  assert.equal(formatSetupScoreConditions(setup, copy), "markt 26–45 · macro geen grens · technisch geen grens");
});

test("custom partial bounds and an unfiltered setup remain distinguishable", () => {
  assert.equal(formatSetupScoreConditions({ min_macro_score: 30 }, copy), "markt geen grens · macro vanaf 30 · technisch geen grens");
  assert.equal(formatSetupScoreConditions({ max_technical_score: 80 }, copy), "markt geen grens · macro geen grens · technisch tot en met 80");
  assert.equal(formatSetupScoreConditions({}, copy), "Geen scorevoorwaarden");
  assert.equal(formatSetupScoreConditions(null, copy), "Nog niet compleet");
});
