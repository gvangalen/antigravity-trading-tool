import { fetchAuth } from "@/lib/api/auth";

export async function fetchWatchlist() {
  return await fetchAuth("/api/watchlist");
}

export async function addToWatchlist(asset) {
  const payload = typeof asset === "string"
    ? { symbol: asset }
    : {
        symbol: asset?.symbol,
        asset_class: asset?.assetClass || asset?.asset_class || null,
        display_name: asset?.displayName || asset?.display_name || null,
        tradingview_symbol: asset?.tradingviewSymbol || asset?.tradingview_symbol || null,
      };
  return await fetchAuth("/api/watchlist", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function removeFromWatchlist(symbol) {
  return await fetchAuth(`/api/watchlist/${symbol}`, {
    method: "DELETE",
  });
}
