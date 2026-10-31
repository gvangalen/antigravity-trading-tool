export function scoreSourceSnapshot(report) {
  let value = report?.score_source_snapshot;
  // Period reports store their immutable Report 2.0 snapshot in meta_json;
  // daily reports have a dedicated column for the same contract.
  if (value == null && report?.meta_json != null) {
    try {
      const meta = typeof report.meta_json === 'string' ? JSON.parse(report.meta_json) : report.meta_json;
      value = meta?.score_source_snapshot;
    } catch {
      return null;
    }
  }
  if (value && typeof value === 'object' && !Array.isArray(value)) return value;
  if (typeof value !== 'string') return null;
  try {
    const parsed = JSON.parse(value);
    return parsed && typeof parsed === 'object' && !Array.isArray(parsed) ? parsed : null;
  } catch {
    return null;
  }
}

export function reportMarketLabel(item) {
  return item?.trading_pair || item?.pair || item?.symbol || '—';
}

export function parseUtcMoment(value) {
  if (value instanceof Date) return Number.isNaN(value.getTime()) ? null : value;
  if (typeof value !== 'string' || !value.trim()) return null;
  const raw = value.trim();
  const withZone = /(?:Z|[+-]\d{2}:?\d{2})$/i.test(raw) ? raw : `${raw}Z`;
  const parsed = new Date(withZone);
  return Number.isNaN(parsed.getTime()) ? null : parsed;
}

export function reportSnapshotMoment(report) {
  const snapshot = scoreSourceSnapshot(report);
  return parseUtcMoment(snapshot?.observed_at || report?.generated_at);
}
