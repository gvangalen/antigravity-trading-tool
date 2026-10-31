import { scoreSourceSnapshot } from './reportSourceSnapshot.mjs';

export function reportV2Locale(report, browserLocale) {
  const snapshot = scoreSourceSnapshot(report);
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

export function reportV2AnalysisParagraphs(value, locale = 'nl') {
  const text = String(value || '').trim();
  if (!text) return [];
  return text.split(/\n\s*\n/).flatMap((paragraph) => {
    const clean = paragraph.trim();
    if (clean.length <= 320 || !Intl.Segmenter) return [clean];
    const sentences = [...new Intl.Segmenter(locale, { granularity: 'sentence' }).segment(clean)]
      .map(({ segment }) => segment.trim()).filter(Boolean);
    if (sentences.length < 3) return [clean];
    const blocks = [];
    for (let index = 0; index < sentences.length; index += 2) {
      blocks.push(sentences.slice(index, index + 2).join(' '));
    }
    return blocks;
  });
}
