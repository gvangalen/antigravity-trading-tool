import assert from "node:assert/strict";
import test from "node:test";

import { canDiscussFeedItem, canUpdateFeedStatus } from "../lib/finnCoachFeedActions.mjs";

test("historical handled missing-score card remains discussable without reopening its status", () => {
  const card = { event_type: "data_blocked", status: "handled" };
  assert.equal(canDiscussFeedItem(card, true), true);
  assert.equal(canDiscussFeedItem(card, false), false);
  assert.equal(canUpdateFeedStatus(card), false);
});

test("active cards remain discussable while old reports do not start a chat", () => {
  assert.equal(canDiscussFeedItem({ event_type: "bot_decision", status: "read" }, false), true);
  assert.equal(canUpdateFeedStatus({ event_type: "bot_decision", status: "read" }), true);
  assert.equal(canDiscussFeedItem({ event_type: "daily_report_ready", status: "read" }, true), false);
});
