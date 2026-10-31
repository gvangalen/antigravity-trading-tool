import test from 'node:test';
import assert from 'node:assert/strict';

import nl from '../dictionaries/nl.json' with { type: 'json' };
import {
  reportV2AnalysisParagraphs,
  reportV2Change,
  reportV2IndicatorName,
  reportV2Locale,
} from '../lib/report/reportV2Presentation.mjs';

test('PDF labels follow the saved prose language, not the print browser language', () => {
  const report = { score_source_snapshot: JSON.stringify({ content_locale: 'nl' }) };
  assert.equal(reportV2Locale(report, 'en'), 'nl');
  assert.equal(reportV2Locale({}, 'de'), 'de');
});

test('long analysis prose becomes readable paragraphs without changing its words', () => {
  const prose = 'BTC heeft een benchmarkscore van 60. De markt- en macroscore zijn beschikbaar. '
    + 'De opgeslagen BTC-voorwaarde is niet bereikt. AAPL heeft geen complete score. '
    + 'De laatste beurskoers is van de vorige sessie. ETH heeft geen gekozen indicatoren.';
  const paragraphs = reportV2AnalysisParagraphs(prose, 'nl');
  assert.equal(paragraphs.length, 1); // Short prose needs no artificial layout.
  const long = `${prose} ${prose}`;
  const blocks = reportV2AnalysisParagraphs(long, 'nl');
  assert.ok(blocks.length > 1);
  assert.equal(blocks.join(' '), long);
  assert.deepEqual(reportV2AnalysisParagraphs('BTC: score 60.\n\nAAPL: geen score.', 'nl'),
    ['BTC: score 60.', 'AAPL: geen score.']);
});

test('report evidence uses translated indicator names and explicit score changes', () => {
  const names = nl.traderProfile.analysisOnboardingStep.indicatorNames;
  assert.equal(reportV2IndicatorName('ma_200', names), 'Voortschrijdend gemiddelde (200 dagen)');
  assert.equal(reportV2Change({ asset: 'BTC/EUR', fact: 'market_score', before: 50, after: 40 }, {
    market_score: 'Markt', unavailable: 'niet beschikbaar', available: 'beschikbaar',
  }), 'BTC/EUR · Markt: 50/100 → 40/100');
});
