import assert from 'node:assert/strict';
import test from 'node:test';
import { coachFeedDiscussionPrompt, coachFeedQuoteCurrency, coachFeedDraftWasEdited } from '../src/services/coachFeedDiscussion.ts';

test('edited mobile feed question is marked separately from the default prompt', () => {
  assert.equal(coachFeedDraftWasEdited('feed-1', 'Bespreek BTC/USDT', 'Bespreek BTC/USDT'), false);
  assert.equal(coachFeedDraftWasEdited('feed-1', 'Bespreek BTC/USDT', 'Hoe laat is het op Mars?'), true);
  assert.equal(coachFeedDraftWasEdited(undefined, 'Bespreek BTC/USDT', 'Andere vraag'), false);
});

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

test('mobile Paper follow-up is advisory and exact-pair scoped', () => {
  const prompt = coachFeedDiscussionPrompt({ event_type: 'paper_next_step', symbol: 'BTC',
    evidence: { trading_pair: 'BTC/USDT', setup_name: 'BTC plan' },
    title: 'Paper-proef', description: '' }, 'nl');
  assert.match(prompt, /BTC\/USDT/);
  assert.match(prompt, /Activeer of verhandel niets/);
});

test('mobile reflection follows only a filled Paper sale', () => {
  const filled = coachFeedDiscussionPrompt({ event_type: 'bot_decision', symbol: 'BTC',
    evidence: { action: 'sell', status: 'executed', order_status: 'filled' },
    title: 'Verkoop', description: '' }, 'nl');
  const pending = coachFeedDiscussionPrompt({ event_type: 'bot_decision', symbol: 'BTC',
    evidence: { action: 'sell', status: 'executed' },
    title: 'Verkoop', description: '' }, 'nl');
  assert.match(filled, /reflectievraag/);
  assert.doesNotMatch(pending, /reflectievraag/);
});
