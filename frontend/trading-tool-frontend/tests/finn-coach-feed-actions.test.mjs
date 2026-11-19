import assert from "node:assert/strict";
import test from "node:test";

import { canDiscussFeedItem, canUpdateFeedStatus } from "../lib/finnCoachFeedActions.mjs";
import { coachFeedDiscussionQuestion } from "../lib/finnCommandSearch.js";

test("watchlist feed discussion uses the exact pair and remains advisory", () => {
  const prompt = coachFeedDiscussionQuestion({
    event_type: "watchlist_added", symbol: "BTC",
    evidence: { trading_pair: "BTC/USDT", market_id: 34 },
  }, "nl");
  assert.match(prompt, /BTC\/USDT/);
  assert.match(prompt, /wijzig of sla niets op/i);
  assert.doesNotMatch(prompt, /BTC\/EUR/);
  const unpaired = coachFeedDiscussionQuestion({
    event_type: "watchlist_added", symbol: "AAPL", evidence: { trading_pair: "AAPL" },
  }, "nl");
  assert.match(unpaired, /leid geen handelspaar af/i);
});

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
