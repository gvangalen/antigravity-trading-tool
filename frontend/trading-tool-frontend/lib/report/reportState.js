import { scoreSourceSnapshot } from './reportSourceSnapshot.mjs';

export function getReportSignature(report) {
  if (!report) return '';
  const snapshot = scoreSourceSnapshot(report);
  if (snapshot?.report_v2?.version === 2) {
    // A regenerated report may use the same facts and prose. The persisted
    // generation moment still changes when the worker saves the new report.
    return JSON.stringify({ generated_at: report.generated_at || null, snapshot });
  }
  return report.generated_at || report.updated_at || report.created_at || JSON.stringify(report);
}

export function isPendingReport(report) {
  return report?._status === 'pending_first_report' || report?._status === 'pending';
}

export function isReadyReport(report) {
  return Boolean(report) && !isPendingReport(report);
}

export function isGeneratedReportReady(report, currentSignature, baselineSignature, taskSucceeded, expectedPeriod = null) {
  // A completed worker task can be visible before the updated report row is.
  // Never render the previously saved snapshot as the newly generated report.
  const savedPeriod = scoreSourceSnapshot(report)?.report_v2?.period;
  return isReadyReport(report) && (!expectedPeriod || savedPeriod === expectedPeriod) && Boolean(currentSignature) &&
    Boolean(taskSucceeded) && currentSignature !== baselineSignature;
}
