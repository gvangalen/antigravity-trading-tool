import test from 'node:test';
import assert from 'node:assert/strict';

import nl from '../dictionaries/nl.json' with { type: 'json' };
import {
  reportV2Change,
  reportV2IndicatorName,
  reportV2Locale,
} from '../lib/report/reportV2Presentation.mjs';

test('PDF labels follow the saved prose language, not the print browser language', () => {
  const report = { score_source_snapshot: JSON.stringify({ content_locale: 'nl' }) };
  assert.equal(reportV2Locale(report, 'en'), 'nl');
  assert.equal(reportV2Locale({}, 'de'), 'de');
});

test('report evidence uses translated indicator names and explicit score changes', () => {
  const names = nl.traderProfile.analysisOnboardingStep.indicatorNames;
  assert.equal(reportV2IndicatorName('ma_200', names), 'Voortschrijdend gemiddelde (200 dagen)');
  assert.equal(reportV2Change({ asset: 'BTC/EUR', fact: 'market_score', before: 50, after: 40 }, {
    market_score: 'Markt', unavailable: 'niet beschikbaar', available: 'beschikbaar',
  }), 'BTC/EUR · Markt: 50/100 → 40/100');
});
