const isDated = (value, now) => {
  if (!value) return false;
  const timestamp = new Date(value).getTime();
  return Number.isFinite(timestamp) && timestamp <= now.getTime() + 5 * 60_000;
};

const numberOrNull = (value) => {
  if (value === null || value === undefined || value === "" || typeof value === "boolean") return null;
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
};

export function marketContextFromEvidence({ quote, quoteStatus, technicalRows, technicalPeriod = "day", now = new Date() }) {
  const quoteChange = numberOrNull(quote?.change_24h);
  const quotePrice = numberOrNull(quote?.price);
  const hasQuote = ["current", "closed_session"].includes(quoteStatus)
    && quotePrice !== null && quotePrice > 0
    && quoteChange !== null && isDated(quote?.as_of, now);

  const maRow = technicalPeriod === "day" && Array.isArray(technicalRows)
    ? technicalRows.find((row) => String(row?.name || "").toLowerCase() === "ma_200")
    : null;
  const maRatio = numberOrNull(maRow?.raw?.value);
  const maSourceAt = maRow?.raw?.source_observed_at || maRow?.timestamp;
  const hasMa = maRatio !== null && maRatio > 0 && maRatio < 10
    && maRow?.raw?.freshness?.status === "available"
    && maRow?.raw?.freshness?.stale === false
    && isDated(maSourceAt, now);

  const ma = hasMa ? {
    position: maRatio >= 1 ? "above" : "below",
    ratio: maRatio,
    sourceAt: maSourceAt,
  } : null;
  const change = hasQuote ? {
    direction: quoteChange > 0 ? "up" : quoteChange < 0 ? "down" : "flat",
    percent: quoteChange,
    sourceAt: quote.as_of,
    closedSession: quoteStatus === "closed_session",
  } : null;

  return { ma, change, available: Boolean(ma || change) };
}
