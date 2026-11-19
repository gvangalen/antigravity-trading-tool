// Feed timestamps are UTC instants. The device chooses the user's display
// zone; a source with only a calendar date is rendered separately.
export function formatCoachFeedInstant(value: string | null | undefined, language: string): string {
  if (!value || !value.trim()) return '—';
  const raw = value.trim();
  const instant = new Date(/(?:Z|[+-]\d{2}:?\d{2})$/i.test(raw) ? raw : `${raw}Z`);
  if (Number.isNaN(instant.getTime())) return '—';
  return instant.toLocaleString(language, { timeZoneName: 'short' });
}
