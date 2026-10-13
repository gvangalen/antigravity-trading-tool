import assert from 'node:assert/strict';
import test from 'node:test';
import { draftQuestionChoices, hasConfirmableDraft, isCollectingDraft } from '../lib/finnDraftConversation.mjs';

test('incomplete setup uses a question instead of a confirmable card', () => {
  const message = { setupDraft: { missing_inputs: ['dca_frequency'], supplied_inputs: { symbol: 'BTC' } }, state: {} };
  assert.equal(isCollectingDraft(message), true);
  assert.equal(hasConfirmableDraft(message), false);
  assert.deepEqual(draftQuestionChoices(message).map((choice) => choice.reply), ['Wekelijks', 'Maandelijks']);
});

test('complete action needs a server proposal before a review card appears', () => {
  const message = { actionDraft: { missing_inputs: [] }, actions: [{ type: 'v2_proposal', proposal_id: 'server-issued' }] };
  assert.equal(hasConfirmableDraft(message), true);
  assert.equal(isCollectingDraft(message), false);
  assert.equal(hasConfirmableDraft({ ...message, actions: [] }), false);
  assert.equal(hasConfirmableDraft({ ...message, state: { status: 'collecting' } }), false);
});

test('legacy collecting drafts use the same question flow', () => {
  const message = { draft: { type: 'bot' }, state: { status: 'collecting', missing_slots: ['name'] }, canConfirm: false };
  assert.equal(isCollectingDraft(message), true);
  assert.equal(hasConfirmableDraft(message), false);
  assert.deepEqual(draftQuestionChoices(message), []);
});

test('localized choices never invent an amount or a recommendation', () => {
  const message = { actionDraft: { missing_inputs: ['dca_amount_mode'] } };
  for (const locale of ['nl', 'en', 'de']) {
    const choices = draftQuestionChoices(message, locale);
    assert.equal(choices.length, 2);
    assert.ok(choices.every((choice) => !/€|recommended|aanbevolen|empfohlen/i.test(choice.label)));
  }
});

test('multiple linked objects preserve the owner-scoped ID in the reply', () => {
  const message = { state: { next_missing_input: 'strategy_id', setup_options: [{ id: 1, name: 'Other setup' }], strategy_options: [{ id: 7, name: 'BTC Base' }, { id: 12, name: 'BTC Swing' }] } };
  assert.deepEqual(draftQuestionChoices(message), [
    { label: 'BTC Base', reply: 'strategy 7' },
    { label: 'BTC Swing', reply: 'strategy 12' },
  ]);
});

test('other structured questions offer a small set of relevant choices', () => {
  for (const [field, expected] of [['risk_profile', 3], ['category', 3], ['execution_mode', 2]]) {
    const choices = draftQuestionChoices({ actionDraft: { missing_inputs: [field] } });
    assert.equal(choices.length, expected);
  }
});
