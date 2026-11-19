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

test("journey feed questions reread current scores and strategy state", () => {
  const analysis = coachFeedDiscussionQuestion({ event_type: "analysis_ready", symbol: "BTC",
    evidence: { trading_pair: "BTC/USDT", market_id: 34 } }, "nl");
  assert.match(analysis, /actuele benchmark/);
  assert.match(analysis, /BTC\/USDT/);
  assert.match(analysis, /Maak niets aan/);
  const strategy = coachFeedDiscussionQuestion({ event_type: "strategy_next_step", symbol: "BTC",
    evidence: { trading_pair: "BTC/USDT", setup_name: "BTC plan" } }, "nl");
  assert.match(strategy, /inmiddels een strategie/);
  assert.match(strategy, /BTC plan/);
  const paper = coachFeedDiscussionQuestion({ event_type: "paper_next_step", symbol: "BTC",
    evidence: { trading_pair: "BTC/USDT", setup_name: "BTC plan" } }, "nl");
  assert.match(paper, /Paper-proef/);
  assert.match(paper, /Activeer of verhandel niets/);
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
