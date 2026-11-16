import assert from "node:assert/strict";
import test from "node:test";

import { coachFeedDetailsHref } from "../lib/finnCoachFeedLinks.mjs";

test("weekly coaching links to its saved reflection week", () => {
  assert.equal(coachFeedDetailsHref({subject_type: "reflection",
    evidence: {week_start: "2026-11-09"}}),
  "/report?reflection_week=2026-11-09#finn-trades-title");
});

test("pair-scoped suggestion preserves the exact quote", () => {
  assert.equal(coachFeedDetailsHref({subject_type: "asset", symbol: "BTC",
    evidence: {market_id: 12, trading_pair: "BTC/USDT"}}),
  "/asset?symbol=BTC&variant=v3&tab=market&quote=USDT");
  assert.equal(coachFeedDetailsHref({subject_type: "asset", symbol: "AAPL",
    evidence: {trading_pair: "AAPL"}}), "/asset?symbol=AAPL");
});

test("missing-indicator bot notice opens the manual trade review", () => {
  assert.equal(coachFeedDetailsHref({subject_type: "bot", subject_id: 42,
    symbol: "ETH", event_type: "data_blocked",
    evidence: {missing_indicators: {macro: ["US10Y"]}}}),
  "/bot?symbol=ETH&bot_id=42&focus=trade");
});
