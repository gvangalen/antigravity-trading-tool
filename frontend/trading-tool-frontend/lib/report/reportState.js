export function isPendingReport(report) {
  return report?._status === 'pending_first_report' || report?._status === 'pending';
}

export function isReadyReport(report) {
  return Boolean(report) && !isPendingReport(report);
}
