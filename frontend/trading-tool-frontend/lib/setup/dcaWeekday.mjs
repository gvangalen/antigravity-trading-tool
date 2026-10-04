const WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"];

// SetupService stores ISO weekday numbers as text; the editor selects names.
export function normalizeDcaWeekday(value) {
  if (value == null || value === "") return null;
  const raw = String(value).trim().toLowerCase();
  if (WEEKDAYS.includes(raw)) return raw;
  if (/^[1-7]$/.test(raw)) return WEEKDAYS[Number(raw) - 1];
  return "";
}
