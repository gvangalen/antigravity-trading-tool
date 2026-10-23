import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import { runInNewContext } from 'node:vm';

test('editing a trade strategy sends the confirmed quote currency', async () => {
  const source = readFileSync(new URL('../lib/api/strategy.js', import.meta.url), 'utf8')
    .replace(/^import .*;\s*$/gm, '')
    .replace(/\bexport (const|function)\b/g, '$1');
  let sent;
  const context = {
    fetchAuth: async (url, options) => {
      sent = { url, method: options.method, body: JSON.parse(options.body) };
      return { ok: true };
    },
  };
  runInNewContext(`${source}\nglobalThis.updateUnderTest = updateStrategy;`, context);

  await context.updateUnderTest(183, {
    entry: 347.14,
    stop_loss: 342,
    targets: [357.42],
    price_currency: 'USD',
    setup_id: 999,
  });

  assert.equal(sent.url, '/api/strategies/183');
  assert.equal(sent.method, 'PUT');
  assert.equal(sent.body.price_currency, 'USD');
  assert.equal(sent.body.setup_id, undefined);
});
