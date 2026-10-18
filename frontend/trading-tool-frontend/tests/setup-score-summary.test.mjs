import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { formatSetupScoreConditions } from "../lib/setup/scoreConditionSummary.mjs";
import { MARKET_CONDITIONS } from "../lib/setup/scoreConditions.mjs";

for (const locale of ["nl", "en", "de"]) {
  const dictionary = JSON.parse(await readFile(new URL(`../dictionaries/${locale}.json`, import.meta.url), "utf8"));
  const copy = dictionary.setups.marketConditions;

  test(`${locale}: all saved presets name the benchmark condition`, () => {
    MARKET_CONDITIONS.forEach((band) => {
      const setup = { min_benchmark_score: band.min, max_benchmark_score: band.max };
      const summary = formatSetupScoreConditions(setup, copy);
      assert.equal(summary, `${copy.options[band.id].title} · ${copy.options[band.id].rule}`);
      assert.doesNotMatch(summary, /\d+\s*[–-]\s*\d+/);
    });
  });

  test(`${locale}: custom shows only the benchmark bounds`, () => {
    const summary = formatSetupScoreConditions({ min_benchmark_score: 18, max_benchmark_score: 47 }, copy);
    assert.equal(summary, `${copy.savedCustomTitle}: ${copy.savedBenchmark} ${copy.savedBetween.replace("{min}", "18").replace("{max}", "47")}`);
    assert.equal(formatSetupScoreConditions({}, copy), copy.savedNoConditions);
    assert.equal(formatSetupScoreConditions(null, copy), copy.savedNotReady);
  });
}
