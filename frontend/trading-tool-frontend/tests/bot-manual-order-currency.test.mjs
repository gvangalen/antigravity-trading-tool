import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import { runInNewContext } from 'node:vm';

test('Paper order confirmation sends the previewed EUR price unit to the API', async () => {
  const source = readFileSync(new URL('../lib/api/botApi.js', import.meta.url), 'utf8')
    .replace(/^import .*;\s*$/gm, '')
    .replace(/\bexport (const|function)\b/g, '$1');
  let sent;
  const context = {
    fetchAuth: async (url, options) => {
      sent = { url, body: JSON.parse(options.body) };
      return { ok: true };
    },
    URLSearchParams,
  };
  runInNewContext(`${source}\nglobalThis.createOrderUnderTest = createManualOrder;`, context);

  await context.createOrderUnderTest({
    bot_id: 7, symbol: 'ETH', side: 'buy', quantity: 0.1,
    price: 100, price_currency: 'EUR', value_eur: 10,
    paper_preview_token: 'server-bound-preview',
  });
  assert.equal(sent.url, '/api/orders/manual');
  assert.equal(sent.body.price, 100);
  assert.equal(sent.body.price_currency, 'EUR');
  assert.equal(sent.body.paper_preview_token, 'server-bound-preview');
});

test('Paper order preview forwards the reference used for its eventual confirmation', async () => {
  const source = readFileSync(new URL('../lib/api/botApi.js', import.meta.url), 'utf8')
    .replace(/^import .*;\s*$/gm, '')
    .replace(/\bexport (const|function)\b/g, '$1');
  let sent;
  const context = {
    fetchAuth: async (url, options) => {
      sent = { url, body: JSON.parse(options.body) };
      return { ok: true };
    },
    URLSearchParams,
  };
  runInNewContext(`${source}\nglobalThis.previewUnderTest = previewManualOrder;`, context);

  await context.previewUnderTest({
    bot_id: 7, symbol: 'ETH', side: 'buy', quantity: 0.1,
    price: 100, price_currency: 'EUR', value_eur: 10,
    idempotency_key: 'qa-paper-order-unique-123',
  });
  assert.equal(sent.url, '/api/orders/preview');
  assert.equal(sent.body.idempotency_key, 'qa-paper-order-unique-123');
});
