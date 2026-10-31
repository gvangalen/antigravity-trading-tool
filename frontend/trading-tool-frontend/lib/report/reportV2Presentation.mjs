export function reportV2Locale(report, browserLocale) {
  const saved = report?.score_source_snapshot;
  let snapshot = saved;
  if (typeof saved === 'string') {
    try { snapshot = JSON.parse(saved); } catch { snapshot = null; }
  }
  // The report prose is a saved snapshot. Its labels must use that same language
  // in the web view and in a fresh browser used to print the PDF.
  const candidate = snapshot?.content_locale || browserLocale;
  const language = String(candidate || browserLocale || 'nl').slice(0, 2).toLowerCase();
  return ['nl', 'en', 'de'].includes(language) ? language : 'nl';
}

export function reportV2IndicatorName(name, labels = {}) {
  const key = String(name || '').trim().toLowerCase();
  return labels[key] || name;
}

export function reportV2Change(change, labels) {
  const fact = change?.fact;
  const title = labels?.[fact] || fact;
  if (!title) return null;
  const value = (item) => {
    if (fact === 'benchmark_availability') return item ? labels.available : labels.unavailable;
    return typeof item === 'number' && Number.isFinite(item) ? `${item}/100` : labels.unavailable;
  };
  return `${change.asset} · ${title}: ${value(change.before)} → ${value(change.after)}`;
}
