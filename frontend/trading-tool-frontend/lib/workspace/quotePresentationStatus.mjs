const US_EQUITY_CLASSES = new Set(["stock", "stocks", "etf", "etfs"]);

function weekdayAt(date, timeZone) {
  try {
    return new Intl.DateTimeFormat("en-US", { weekday: "short", timeZone }).format(date);
  } catch {
    return null;
  }
}

export function quotePresentationStatus({ stale, assetClass, marketRegion, timeZone, sourceAt, now = new Date() }) {
  if (!stale) return "current";

  const source = new Date(sourceAt);
  const current = new Date(now);
  const ageMs = current.getTime() - source.getTime();
  if (
    !US_EQUITY_CLASSES.has(String(assetClass || "").toLowerCase())
    || String(marketRegion || "").toLowerCase() !== "us"
    || !timeZone
    || !Number.isFinite(ageMs)
    || ageMs < 0
    || ageMs > 72 * 60 * 60 * 1000
  ) return "stale";

  const currentDay = weekdayAt(current, timeZone);
  const sourceDay = weekdayAt(source, timeZone);
  return (currentDay === "Sat" || currentDay === "Sun") && sourceDay === "Fri"
    ? "closed_session"
    : "stale";
}
