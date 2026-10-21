import assert from "node:assert/strict";
import test from "node:test";

import { recordedBotDecision } from "../lib/report/botDecisionPresentation.mjs";

test("a report without a recorded decision cannot claim a hold or unmet criteria", () => {
  assert.equal(recordedBotDecision(null), null);
  assert.equal(recordedBotDecision("{}"), null);
  assert.equal(recordedBotDecision({ bot_name: "Paused Paper bot" }), null);
  assert.equal(recordedBotDecision("invalid"), null);
});

test("a saved hold remains a recorded decision when its action is present", () => {
  assert.deepEqual(recordedBotDecision('{"bot_name":"Paper bot","action":"hold"}'), {
    bot_name: "Paper bot", action: "hold",
  });
});
