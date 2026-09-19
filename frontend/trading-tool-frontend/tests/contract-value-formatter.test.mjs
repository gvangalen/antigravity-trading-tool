import assert from "node:assert/strict";
import test from "node:test";

import { formatExecutionMode } from "../lib/contractValueFormatter.mjs";

test("execution mode is localized without exposing canonical enum values", () => {
  assert.equal(formatExecutionMode("fixed", "nl-NL"), "Vast bedrag");
  assert.equal(formatExecutionMode("fixed", "en-US"), "Fixed amount");
  assert.equal(formatExecutionMode("fixed", "de-DE"), "Fester Betrag");
  assert.equal(formatExecutionMode("future_internal_mode", "nl"), "");
});
