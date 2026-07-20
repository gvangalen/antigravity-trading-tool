"use client";

import { fetchAuth } from "@/lib/api/auth";

export function fetchAssetWorkspace(symbol, periods = {}) {
  const params = new URLSearchParams({
    symbol: String(symbol || "BTC").toUpperCase(),
    market_period: periods.market || "day",
    macro_period: periods.macro || "day",
    technical_period: periods.technical || "day",
  });
  return fetchAuth(`/api/workspace/asset?${params.toString()}`, { method: "GET" });
}

export function fetchWorkspaceWatchlist(symbols = []) {
  const normalized = Array.from(
    new Set(symbols.map((symbol) => String(symbol || "").toUpperCase()).filter(Boolean))
  );
  const params = new URLSearchParams({ symbols: normalized.join(",") });
  return fetchAuth(`/api/workspace/watchlist?${params.toString()}`, { method: "GET" });
}
