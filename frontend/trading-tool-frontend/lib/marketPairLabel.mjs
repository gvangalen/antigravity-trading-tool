/** Show the exact saved market, never infer a quote from the funding currency. */
export function marketPairLabel(record) {
  const symbol = String(record?.symbol || record?.setup_symbol || record?.strategy?.setup?.symbol || "").toUpperCase();
  const marketId = record?.market_id ?? record?.setup_market_id ?? record?.strategy?.market_id ?? record?.strategy?.setup?.market_id;
  const quote = String(record?.quote_currency || record?.market_quote_currency || record?.strategy?.quote_currency || record?.strategy?.setup?.quote_currency || "").toUpperCase();
  if (marketId != null && symbol && quote) return `${symbol}/${quote}`;
  return symbol || "—";
}
