import { parseUtcMoment } from '../report/reportSourceSnapshot.mjs';

export function formatUtcTimestamp(value, locale) {
  const moment = parseUtcMoment(value);
  if (!moment) return '—';
  const dateTime = new Intl.DateTimeFormat(locale || 'en-US', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    timeZone: 'UTC',
  }).format(moment);
  return `${dateTime} UTC`;
}

export function formatUtcSourceDate(value, locale) {
  const moment = parseUtcMoment(value);
  if (!moment) return null;
  return new Intl.DateTimeFormat(locale || 'en-US', {
    day: 'numeric',
    month: 'long',
    year: 'numeric',
    timeZone: 'UTC',
  }).format(moment);
}
