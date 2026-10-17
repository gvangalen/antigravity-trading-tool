import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import { formatSetupScoreConditions } from "../lib/setup/scoreConditionSummary.mjs";
import { MARKET_CONDITIONS } from "../lib/setup/scoreConditions.mjs";

const expectations = {
  nl: {
    preset: ["Zwaar onder druk", "Onder druk", "Geen duidelijke richting", "De markt trekt aan", "Sterke markt"],
    custom: "Eigen voorwaarden: markt tussen 20 en 60; macro vanaf 30; technisch tot en met 80",
    off: "Geen scorevoorwaarden",
    missing: "Nog niet compleet",
  },
  en: {
    preset: ["Heavy pressure", "Under pressure", "No clear direction", "Gaining strength", "Strong market"],
    custom: "Custom conditions: market between 20 and 60; macro from 30; technical through 80",
    off: "No score conditions",
    missing: "Not complete yet",
  },
  de: {
    preset: ["Stark unter Druck", "Unter Druck", "Keine klare Richtung", "Der Markt wird stärker", "Starker Markt"],
    custom: "Eigene Bedingungen: Markt zwischen 20 und 60; Makro ab 30; Technik bis einschließlich 80",
    off: "Keine Score-Bedingungen",
    missing: "Noch nicht vollständig",
  },
};

for (const [locale, expected] of Object.entries(expectations)) {
  const dictionary = JSON.parse(await readFile(new URL(`../dictionaries/${locale}.json`, import.meta.url), "utf8"));
  const copy = dictionary.setups.marketConditions;

  test(`${locale}: all five saved presets use a readable market situation`, () => {
    MARKET_CONDITIONS.forEach((band, index) => {
      const setup = { min_market_score: band.min, max_market_score: band.max };
      const summary = formatSetupScoreConditions(setup, copy);
      assert.ok(summary.startsWith(`${expected.preset[index]} · `), summary);
      assert.equal(summary, `${copy.options[band.id].title} · ${copy.options[band.id].rule}`);
      assert.doesNotMatch(summary, /\d+\s*[–-]\s*\d+/);
    });
  });

  test(`${locale}: custom shows only actual stored limits and preserves one-sided bounds`, () => {
    assert.equal(formatSetupScoreConditions({
      min_market_score: 20,
      max_market_score: 60,
      min_macro_score: 30,
      max_technical_score: 80,
    }, copy), expected.custom);
    assert.equal(formatSetupScoreConditions({}, copy), expected.off);
    assert.equal(formatSetupScoreConditions(null, copy), expected.missing);
  });
}
