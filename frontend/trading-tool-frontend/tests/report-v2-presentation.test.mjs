import test from 'node:test';
import assert from 'node:assert/strict';

import nl from '../dictionaries/nl.json' with { type: 'json' };
import { getReportSignature, isGeneratedReportReady } from '../lib/report/reportState.js';
import {
  reportV2AnalysisParagraphs,
  reportV2Change,
  reportV2IndicatorName,
  reportV2Locale,
  reportV2PeriodLabel,
  reportV2PeriodState,
} from '../lib/report/reportV2Presentation.mjs';

test('worker success waits for the changed saved snapshot, even when created_at is unchanged', () => {
  const saved = { report_date: '2026-10-31', created_at: '2026-10-31T18:00:00Z' };
  assert.equal(isGeneratedReportReady(saved, saved.created_at, saved.created_at, false), false);
  assert.equal(isGeneratedReportReady(saved, saved.created_at, saved.created_at, true), false);
  assert.equal(isGeneratedReportReady(saved, 'new-snapshot', saved.created_at, true), true);
  assert.equal(isGeneratedReportReady(saved, 'new-snapshot', saved.created_at, false), false);
  assert.equal(isGeneratedReportReady({ _status: 'pending' }, 'same', 'same', true), false);
});

test('period report identity follows the frozen facts, not the upsert timestamp', () => {
  const old = { created_at: 'same', meta_json: { score_source_snapshot: {
    report_v2: { version: 2, period: 'weekly' }, observed_at: '2026-11-01T10:00:00Z',
  } } };
  const next = { created_at: 'same', meta_json: { score_source_snapshot: {
    report_v2: { version: 2, period: 'weekly' }, observed_at: '2026-11-01T10:01:00Z',
  } } };
  assert.notEqual(getReportSignature(old), getReportSignature(next));
  assert.equal(isGeneratedReportReady(old, getReportSignature(old), getReportSignature(old), true), false);
  assert.equal(isGeneratedReportReady(next, getReportSignature(next), getReportSignature(old), true, 'weekly'), true);
  assert.equal(isGeneratedReportReady(next, getReportSignature(next), getReportSignature(old), true, 'daily'), false);
});

test('PDF labels follow the saved prose language, not the print browser language', () => {
  const report = { score_source_snapshot: JSON.stringify({ content_locale: 'nl' }) };
  assert.equal(reportV2Locale(report, 'en'), 'nl');
  assert.equal(reportV2Locale({ meta_json: { score_source_snapshot: { content_locale: 'de' } } }, 'en'), 'de');
  assert.equal(reportV2Locale({}, 'de'), 'de');
});

test('period report headers show the saved range; daily reports keep their date', () => {
  const report = { report_date: '2026-10-31', meta_json: { score_source_snapshot: {
    content_locale: 'nl', report_v2: { period: 'weekly', period_start: '2026-10-26', period_end: '2026-10-31' },
  } } };
  assert.match(reportV2PeriodLabel(report, 'en'), /Oct 26, 2026 – Oct 31, 2026/);
  assert.match(reportV2PeriodLabel(report, 'de'), /26\. Okt\. 2026 – 31\. Okt\. 2026/);
  assert.match(reportV2PeriodLabel(report, 'nl'), /26 okt 2026 – 31 okt 2026/);
  assert.equal(reportV2PeriodLabel({ report_date: '2026-10-31' }, 'nl'), '2026-10-31');
  report.meta_json.score_source_snapshot.report_v2.comparison = { period_complete: false };
  assert.equal(reportV2PeriodState(report, 'en'), 'Week in progress');
  assert.equal(reportV2PeriodState(report, 'de'), 'Laufende Woche');
  assert.equal(reportV2PeriodState(report, 'nl'), 'Lopende week');
  report.meta_json.score_source_snapshot.report_v2.comparison.period_complete = true;
  assert.equal(reportV2PeriodState(report, 'en'), null);
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
  assert.equal(reportV2Change({ asset: 'BTC/EUR', fact: 'indicator_score', indicator: 'ma_200',
    before: 40, after: 65, value_before: 79000, value_after: 81000, unit: 'EUR' }, {
    indicatorNames: names, unavailable: 'niet beschikbaar', locale: 'nl',
  }), 'BTC/EUR · Voortschrijdend gemiddelde (200 dagen): 40/100 → 65/100 (79.000 → 81.000 EUR)');
});
