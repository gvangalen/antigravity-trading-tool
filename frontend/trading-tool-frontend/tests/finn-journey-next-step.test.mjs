import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { affirmativeJourneyReply, journeyNextStepAfterConfirmedWrite } from '../lib/finnJourneyNextStep.mjs';

test('confirmed setup asks about a strategy for the exact saved pair', () => {
  const guidance = journeyNextStepAfterConfirmedWrite('create_setup', {
    step: 'strategy', setup_id: 42, pair: 'BTC/USDT',
  });
  assert.match(guidance.question, /BTC\/USDT.*strategie/);
  assert.match(guidance.choices[0].reply, /ID 42/);
  assert.match(guidance.choices[0].reply, /Maak geen nieuwe setup/);
});

test('confirmed strategy offers only a separate Paper proposal', () => {
  const guidance = journeyNextStepAfterConfirmedWrite('create_strategy', {
    step: 'paper', setup_id: 42, strategy_id: 91, pair: 'BTC/EUR',
  });
  assert.match(guidance.question, /Paper-bot/);
  assert.match(guidance.choices[0].reply, /ID 91/);
  assert.match(guidance.choices[0].reply, /Activeer niets en plaats geen order/);
  assert.equal(journeyNextStepAfterConfirmedWrite('create_setup', { step: 'paper', setup_id: 42, pair: 'BTC/EUR' }), null);
});

test('a combined task continuation does not display a competing question', () => {
  const source = readFileSync(new URL('../components/ui/AIAssistant.jsx', import.meta.url), 'utf8');
  assert.match(source, /execution\.task_continuation \? null\s*: journeyNextStepAfterConfirmedWrite/);
  assert.match(source, /journeyNextStep\) next\.push/);
  assert.equal(journeyNextStepAfterConfirmedWrite('update_setup', { step: 'strategy', setup_id: 42, pair: 'BTC/EUR' }), null);
});

test('a short yes resumes only the latest verified journey question', () => {
  const guidance = journeyNextStepAfterConfirmedWrite('create_setup', {
    step: 'strategy', setup_id: 42, pair: 'BTC/USDT',
  });
  const pending = [{ role: 'assistant', journeyGuidance: true, watchlistGuidance: guidance }];
  assert.equal(affirmativeJourneyReply('ja', pending), guidance.choices[0].reply);
  assert.equal(affirmativeJourneyReply('ja', [...pending, { role: 'user', text: 'anders' }]), null);
  assert.equal(affirmativeJourneyReply('ja', [{ role: 'assistant', watchlistGuidance: guidance }]), null);
  assert.equal(affirmativeJourneyReply('nee', pending), null);
});
