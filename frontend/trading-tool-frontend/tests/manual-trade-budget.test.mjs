import test from 'node:test';
import assert from 'node:assert/strict';
import { manualTradeAvailableQuote } from '../lib/bot/manualTradeBudget.mjs';

test('manual Paper zero caps leave virtual cash available', () => {
  assert.deepEqual(manualTradeAvailableQuote({
    totalBudget: 0, invested: 0, dailyLimit: 0, todaySpent: 0,
    maxOrder: 0, isLive: false, paperCash: 20,
  }), { remainingBudget: 20, available: 20 });
  assert.equal(manualTradeAvailableQuote({
    totalBudget: 0, invested: 0, dailyLimit: 0, todaySpent: 0,
    maxOrder: 0, isLive: false, paperCash: null,
  }).available, 0);
});

test('positive Paper caps still limit order size and Live requires total budget', () => {
  assert.equal(manualTradeAvailableQuote({
    totalBudget: 100, invested: 30, dailyLimit: 25, todaySpent: 10,
    maxOrder: 12, isLive: false, paperCash: 80,
  }).available, 12);
  assert.equal(manualTradeAvailableQuote({
    totalBudget: 0, invested: 0, dailyLimit: 0, todaySpent: 0,
    maxOrder: 0, isLive: true,
  }).available, 0);
});
