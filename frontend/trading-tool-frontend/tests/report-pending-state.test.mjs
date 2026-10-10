import test from 'node:test';
import assert from 'node:assert/strict';

import { isPendingReport, isReadyReport } from '../lib/report/reportState.js';

test('the first-report placeholder starts generation and cannot finish polling', () => {
  const pending = { _status: 'pending_first_report', headline: 'Being prepared' };
  assert.equal(isPendingReport(pending), true);
  assert.equal(isReadyReport(pending), false);
  assert.equal(isReadyReport({ _status: 'pending' }), false);
  assert.equal(isReadyReport({ report_date: '2026-10-10', executive_summary: 'Done' }), true);
});
