import test from "node:test";
import assert from "node:assert/strict";

import { visibleCoachFeedItems } from "../lib/finnCoachFeedVisible.mjs";

const now = Date.parse("2026-11-19T12:00:00Z");
const item = (id, event_type = "bot_decision", status = "unread", created_at = "2026-11-19T11:00:00Z") =>
  ({ id, event_type, status, created_at });

test("recent unread report remains in three visible updates", () => {
  const rows = [item("a"), item("b"), item("c"), item("report", "daily_report_ready")];
  assert.deepEqual(visibleCoachFeedItems(rows, now).map((row) => row.id), ["a", "b", "report"]);
});

test("handled and old reports do not displace current updates", () => {
  const rows = [item("a"), item("b"), item("c"),
    item("handled", "daily_report_ready", "handled"),
    item("old", "periodic_report_ready", "unread", "2026-11-16T11:00:00Z")];
  assert.deepEqual(visibleCoachFeedItems(rows, now).map((row) => row.id), ["a", "b", "c"]);
});

test("recent weekly trade reflection stays visible", () => {
  const rows = [item("a"), item("b"), item("c"), item("reflection", "weekly_reflection")];
  assert.deepEqual(visibleCoachFeedItems(rows, now).map((row) => row.id), ["a", "b", "reflection"]);
});
