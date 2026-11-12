import test from 'node:test';
import assert from 'node:assert/strict';
import { watchlistIntent, watchlistChoices, watchlistScopeChoices, replacementAfterConfirmedAdd } from '../lib/finnWatchlistConversation.mjs';

const btc = { symbol: 'BTC', display_name: 'Bitcoin', asset_class: 'crypto', start: 5, end: 8 };
const eth = { symbol: 'ETH', display_name: 'Ethereum', asset_class: 'crypto', start: 5, end: 8 };
const apple = { symbol: 'AAPL', display_name: 'Apple Inc.', asset_class: 'stock', start: 9, end: 14 };
const markets = [
  { pair: 'BTC/EUR', quote_currency: 'EUR', status: 'available' },
  { pair: 'BTC/USDT', quote_currency: 'USDT', status: 'available' },
];

function mentionsIn(text) {
  const entries = [
    { word: 'Apple', ...apple },
    { word: 'Bitcoin', ...btc },
    { word: 'Ethereum', ...eth },
    { word: 'BTC/EUR', ...btc, quote_currency: 'EUR' },
    { word: 'BTC/USDT', ...btc, quote_currency: 'USDT' },
  ];
  const mentions = [];
  for (const entry of entries) {
    for (const match of text.matchAll(new RegExp(entry.word.replace('/', '\\/'), 'gi'))) {
      mentions.push({ ...entry, start: match.index, end: match.index + entry.word.length });
    }
  }
  return mentions.sort((left, right) => left.start - right.start)
    .filter((mention, index, all) => !all.slice(0, index).some((other) => other.start === mention.start && other.end > mention.end));
}

test('bare crypto add offers clickable market choices from supplied market catalog', () => {
  for (const target of [btc, eth]) {
    const intent = watchlistIntent(`Voeg ${target.symbol} toe aan mijn watchlist`, [target]);
    assert.equal(intent.kind, 'add');
    const options = watchlistChoices(intent, [], markets.map((market) => ({
      ...market, pair: market.pair.replace('BTC', target.symbol),
    })));
    assert.deepEqual(options.choices.map((choice) => choice.action.target_quote_currency), ['EUR', 'USDT']);
  }
});

test('stock addition uses the same guidance without a crypto pair', () => {
  const intent = watchlistIntent('Voeg Apple toe aan mijn watchlist', [apple]);
  const options = watchlistChoices(intent, [], []);
  assert.equal(options.choices.length, 1);
  assert.equal(options.choices[0].action.target_symbol, 'AAPL');
  assert.equal(options.choices[0].action.target_quote_currency, null);
});

test('Apple to Bitcoin replacement keeps owner source and exact target pair', () => {
  const intent = watchlistIntent('Vervang Apple door BTC in mijn watchlist', [apple, btc], [
    { symbol: 'AAPL', market_id: null },
  ]);
  assert.equal(intent.kind, 'replace');
  const options = watchlistChoices(intent, [{ symbol: 'AAPL', market_id: null }], markets);
  assert.equal(options.choices.length, 2);
  assert.equal(options.choices[0].action.source_symbol, 'AAPL');
  assert.equal(options.choices[0].action.target_quote_currency, 'EUR');
});

test('natural in plaats van phrasing resolves direction without a ticker special case', () => {
  const text = 'Nee ik wil in plaats van Apple nu voortaan bitcoin volgen, voeg die toe aan de watchlist';
  const first = { ...apple, start: text.indexOf('Apple'), end: text.indexOf('Apple') + 5 };
  const second = { ...btc, start: text.indexOf('bitcoin'), end: text.indexOf('bitcoin') + 7 };
  const intent = watchlistIntent(text, [first, second], [{ symbol: 'AAPL', market_id: null }]);
  assert.equal(intent.kind, 'replace');
  assert.equal(intent.source.symbol, 'AAPL');
  assert.equal(intent.target.symbol, 'BTC');
});

test('repeated directed asset names resolve one safe replacement with clickable pairs', () => {
  const text = 'Ik wil in plaats van Apple voortaan Bitcoin volgen. Vervang Apple in mijn watchlist door Bitcoin.';
  const intent = watchlistIntent(text, mentionsIn(text), [{ symbol: 'AAPL', market_id: null }]);
  assert.equal(intent.kind, 'replace');
  assert.equal(intent.source.symbol, 'AAPL');
  assert.equal(intent.target.symbol, 'BTC');
  assert.deepEqual(watchlistChoices(intent, [{ symbol: 'AAPL', market_id: null }], markets).choices
    .map((choice) => choice.action.target_quote_currency), ['EUR', 'USDT']);
});

test('a previous unrelated pair cannot determine the replacement quote', () => {
  const text = 'BTC/EUR staat al in mijn watchlist. Vervang Apple door Bitcoin.';
  const intent = watchlistIntent(text, mentionsIn(text), [{ symbol: 'AAPL', market_id: null }]);
  assert.equal(intent.kind, 'replace');
  assert.equal(intent.target.quote_currency, undefined);
  assert.equal(watchlistChoices(intent, [{ symbol: 'AAPL', market_id: null }], markets).choices.length, 2);
});

test('negated, conflicting and self-directed replacements do not offer a proposal', () => {
  for (const text of [
    'Vervang Apple niet door BTC/EUR in mijn watchlist.',
    'Vervang Apple door Bitcoin en Bitcoin door Apple in mijn watchlist.',
    'Vervang Apple door Apple en BTC/EUR in mijn watchlist.',
    'Vervang Apple door BTC/EUR. Vervang Bitcoin door Apple in mijn watchlist.',
    'Vervang Apple door Bitcoin in mijn watchlist. Verwijder Bitcoin uit mijn watchlist.',
    'Vervang Apple door Bitcoin in mijn watchlist. Voeg BTC/EUR toe aan mijn watchlist.',
  ]) {
    const intent = watchlistIntent(text, mentionsIn(text), [{ symbol: 'AAPL', market_id: null }]);
    assert.notEqual(intent?.kind, 'replace', text);
    assert.deepEqual(watchlistChoices(intent, [{ symbol: 'AAPL', market_id: null }], markets)?.choices, []);
  }
});

test('conflicting instructions explain the conflict and a negated action is acknowledged', () => {
  const conflict = 'Vervang Apple door Bitcoin in mijn watchlist. Voeg BTC/EUR toe aan mijn watchlist.';
  const conflicting = watchlistChoices(watchlistIntent(conflict, mentionsIn(conflict), [
    { symbol: 'AAPL', market_id: null },
  ]), [{ symbol: 'AAPL', market_id: null }], markets);
  assert.match(conflicting.question, /Welke wijziging wil je eerst/i);
  assert.deepEqual(conflicting.choices, []);

  const negated = 'Vervang Apple niet door BTC/EUR in mijn watchlist.';
  const acknowledged = watchlistChoices(watchlistIntent(negated, mentionsIn(negated), [
    { symbol: 'AAPL', market_id: null },
  ]), [{ symbol: 'AAPL', market_id: null }], markets);
  assert.match(acknowledged.question, /niet uit/i);
  assert.deepEqual(acknowledged.choices, []);
});

test('stop following one asset and follow another keeps replacement direction', () => {
  const text = 'Apple niet meer volgen; volg Bitcoin';
  const source = { ...apple, start: text.indexOf('Apple'), end: text.indexOf('Apple') + 5 };
  const target = { ...btc, start: text.indexOf('Bitcoin'), end: text.indexOf('Bitcoin') + 7 };
  const intent = watchlistIntent(text, [source, target], [{ symbol: 'AAPL', market_id: null }]);
  assert.equal(intent.kind, 'replace');
  assert.equal(intent.source.symbol, 'AAPL');
  assert.equal(intent.target.symbol, 'BTC');
});

test('unclear asset change asks what surface the user meant', () => {
  const intent = watchlistIntent('Mijn aandeel aanpassen in bitcoin', [btc]);
  assert.equal(intent.kind, 'clarify_scope');
  assert.deepEqual(watchlistChoices(intent, []).choices.map((choice) => choice.label), ['Watchlist', 'Portfolio']);
  assert.equal(watchlistChoices(intent, []).choices[0].action.kind, 'clarify_watchlist_scope');
  const next = watchlistScopeChoices(btc, [{ symbol: 'AAPL', market_id: null }], markets);
  assert.deepEqual(next.choices.map((choice) => choice.action.kind), ['add', 'add', 'replace', 'replace']);
  assert.equal(next.choices[2].action.source_symbol, 'AAPL');
});

test('two asset actions without a watchlist scope ask before changing state', () => {
  const text = 'Haal Apple weg en voeg BTC/EUR toe';
  const source = { ...apple, start: text.indexOf('Apple'), end: text.indexOf('Apple') + 5 };
  const target = { ...btc, start: text.indexOf('BTC/EUR'), end: text.indexOf('BTC/EUR') + 7, quote_currency: 'EUR' };
  const intent = watchlistIntent(text, [source, target]);
  assert.equal(intent.kind, 'clarify_scope');
  assert.equal(intent.target.symbol, 'BTC');
  assert.equal(watchlistChoices(intent, []).choices[0].action.kind, 'clarify_watchlist_scope');
});

test('ambiguous replacement does not select an asset', () => {
  const intent = watchlistIntent('Vervang iets in mijn watchlist', []);
  assert.equal(intent.kind, 'clarify_assets');
  assert.equal(watchlistChoices(intent, []).choices.length, 0);
});

test('replacement advances only after the exact destination was confirmed', () => {
  const pending = {
    kind: 'replace', source_symbol: 'AAPL', target_symbol: 'BTC', target_quote_currency: 'EUR',
  };
  assert.equal(replacementAfterConfirmedAdd(pending, 'watchlist_add', {
    asset: 'BTC', quote_currency: 'USDT',
  }), null);
  assert.equal(replacementAfterConfirmedAdd(pending, 'watchlist_remove', {
    asset: 'BTC', quote_currency: 'EUR',
  }), null);
  const next = replacementAfterConfirmedAdd(pending, 'watchlist_add', {
    asset: 'BTC', quote_currency: 'EUR',
  });
  assert.equal(next.action.kind, 'remove');
  assert.equal(next.action.source_symbol, 'AAPL');
});
