export function paperPriceMessageKey({ isLive, symbol, reasonCode, at }) {
  if (isLive !== false || reasonCode !== "market_price_stale") return null;
  if (String(symbol || "").toUpperCase() !== "AAPL") return "paperPriceUnavailable";

  if (!at) return "paperPriceUnavailable";
  const date = new Date(at);
  if (!Number.isFinite(date.getTime())) return "paperPriceUnavailable";
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: "America/New_York", weekday: "short", hour: "2-digit",
    minute: "2-digit", hourCycle: "h23",
  }).formatToParts(date);
  const value = (type) => parts.find((part) => part.type === type)?.value;
  const weekday = value("weekday");
  const minutes = Number(value("hour")) * 60 + Number(value("minute"));
  return weekday === "Sat" || weekday === "Sun" || minutes < 9 * 60 + 30 || minutes >= 16 * 60
    ? "paperAaplMarketClosed" : "paperPriceUnavailable";
}
