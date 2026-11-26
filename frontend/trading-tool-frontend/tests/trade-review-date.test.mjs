import assert from 'node:assert/strict';
import test from 'node:test';
import { formatTradeReviewDate } from '../lib/report/tradeReviewDate.mjs';

test('a closed trade renders its timestamp with the local offset', () => {
  const text = formatTradeReviewDate('2026-10-30T14:45:00', 'nl-NL');
  assert.match(text, /30 okt 2026/);
  assert.match(text, /15:45/);
  assert.match(text, /CET/);
});

test('invalid trade timestamps do not crash the reflection list', () => {
  assert.equal(formatTradeReviewDate('not-a-timestamp', 'nl-NL'), '');
});

test('trade timestamps at a week boundary use the reflection time zone', () => {
  const instant = '2026-11-01T11:00:00Z';
  assert.match(formatTradeReviewDate(instant, 'nl-NL', 'Pacific/Kiritimati'), /2 nov 2026/);
  assert.match(formatTradeReviewDate(instant, 'nl-NL', 'Pacific/Kiritimati'), /01:00/);
  assert.match(formatTradeReviewDate(instant, 'nl-NL', 'Europe\/Amsterdam'), /1 nov 2026/);
});
