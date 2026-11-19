const QUOTES = ["USDT", "EUR", "USD"];
const KNOWN_CRYPTO = new Set(["ADA", "AVAX", "BTC", "DOGE", "DOT", "ETH", "LINK", "LTC", "SOL", "XRP"]);

export function marketDisplayQuote(symbol, { quoteCurrency, tradingviewSymbol } = {}) {
  const base = String(symbol || "").trim().toUpperCase();
  const explicit = String(quoteCurrency || "").trim().toUpperCase();
  if (QUOTES.includes(explicit)) return explicit;
  const market = String(tradingviewSymbol || "").trim().toUpperCase().split(":").pop();
  return QUOTES.find((quote) => market === `${base}${quote}`) || null;
}

export function marketDisplayLabel(symbol, { assetClass, quoteCurrency, tradingviewSymbol } = {}) {
  const base = String(symbol || "").trim().toUpperCase();
  if (!base) return null;
  const kind = String(assetClass || "").trim().toLowerCase();
  if (kind && kind !== "crypto") return base;
  const quote = marketDisplayQuote(base, { quoteCurrency, tradingviewSymbol });
  if (quote) return `${base}/${quote}`;
  if (kind === "crypto" || KNOWN_CRYPTO.has(base)) return null;
  return base;
}
