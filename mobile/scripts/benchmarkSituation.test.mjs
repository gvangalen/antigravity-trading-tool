import assert from 'node:assert/strict';
import { test } from 'node:test';

import { benchmarkSituationId } from '../src/services/benchmarkSituation.ts';

test('the mobile benchmark uses the same five inclusive bands as saved setup presets', () => {
  assert.equal(benchmarkSituationId(25), 'heavy_pressure');
  assert.equal(benchmarkSituationId(26), 'pressure');
  assert.equal(benchmarkSituationId(45), 'pressure');
  assert.equal(benchmarkSituationId(46), 'no_direction');
  assert.equal(benchmarkSituationId(60), 'no_direction');
  assert.equal(benchmarkSituationId(61), 'gaining_strength');
  assert.equal(benchmarkSituationId(75), 'gaining_strength');
  assert.equal(benchmarkSituationId(76), 'strong');
});

test('missing or invalid benchmark scores do not imply a market situation', () => {
  for (const value of [null, undefined, -1, 101, Number.NaN]) {
    assert.equal(benchmarkSituationId(value), null);
  }
});
