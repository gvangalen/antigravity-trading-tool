import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { test } from 'node:test';
import { formatUtcSourceDate, formatUtcTimestamp } from '../lib/time/formatUtcTimestamp.mjs';

const moduleUrl = new URL('../lib/time/formatUtcTimestamp.mjs', import.meta.url).href;

function renderInZone(zone, value) {
  const code = `import { formatUtcTimestamp } from ${JSON.stringify(moduleUrl)};
    process.stdout.write(formatUtcTimestamp(${JSON.stringify(value)}, 'en-GB'));`;
  const result = spawnSync(process.execPath, ['--input-type=module', '-e', code], {
    encoding: 'utf8',
    env: { ...process.env, TZ: zone },
  });
  assert.equal(result.status, 0, result.stderr);
  return result.stdout;
}

test('Analyse shows one UTC source moment in different browser zones', () => {
  const source = '2026-11-08T14:30:00Z';
  const amsterdam = renderInZone('Europe/Amsterdam', source);
  const newYork = renderInZone('America/New_York', source);
  assert.equal(amsterdam, newYork);
  assert.match(amsterdam, /14:30 UTC$/);
  assert.equal(renderInZone('Asia/Tokyo', '2026-11-08T14:30:00'), amsterdam);
});

test('invalid source moments remain unknown', () => {
  assert.equal(formatUtcTimestamp('invalid', 'nl-NL'), '—');
  assert.equal(formatUtcTimestamp(null, 'nl-NL'), '—');
  assert.equal(formatUtcSourceDate('invalid', 'nl-NL'), null);
});

test('short source date follows the UTC day across an offset boundary', () => {
  const source = '2026-11-08T00:30:00+02:00';
  assert.equal(formatUtcSourceDate(source, 'en-GB'), '7 November 2026');
  assert.match(formatUtcTimestamp(source, 'en-GB'), /^7 Nov 2026, 22:30 UTC$/);
});
