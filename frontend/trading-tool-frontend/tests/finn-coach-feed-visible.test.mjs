import test from "node:test";
import assert from "node:assert/strict";

import { visibleCoachFeedItems } from "../lib/finnCoachFeedVisible.mjs";

const item = (id, created_at, extra = {}) => ({
  id, created_at, status: "unread", event_type: "bot_decision", ...extra,
});

test("the dashboard shows the three newest notifications", () => {
  const rows = [
    item("old-report", "2026-11-19T14:00:00Z", { event_type: "daily_report_ready", priority: 1 }),
    item("bot", "2026-11-20T00:03:00Z", { activity_at: "2026-11-20T00:03:00Z" }),
    item("new-report", "2026-11-20T06:20:00Z", { event_type: "daily_report_ready" }),
    item("older", "2026-11-18T12:00:00Z", { priority: 1 }),
  ];
  assert.deepEqual(visibleCoachFeedItems(rows).map((row) => row.id),
    ["new-report", "bot", "old-report"]);
});

test("a bot's displayed activity time determines its position", () => {
  const rows = [
    item("bot", "2026-11-19T08:00:00Z", { activity_at: "2026-11-20T00:03:00Z" }),
    item("report", "2026-11-19T22:00:00Z", { event_type: "daily_report_ready" }),
  ];
  assert.deepEqual(visibleCoachFeedItems(rows).map((row) => row.id), ["bot", "report"]);
});

test("the latest updates remain first regardless of priority", () => {
  const rows = [
    item("report", "2026-11-20T10:00:00Z", { event_type: "daily_report_ready", priority: 1 }),
    item("risk", "2026-11-20T08:00:00Z", { event_type: "position_risk", priority: 4 }),
    item("proposal", "2026-11-20T07:00:00Z", { event_type: "proposal_pending", priority: 5 }),
  ];
  assert.deepEqual(visibleCoachFeedItems(rows).map((row) => row.id),
    ["report", "risk", "proposal"]);
});

test("read and handled notifications follow the same timeline as all updates", () => {
  const rows = [
    item("read", "2026-11-20T10:00:00Z", { status: "read" }),
    item("handled", "2026-11-20T09:00:00Z", { status: "handled" }),
    item("new", "2026-11-20T08:00:00Z"),
  ];
  assert.deepEqual(visibleCoachFeedItems(rows).map((row) => row.id), ["read", "handled", "new"]);
});

test("the compact feed follows the expanded timeline rather than old unread reports", () => {
  const rows = [
    item("old-report-1", "2026-11-22T21:10:00Z", { event_type: "daily_report_ready" }),
    item("old-report-2", "2026-11-23T20:30:00Z", { event_type: "daily_report_ready" }),
    item("today-report", "2026-11-24T04:50:00Z", { event_type: "daily_report_ready", status: "read" }),
    item("analysis-early", "2026-11-24T14:00:00Z", { event_type: "analysis_ready" }),
    item("analysis-latest", "2026-11-24T17:30:00Z", { event_type: "analysis_ready" }),
    item("bot", "2026-11-24T17:33:00Z", { event_type: "bot_decision" }),
  ];
  assert.deepEqual(visibleCoachFeedItems(rows).map((row) => row.id),
    ["bot", "analysis-latest", "analysis-early"]);
  assert.deepEqual(visibleCoachFeedItems(rows.filter((row) => row.id !== "analysis-early"))
    .map((row) => row.id), ["bot", "analysis-latest", "today-report"]);
});
