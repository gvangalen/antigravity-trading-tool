import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";

const source = fs.readFileSync(
  path.resolve("app/(protected)/bot/page.jsx"),
  "utf8",
);

test("bot onboarding derives the only owner-visible strategy without putting an id in the route", () => {
  assert.match(source, /symbolStrategies\.length === 1 \? symbolStrategies\[0\] : null/);
  assert.match(source, /strategy_id: matchingStrategy\?\.id \?\? null/);
});

test("bot onboarding does not guess when multiple strategies match the active asset", () => {
  assert.match(source, /symbolStrategies\.length === 1/);
  assert.doesNotMatch(source, /symbolStrategies\[0\]\s*\|\|/);
});

test("bot onboarding preserves the Next router state when it consumes handoff parameters", () => {
  assert.match(source, /window\.history\.replaceState\(window\.history\.state, "", newUrl\)/);
  assert.doesNotMatch(source, /window\.history\.replaceState\(\{\},\s*['"]['"],\s*newUrl\)/);
});
