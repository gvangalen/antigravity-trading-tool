import { fetchAuth } from "@/lib/api/auth";

export async function fetchWatchlist() {
  return await fetchAuth("/api/watchlist", { forceFresh: true });
}

export async function addToWatchlist(asset) {
  const payload = typeof asset === "string"
    ? { symbol: asset }
    : {
        symbol: asset?.symbol,
        asset_class: asset?.assetClass || asset?.asset_class || null,
        display_name: asset?.displayName || asset?.display_name || null,
        tradingview_symbol: asset?.tradingviewSymbol || asset?.tradingview_symbol || null,
        market_id: asset?.marketId || asset?.market_id || null,
      };
  return await fetchAuth("/api/watchlist", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function removeFromWatchlist(symbol, marketId = null, options = {}) {
  const query = marketId == null ? "" : `?market_id=${encodeURIComponent(marketId)}`;
  return await fetchAuth(`/api/watchlist/${encodeURIComponent(symbol)}${query}`, {
    method: "DELETE",
    ...options,
  });
}
