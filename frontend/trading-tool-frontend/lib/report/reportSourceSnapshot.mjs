export function scoreSourceSnapshot(report) {
  const value = report?.score_source_snapshot;
  if (value && typeof value === 'object' && !Array.isArray(value)) return value;
  if (typeof value !== 'string') return null;
  try {
    const parsed = JSON.parse(value);
    return parsed && typeof parsed === 'object' && !Array.isArray(parsed) ? parsed : null;
  } catch {
    return null;
  }
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
