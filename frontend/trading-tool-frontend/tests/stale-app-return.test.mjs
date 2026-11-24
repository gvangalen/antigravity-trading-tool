import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';
import { runInNewContext } from 'node:vm';

test('a tab returning after a deploy reloads its HTML route before navigation', async () => {
  const rootLayout = await readFile(new URL('../app/layout.jsx', import.meta.url), 'utf8');
  const inlineScript = rootLayout.match(/const script = `([\s\S]*?)`;/)?.[1]
    .replace('${JSON.stringify(STALE_APP_RECOVERY_VERSION)}', '"test-build"');
  assert.ok(inlineScript);

  const listeners = {};
  const replacements = [];
  const storage = new Map([['tradamind_app_cache_version', 'test-build']]);
  let reads = 0;
  const document = {
    visibilityState: 'hidden',
    addEventListener: (name, handler) => { listeners[name] = handler; },
  };
  runInNewContext(inlineScript, {
    Date, Promise, URL, document,
    fetch: async () => ({ ok: true, json: async () => ({ commit_sha: ++reads === 1 ? 'old-sha' : 'new-sha' }) }),
    window: {
      location: { href: 'https://tradamind.com/portfolio', replace: (url) => replacements.push(url) },
      localStorage: { getItem: (key) => storage.get(key), setItem: (key, value) => storage.set(key, value) },
      sessionStorage: { getItem: (key) => storage.get(key), setItem: (key, value) => storage.set(key, value) },
      addEventListener: (name, handler) => { listeners[name] = handler; },
    },
    navigator: {},
  });
  await new Promise((resolve) => setImmediate(resolve));
  listeners.visibilitychange();
  await new Promise((resolve) => setImmediate(resolve));
  assert.equal(replacements.length, 0);

  document.visibilityState = 'visible';
  listeners.visibilitychange();
  await new Promise((resolve) => setImmediate(resolve));
  assert.equal(replacements.length, 1);
  assert.match(replacements[0], /__tm_recover=test-build-version-/);
});
