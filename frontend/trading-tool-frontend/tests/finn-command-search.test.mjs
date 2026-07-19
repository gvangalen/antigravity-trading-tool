import assert from "node:assert/strict";
import test from "node:test";

import {
  getCommandTokens,
  getDefaultIndicatorCategory,
  matchesCommandQuery,
  normalizeCommandText,
} from "../lib/finnCommandSearch.js";

test("normalizes accents and punctuation in natural commands", () => {
  assert.equal(normalizeCommandText("Öffne: Ethereum!"), "offne ethereum");
});

test("removes common command words before matching", () => {
  assert.deepEqual(getCommandTokens("Voeg RSI toe aan Technisch"), ["rsi", "technisch"]);
  assert.equal(matchesCommandQuery("RSI technische indicator", "Voeg RSI toe aan Technisch"), true);
});

test("matches asset commands without requiring an exact phrase", () => {
  assert.equal(matchesCommandQuery("ETH Ethereum", "Open Ethereum"), true);
  assert.equal(matchesCommandQuery("ETH Ethereum", "Wissel naar ETH"), true);
  assert.equal(matchesCommandQuery("BTC Bitcoin", "Zoek BTC"), true);
  assert.equal(matchesCommandQuery("BTC Bitcoin", "Open Ethereum"), false);
});

test("matches workspace navigation commands", () => {
  assert.equal(matchesCommandQuery("plan Mijn Plan werkruimte", "Ga naar Mijn Plan"), true);
});

test("chooses the indicator category from the active workspace", () => {
  assert.equal(getDefaultIndicatorCategory("/macro"), "macro");
  assert.equal(getDefaultIndicatorCategory("/market"), "market");
  assert.equal(getDefaultIndicatorCategory("/asset"), "technical");
});
