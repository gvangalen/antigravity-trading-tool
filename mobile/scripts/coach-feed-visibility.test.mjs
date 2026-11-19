import assert from 'node:assert/strict';
import test from 'node:test';
import { visibleCoachFeedItems } from '../src/services/coachFeedVisibility.ts';

const now = Date.parse('2026-11-19T12:00:00Z');
const item = (id, event_type, status = 'unread', priority = 1, created_at = '2026-11-19T11:00:00Z') =>
  ({ id, event_type, status, priority, created_at });

test('mobile feed prioritizes risk, then a recent report, then the next step', () => {
  const rows = [item('next', 'strategy_next_step', 'unread', 2),
    item('report', 'periodic_report_ready'),
    item('risk', 'position_risk', 'unread', 4, '2026-11-19T09:00:00Z'),
    item('discussed', 'paper_next_step', 'read', 5)];
  assert.deepEqual(visibleCoachFeedItems(rows, now).map((row) => row.id),
    ['risk', 'report', 'next']);
});

test('mobile feed keeps a new report visible behind three urgent updates', () => {
  const rows = [item('a', 'position_risk', 'unread', 4),
    item('b', 'plan_review', 'unread', 4),
    item('c', 'data_blocked', 'unread', 4),
    item('report', 'daily_report_ready')];
  const visible = visibleCoachFeedItems(rows, now);
  assert.equal(visible.length, 3);
  assert.equal(visible[2].id, 'report');
});
