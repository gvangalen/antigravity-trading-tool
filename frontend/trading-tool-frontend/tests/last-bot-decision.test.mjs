import assert from "node:assert/strict";
import test from "node:test";
import { selectLastBotDecision } from "../lib/bot/lastDecision.mjs";

test("paused bot retains its own last recorded Paper decision in the summary", () => {
  const history = [
    { bot_id: 7, action: "BUY", decision_ts: "2026-10-23T10:00:00Z" },
    { bot_id: 8, action: "HOLD", decision_ts: "2026-10-23T11:00:00Z" },
    { bot_id: 7, action: "HOLD", decision_ts: "2026-10-22T10:00:00Z" },
  ];
  assert.equal(selectLastBotDecision(undefined, history, 7).action, "BUY");
  assert.equal(selectLastBotDecision({ action: "HOLD" }, history, 7).action, "HOLD");
  assert.equal(selectLastBotDecision(undefined, history, 9), null);
});
