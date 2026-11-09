"use client";

import { useState, useEffect, useRef } from "react";
import { useAuth } from "@/components/auth/AuthProvider";
import { createWatchlistRequestTracker, watchlistCacheKey } from "@/lib/workspace/watchlistMembership.mjs";
import { fetchWatchlist, addToWatchlist, removeFromWatchlist } from "@/lib/api/watchlist";
import {
  getCachedResourceSnapshot,
  isCachedResourceFresh,
  markCachedResourceStale,
  setCachedResourceData,
  subscribeCachedResource,
  clearCachedResource,
} from "@/lib/clientDataCache";

const WATCHLIST_CACHE_TTL_MS = 30_000;
const activeWatchlistKeys = new Map();
const requestTracker = createWatchlistRequestTracker();

export function invalidateWatchlist() {
  activeWatchlistKeys.forEach((_count, key) => markCachedResourceStale(key));
  if (typeof window !== "undefined") {
    window.dispatchEvent(new CustomEvent("watchlist-updated"));
  }
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
      market_id: null,
      quote_currency: null,
    };
  }

  const symbol = String(item?.symbol || "").toUpperCase();
  return {
    symbol,
    display_name: item?.display_name || item?.displayName || symbol,
    asset_class: item?.asset_class || item?.assetClass || "crypto",
    logo_url: item?.logo_url || item?.logoUrl || null,
    tradingview_symbol: item?.tradingview_symbol || item?.tradingviewSymbol || null,
    market_id: item?.market_id || item?.marketId || null,
    quote_currency: item?.quote_currency || item?.quoteCurrency || null,
  };
}

async function loadWatchlistShared(cacheKey, forceFresh = false) {
  if (!forceFresh && isCachedResourceFresh(cacheKey, WATCHLIST_CACHE_TTL_MS)) {
    return { data: getCachedResourceSnapshot(cacheKey, []).data || [], current: true };
  }
  const generation = requestTracker.next(cacheKey);
  const data = await fetchWatchlist();
  if (!requestTracker.isCurrent(cacheKey, generation)) return { data: [], current: false };
  const normalized = Array.isArray(data)
    ? data.map(normalizeWatchlistItem).filter((item) => item.symbol)
    : [];
  setCachedResourceData(cacheKey, normalized);
  return { data: normalized, current: true };
}

export function useWatchlist(options = {}) {
  const { autoLoad = true } = options;
  const { user } = useAuth() || {};
  const cacheKey = watchlistCacheKey(user?.id);
  const activeCacheKeyRef = useRef(cacheKey);
  activeCacheKeyRef.current = cacheKey;
  const initialSnapshot = cacheKey ? getCachedResourceSnapshot(cacheKey, []) : { data: [], hasData: false };
  const [watchlistState, setWatchlistState] = useState({ key: cacheKey, data: initialSnapshot.data || [] });
  const [loading, setLoading] = useState(() => autoLoad && Boolean(cacheKey) && !initialSnapshot.hasData);
  const watchlist = watchlistState.key === cacheKey ? watchlistState.data : [];

  useEffect(() => {
    if (!cacheKey) {
      setWatchlistState({ key: null, data: [] });
      setLoading(false);
      return undefined;
    }
    activeWatchlistKeys.set(cacheKey, (activeWatchlistKeys.get(cacheKey) || 0) + 1);
    setWatchlistState({ key: cacheKey, data: getCachedResourceSnapshot(cacheKey, []).data || [] });
    const unsubscribe = subscribeCachedResource(cacheKey, () => {
      if (activeCacheKeyRef.current !== cacheKey) return;
      const snapshot = getCachedResourceSnapshot(cacheKey, []);
      setWatchlistState({ key: cacheKey, data: snapshot.data || [] });
    });

    if (autoLoad) {
      void loadWatchlist(true);
    } else {
      setLoading(false);
    }

    // Listen for changes from other components
    const handleSync = () => loadWatchlist(true);
    const handleAuthScopeChanged = () => {
      activeCacheKeyRef.current = null;
      requestTracker.next(cacheKey);
      clearCachedResource(cacheKey);
      setWatchlistState({ key: null, data: [] });
      setLoading(false);
    };
    window.addEventListener("watchlist-updated", handleSync);
    window.addEventListener("tradamind:auth-scope-changed", handleAuthScopeChanged);
    return () => {
      const remaining = (activeWatchlistKeys.get(cacheKey) || 1) - 1;
      if (remaining) activeWatchlistKeys.set(cacheKey, remaining);
      else activeWatchlistKeys.delete(cacheKey);
      unsubscribe();
      window.removeEventListener("watchlist-updated", handleSync);
      window.removeEventListener("tradamind:auth-scope-changed", handleAuthScopeChanged);
    };
  }, [autoLoad, cacheKey]);

  async function loadWatchlist(forceFresh = false) {
    if (!cacheKey || activeCacheKeyRef.current !== cacheKey) return [];
    try {
      if (!getCachedResourceSnapshot(cacheKey, []).hasData) {
        setLoading(true);
      }
      const result = await loadWatchlistShared(cacheKey, forceFresh);
      if (!result.current || activeCacheKeyRef.current !== cacheKey) return [];
      setWatchlistState({ key: cacheKey, data: result.data });
      return result.data;
    } catch (err) {
      console.error("❌ Watchlist load error:", err);
      return getCachedResourceSnapshot(cacheKey, []).data || [];
    } finally {
      if (activeCacheKeyRef.current === cacheKey) setLoading(false);
    }
  }

  async function add(asset) {
    try {
      if (!cacheKey || activeCacheKeyRef.current !== cacheKey) return;
      await addToWatchlist(asset);
      if (activeCacheKeyRef.current !== cacheKey) return;
      await loadWatchlist(true);
      if (activeCacheKeyRef.current !== cacheKey) return;
      invalidateWatchlist();
    } catch (err) {
      console.error("❌ Watchlist add error:", err);
      throw err;
    }
  }

  async function remove(symbol, marketId = null) {
    try {
      if (!cacheKey || activeCacheKeyRef.current !== cacheKey) return;
      await removeFromWatchlist(symbol, marketId);
      if (activeCacheKeyRef.current !== cacheKey) return;
      await loadWatchlist(true);
      if (activeCacheKeyRef.current !== cacheKey) return;
      invalidateWatchlist();
    } catch (err) {
      console.error("❌ Watchlist remove error:", err);
      throw err;
    }
  }

  const isInWatchlist = (symbol) => {
    const normalized = symbol?.toUpperCase();
    return (watchlist || []).some((item) => item?.symbol === normalized);
  };

  return {
    watchlist,
    symbols: Array.from(new Set((watchlist || []).map((item) => item.symbol).filter(Boolean))),
    loading: watchlistState.key === cacheKey ? loading : Boolean(cacheKey && autoLoad),
    add,
    remove,
    isInWatchlist,
    refresh: (forceFresh = true) => loadWatchlist(forceFresh),
  };
}
