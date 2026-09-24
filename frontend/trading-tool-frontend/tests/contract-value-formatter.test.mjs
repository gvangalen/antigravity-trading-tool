import assert from "node:assert/strict";
import test from "node:test";

import { formatDraftCardValue, formatExecutionMode } from "../lib/contractValueFormatter.mjs";

test("execution mode is localized without exposing canonical enum values", () => {
  assert.equal(formatExecutionMode("fixed", "nl-NL"), "Vast bedrag");
  assert.equal(formatExecutionMode("fixed", "en-US"), "Fixed amount");
  assert.equal(formatExecutionMode("fixed", "de-DE"), "Fester Betrag");
  assert.equal(formatExecutionMode("future_internal_mode", "nl"), "");
});

test("strategy draft renders typed targets and risk without internal values", () => {
  assert.equal(formatDraftCardValue([{ price: 82000 }], "nl-NL"), "82.000");
  assert.equal(formatDraftCardValue([{ price: 82000 }, { price: 86000 }], "nl-NL"), "82.000, 86.000");
  assert.equal(formatDraftCardValue([{ target: "10% profit" }, { target: "20% profit" }], "nl-NL"), "10% profit, 20% profit");
  assert.equal(formatDraftCardValue("cautious", "nl-NL"), "Voorzichtig");
  assert.equal(formatDraftCardValue("moderate", "nl-NL"), "Gebalanceerd");
  assert.equal(formatDraftCardValue("cautious", "en-US"), "Cautious");
  assert.equal(formatDraftCardValue({ internal_id: 42 }, "nl-NL"), "");
});
