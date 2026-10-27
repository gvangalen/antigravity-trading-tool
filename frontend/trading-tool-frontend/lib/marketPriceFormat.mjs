export function formatMarketPrice(value, locale, quoteCurrency) {
  const price = Number(value);
  if (value == null || !Number.isFinite(price)) return "---";
  const quote = String(quoteCurrency || "").toUpperCase();
  if (quote === "USDT") {
    return `${new Intl.NumberFormat(locale, { maximumFractionDigits: 2 }).format(price)} USDT`;
  }
  return new Intl.NumberFormat(locale, {
    style: "currency", currency: quote || "USD",
  }).format(price);
}
