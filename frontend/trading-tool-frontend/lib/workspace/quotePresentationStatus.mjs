const US_EQUITY_CLASSES = new Set(["stock", "stocks", "etf", "etfs", "index"]);

function weekdayAt(date, timeZone) {
  try {
    return new Intl.DateTimeFormat("en-US", { weekday: "short", timeZone }).format(date);
  } catch {
    return null;
  }
}

function hourAndMinuteAt(date, timeZone) {
  try {
    const parts = new Intl.DateTimeFormat("en-US", {
      hour: "2-digit", minute: "2-digit", hourCycle: "h23", timeZone,
    }).formatToParts(date);
    return Number(parts.find((part) => part.type === "hour")?.value) * 60
      + Number(parts.find((part) => part.type === "minute")?.value);
  } catch {
    return null;
  }
}

export function quotePresentationStatus({ stale, assetClass, marketRegion, timeZone, sourceAt, now = new Date() }) {
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
  ) return stale ? "stale" : "current";

  const currentDay = weekdayAt(current, timeZone);
  const sourceDay = weekdayAt(source, timeZone);
  const currentMinute = hourAndMinuteAt(current, timeZone);
  const sourceMinute = hourAndMinuteAt(source, timeZone);
  const beforeMondayOpen = currentDay === "Mon" && Number.isFinite(currentMinute)
    && currentMinute < 9 * 60 + 30;
  const nearFridayClose = sourceDay === "Fri" && Number.isFinite(sourceMinute)
    && sourceMinute >= 15 * 60 + 30;
  return ((currentDay === "Sat" || currentDay === "Sun") || beforeMondayOpen) && nearFridayClose
    ? "closed_session"
    : stale ? "stale" : "current";
}
