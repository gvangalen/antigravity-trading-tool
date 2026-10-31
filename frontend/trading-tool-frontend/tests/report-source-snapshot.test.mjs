import test from 'node:test';
import assert from 'node:assert/strict';

import {
  parseUtcMoment,
  reportMarketLabel,
  reportSnapshotMoment,
  scoreSourceSnapshot,
} from '../lib/report/reportSourceSnapshot.mjs';

test('report snapshot keeps the source capture time distinct from report creation', () => {
  const report = {
    generated_at: '2026-10-10T05:40:00',
    score_source_snapshot: JSON.stringify({
      observed_at: '2026-10-10T05:31:00+00:00',
      assets: [{ symbol: 'ETH', component_source_observed_at: {
        market: { Price: '2026-10-10T05:30:00+00:00' },
      } }],
    }),
  };

  assert.equal(reportSnapshotMoment(report)?.toISOString(), '2026-10-10T05:31:00.000Z');
  assert.equal(scoreSourceSnapshot(report)?.assets[0].component_source_observed_at.market.Price, '2026-10-10T05:30:00+00:00');
});

test('pair-scoped report rows and current bots show the verified pair', () => {
  assert.equal(reportMarketLabel({ symbol: 'BTC', pair: 'BTC/EUR' }), 'BTC/EUR');
  assert.equal(reportMarketLabel({ symbol: 'BTC', trading_pair: 'BTC/USDT' }), 'BTC/USDT');
  assert.equal(reportMarketLabel({ symbol: 'AAPL', pair: null }), 'AAPL');
});

test('legacy reports have no invented source snapshot and naive database times are UTC', () => {
  assert.equal(scoreSourceSnapshot({ generated_at: '2026-10-10T03:38:00' }), null);
  assert.equal(reportSnapshotMoment({ generated_at: '2026-10-10T03:38:00' })?.toISOString(), '2026-10-10T03:38:00.000Z');
  assert.equal(parseUtcMoment('invalid'), null);
});

test('period reports read the frozen Report 2.0 evidence from meta_json', () => {
  const report = { meta_json: JSON.stringify({ score_source_snapshot: {
    content_locale: 'nl', report_v2: { version: 2, period: 'monthly' }, assets: [],
  } }) };
  assert.equal(scoreSourceSnapshot(report)?.report_v2.period, 'monthly');
});
