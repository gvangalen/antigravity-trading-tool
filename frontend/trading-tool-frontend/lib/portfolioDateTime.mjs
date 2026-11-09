// Intl does not allow dateStyle/timeStyle together with timeZoneName.
// Explicit fields keep the source time zone visible without crashing Portfolio.
export const PORTFOLIO_TIME_OPTIONS = Object.freeze({
  day: "numeric",
  month: "short",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
  timeZone: "Europe/Amsterdam",
  timeZoneName: "short",
});
