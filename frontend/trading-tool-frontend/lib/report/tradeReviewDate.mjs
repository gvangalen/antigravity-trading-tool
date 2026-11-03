export function formatTradeReviewDate(value, locale) {
  // Older trade-review timestamps without an offset were stored in UTC.
  const instant = typeof value === 'string' && /^\d{4}-\d\d-\d\dT\d\d:\d\d/.test(value)
    && !/(?:Z|[+-]\d\d:\d\d)$/.test(value) ? `${value}Z` : value;
  const date = new Date(instant);
  if (Number.isNaN(date.getTime())) return '';
  return new Intl.DateTimeFormat(locale, {
    day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit', timeZone: 'Europe/Amsterdam', timeZoneName: 'short',
  }).format(date);
}
