import assert from 'node:assert/strict';
import test from 'node:test';
import { coachFeedDiscussionPrompt, coachFeedQuoteCurrency } from '../src/services/coachFeedDiscussion.ts';

test('mobile coach prompts reread the exact pair and stay advisory', () => {
  const item = { event_type: 'strategy_next_step', symbol: 'BTC',
    evidence: { trading_pair: 'BTC/USDT', setup_name: 'Mijn plan' },
    title: 'Strategie ontbreekt', description: '' };
  const prompt = coachFeedDiscussionPrompt(item, 'nl');
  assert.match(prompt, /BTC\/USDT/);
  assert.match(prompt, /Mijn plan/);
  assert.match(prompt, /Maak niets aan/);
  assert.doesNotMatch(prompt, /BTC\/EUR/);
  assert.equal(coachFeedQuoteCurrency(item), 'USDT');
  assert.equal(coachFeedQuoteCurrency({ ...item, evidence: { trading_pair: 'BTC/USDT/OTHER' } }), undefined);
});

test('mobile Paper decision asks for historical execution evidence', () => {
  const prompt = coachFeedDiscussionPrompt({ event_type: 'bot_decision', symbol: 'AAPL',
    title: 'Paper-besluit', description: '' }, 'nl');
  assert.match(prompt, /botgeschiedenis/);
  assert.match(prompt, /geen actuele koers/);
});
