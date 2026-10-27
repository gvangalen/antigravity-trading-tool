import { fetchAuth } from "@/lib/api/auth";

export async function fetchTradingMarkets(symbol) {
  return await fetchAuth(`/api/assets/${encodeURIComponent(String(symbol || "").toUpperCase())}/trading-markets`, {
    method: "GET",
    forceFresh: true,
  });
}

export async function selectTradingMarket(symbol, quoteCurrency, options = {}) {
  const { periods, watchlistSymbols = [], includeWorkspace = false, ...requestOptions } = options;
  const params = new URLSearchParams();
  if (includeWorkspace) params.set("include_workspace", "true");
  if (periods) {
    params.set("market_period", periods.market || "day");
    params.set("macro_period", periods.macro || "day");
    params.set("technical_period", periods.technical || "day");
  }
  if (watchlistSymbols.length) params.set("watchlist_symbols", watchlistSymbols.join(","));
  return await fetchAuth(
    `/api/assets/${encodeURIComponent(String(symbol || "").toUpperCase())}` +
      `/trading-markets/${encodeURIComponent(String(quoteCurrency || "").toUpperCase())}/select` +
      (params.size ? `?${params.toString()}` : ""),
    { method: "POST", ...requestOptions },
  );
}

export async function searchAssets(query, options = {}) {
  const {
    assetClasses = ["crypto", "stock"],
    limit = 8,
  } = options;

  const normalizedQuery = String(query || "").trim();
  if (!normalizedQuery) return [];

  const params = new URLSearchParams({
    q: normalizedQuery,
    asset_classes: assetClasses.join(","),
    limit: String(limit),
  });

  return await fetchAuth(`/api/assets/search?${params.toString()}`, {
    method: "GET",
  });
}
