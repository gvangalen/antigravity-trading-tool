import test from "node:test";
import assert from "node:assert/strict";

import { visibleCoachFeedItems } from "../lib/finnCoachFeedVisible.mjs";

const now = Date.parse("2026-11-19T12:00:00Z");
const item = (id, event_type = "bot_decision", status = "unread", created_at = "2026-11-19T11:00:00Z", priority = 1) =>
  ({ id, event_type, status, created_at, priority });

test("recent unread report remains in three visible updates", () => {
  const rows = [item("a"), item("b"), item("c"), item("report", "daily_report_ready")];
  assert.deepEqual(visibleCoachFeedItems(rows, now).map((row) => row.id), ["report", "c", "b"]);
});

test("handled and old reports do not displace current updates", () => {
  const rows = [item("a"), item("b"), item("c"),
    item("handled", "daily_report_ready", "handled"),
    item("old", "periodic_report_ready", "unread", "2026-11-16T11:00:00Z")];
  assert.deepEqual(visibleCoachFeedItems(rows, now).map((row) => row.id), ["c", "b", "a"]);
});

test("recent weekly trade reflection stays visible", () => {
  const rows = [item("a"), item("b"), item("c"), item("reflection", "weekly_reflection")];
  assert.deepEqual(visibleCoachFeedItems(rows, now).map((row) => row.id), ["reflection", "c", "b"]);
});

test("risk and confirmation outrank a fresh report and routine journey cards", () => {
  const rows = [item("watchlist", "watchlist_added"), item("report", "daily_report_ready"),
    item("risk", "position_risk", "unread", "2026-11-19T09:00:00Z", 4),
    item("proposal", "proposal_pending", "unread", "2026-11-19T08:00:00Z", 5)];
  assert.deepEqual(visibleCoachFeedItems(rows, now).map((row) => row.id),
    ["proposal", "risk", "report"]);
});

test("a new report remains visible behind several urgent cards", () => {
  const rows = [item("risk-a", "position_risk", "unread", "2026-11-19T10:00:00Z", 4),
    item("risk-b", "data_blocked", "unread", "2026-11-19T09:00:00Z", 4),
    item("risk-c", "plan_review", "unread", "2026-11-19T08:00:00Z", 4),
    item("report", "daily_report_ready")];
  assert.deepEqual(visibleCoachFeedItems(rows, now).map((row) => row.id),
    ["risk-a", "risk-b", "report"]);
});

test("a discussed card moves to history and cannot crowd out another next step", () => {
  const rows = [item("discussed", "strategy_next_step", "read", "2026-11-19T11:59:00Z", 4),
    item("next", "analysis_ready", "unread", "2026-11-19T09:00:00Z", 2)];
  assert.deepEqual(visibleCoachFeedItems(rows, now).map((row) => row.id), ["next"]);
});
