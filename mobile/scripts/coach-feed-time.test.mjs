import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import test from 'node:test';

import { formatCoachFeedInstant } from '../src/services/coachFeedTime.ts';

const moduleUrl = new URL('../src/services/coachFeedTime.ts', import.meta.url).href;

function renderInZone(zone) {
  const code = `import { formatCoachFeedInstant } from ${JSON.stringify(moduleUrl)};
    process.stdout.write(formatCoachFeedInstant('2026-11-19T00:30:00Z', 'en-GB'));`;
  const result = spawnSync(process.execPath, ['--experimental-strip-types', '--input-type=module', '-e', code], {
    encoding: 'utf8', env: { ...process.env, TZ: zone },
  });
  assert.equal(result.status, 0, result.stderr);
  return result.stdout;
}

test('mobile FINN feed follows device time zone for UTC source moments', () => {
  assert.match(renderInZone('Europe/Amsterdam'), /19\/11\/2026, 0?1:30.*(?:CET|GMT\+1)$/);
  assert.match(renderInZone('America/New_York'), /18\/11\/2026, 19:30.*(?:EST|GMT-5)$/);
  assert.match(renderInZone('Asia/Tokyo'), /19\/11\/2026, 0?9:30.*(?:JST|GMT\+9)$/);
  assert.equal(formatCoachFeedInstant('invalid', 'en-GB'), '—');
});
