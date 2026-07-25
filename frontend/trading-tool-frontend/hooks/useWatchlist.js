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

async function loadWatchlistShared(forceFresh = false) {
  if (!forceFresh && hasFreshWatchlistCache()) {
    return watchlistCache;
  }

  if (!watchlistInFlightPromise) {
    watchlistInFlightPromise = fetchWatchlist()
      .then((data) => {
        watchlistCache = Array.isArray(data) ? data : [];
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

  async function add(symbol) {
    try {
      await addToWatchlist(symbol);
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
    return (watchlist || []).includes(symbol?.toUpperCase());
  };

  return {
    watchlist,
    loading,
    add,
    remove,
    isInWatchlist,
    refresh: (forceFresh = true) => loadWatchlist(forceFresh),
  };
}
