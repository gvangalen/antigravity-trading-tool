"use client";

import { useState, useEffect } from "react";
import { fetchWatchlist, addToWatchlist, removeFromWatchlist } from "@/lib/api/watchlist";
import {
  fetchCachedResource,
  getCachedResourceSnapshot,
  markCachedResourceStale,
  setCachedResourceData,
  subscribeCachedResource,
} from "@/lib/clientDataCache";

const WATCHLIST_CACHE_TTL_MS = 30_000;
const WATCHLIST_CACHE_KEY = "watchlist:default";

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
  return fetchCachedResource(WATCHLIST_CACHE_KEY, {
    ttlMs: WATCHLIST_CACHE_TTL_MS,
    forceFresh,
    initialData: [],
    fetcher: async () => {
      const data = await fetchWatchlist();
      return Array.isArray(data)
        ? data.map(normalizeWatchlistItem).filter((item) => item.symbol)
        : [];
    },
  });
}

export function useWatchlist(options = {}) {
  const { autoLoad = true } = options;
  const initialSnapshot = getCachedResourceSnapshot(WATCHLIST_CACHE_KEY, []);
  const [watchlist, setWatchlist] = useState(initialSnapshot.data || []);
  const [loading, setLoading] = useState(() => autoLoad && !initialSnapshot.hasData);

  useEffect(() => {
    const unsubscribe = subscribeCachedResource(WATCHLIST_CACHE_KEY, () => {
      const snapshot = getCachedResourceSnapshot(WATCHLIST_CACHE_KEY, []);
      setWatchlist(snapshot.data || []);
    });

    if (autoLoad) {
      void loadWatchlist();
    } else {
      setLoading(false);
    }

    // Listen for changes from other components
    const handleSync = () => loadWatchlist();
    window.addEventListener("watchlist-updated", handleSync);
    return () => {
      unsubscribe();
      window.removeEventListener("watchlist-updated", handleSync);
    };
  }, [autoLoad]);

  async function loadWatchlist(forceFresh = false) {
    try {
      if (!getCachedResourceSnapshot(WATCHLIST_CACHE_KEY, []).hasData) {
        setLoading(true);
      }
      const data = await loadWatchlistShared(forceFresh);
      setWatchlist(data || []);
      return data || [];
    } catch (err) {
      console.error("❌ Watchlist load error:", err);
      return getCachedResourceSnapshot(WATCHLIST_CACHE_KEY, []).data || [];
    } finally {
      setLoading(false);
    }
  }

  const notify = () => {
    markCachedResourceStale(WATCHLIST_CACHE_KEY);
    window.dispatchEvent(new CustomEvent("watchlist-updated"));
  };

  async function add(asset) {
    try {
      await addToWatchlist(asset);
      const data = await loadWatchlist(true);
      setCachedResourceData(WATCHLIST_CACHE_KEY, data || []);
      notify();
    } catch (err) {
      console.error("❌ Watchlist add error:", err);
    }
  }

  async function remove(symbol) {
    try {
      await removeFromWatchlist(symbol);
      const data = await loadWatchlist(true);
      setCachedResourceData(WATCHLIST_CACHE_KEY, data || []);
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
