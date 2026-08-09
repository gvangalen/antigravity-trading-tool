"use client";

import { useState, useEffect } from "react";
import { fetchWatchlist, addToWatchlist, removeFromWatchlist } from "@/lib/api/watchlist";

const WATCHLIST_CACHE_TTL_MS = 30_000;

let watchlistCache = [];
let watchlistCacheUpdatedAt = 0;
let watchlistInFlightPromise = null;

function hasFreshWatchlistCache() {
  return Date.now() - watchlistCacheUpdatedAt < WATCHLIST_CACHE_TTL_MS;
}

function normalizeWatchlistItem(item) {
  if (typeof item === "string") {
    const symbol = item.toUpperCase();
    return {
      symbol,
      display_name: symbol,
      asset_class: "crypto",
      logo_url: null,
      tradingview_symbol: null,
    };
  }

  const symbol = String(item?.symbol || "").toUpperCase();
  return {
    symbol,
    display_name: item?.display_name || item?.displayName || symbol,
    asset_class: item?.asset_class || item?.assetClass || "crypto",
    logo_url: item?.logo_url || item?.logoUrl || null,
    tradingview_symbol: item?.tradingview_symbol || item?.tradingviewSymbol || null,
  };
}

async function loadWatchlistShared(forceFresh = false) {
  if (!forceFresh && hasFreshWatchlistCache()) {
    return watchlistCache;
  }

  if (!watchlistInFlightPromise) {
    watchlistInFlightPromise = fetchWatchlist()
      .then((data) => {
        watchlistCache = Array.isArray(data) ? data.map(normalizeWatchlistItem).filter((item) => item.symbol) : [];
        watchlistCacheUpdatedAt = Date.now();
        return watchlistCache;
      })
      .finally(() => {
        watchlistInFlightPromise = null;
      });
  }

  return watchlistInFlightPromise;
}

export function useWatchlist(options = {}) {
  const { autoLoad = true } = options;
  const [watchlist, setWatchlist] = useState(() => (hasFreshWatchlistCache() ? watchlistCache : []));
  const [loading, setLoading] = useState(() => autoLoad && !hasFreshWatchlistCache());

  useEffect(() => {
    if (autoLoad) {
      void loadWatchlist();
    } else {
      setLoading(false);
    }

    // Listen for changes from other components
    const handleSync = () => loadWatchlist();
    window.addEventListener("watchlist-updated", handleSync);
    return () => window.removeEventListener("watchlist-updated", handleSync);
  }, [autoLoad]);

  async function loadWatchlist(forceFresh = false) {
    try {
      setLoading(true);
      const data = await loadWatchlistShared(forceFresh);
      setWatchlist(data || []);
      return data || [];
    } catch (err) {
      console.error("❌ Watchlist load error:", err);
      return [];
    } finally {
      setLoading(false);
    }
  }

  const notify = () => {
    watchlistCacheUpdatedAt = 0;
    window.dispatchEvent(new CustomEvent("watchlist-updated"));
  };

  async function add(asset) {
    try {
      await addToWatchlist(asset);
      await loadWatchlist(true);
      notify();
    } catch (err) {
      console.error("❌ Watchlist add error:", err);
    }
  }

  async function remove(symbol) {
    try {
      await removeFromWatchlist(symbol);
      await loadWatchlist(true);
      notify();
    } catch (err) {
      console.error("❌ Watchlist remove error:", err);
    }
  }

  const isInWatchlist = (symbol) => {
    const normalized = symbol?.toUpperCase();
    return (watchlist || []).some((item) => item?.symbol === normalized);
  };

  return {
    watchlist,
    symbols: (watchlist || []).map((item) => item.symbol).filter(Boolean),
    loading,
    add,
    remove,
    isInWatchlist,
    refresh: (forceFresh = true) => loadWatchlist(forceFresh),
  };
}
