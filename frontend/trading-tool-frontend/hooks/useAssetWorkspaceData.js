"use client";

import { useEffect, useState } from "react";
import { useVisibilityPolling } from "@/hooks/useVisibilityPolling";
import { fetchAssetWorkspace, fetchWorkspaceWatchlist } from "@/lib/api/workspace";

export function useAssetWorkspaceData(symbol, periods, watchlistSymbols) {
  const [workspace, setWorkspace] = useState(null);
  const [watchlist, setWatchlist] = useState([]);
  const [loading, setLoading] = useState(true);
  const [watchlistLoading, setWatchlistLoading] = useState(true);
  const [error, setError] = useState(null);
  const watchlistKey = (watchlistSymbols || []).join(",");

  async function reloadWorkspace() {
    setLoading(true);
    try {
      const payload = await fetchAssetWorkspace(symbol, periods);
      setWorkspace(payload);
      setError(null);
      return payload;
    } catch (nextError) {
      setError(nextError);
      return null;
    } finally {
      setLoading(false);
    }
  }

  async function reloadWatchlist() {
    setWatchlistLoading(true);
    try {
      const payload = await fetchWorkspaceWatchlist(watchlistSymbols || []);
      setWatchlist(Array.isArray(payload?.rows) ? payload.rows : []);
      return payload;
    } catch {
      setWatchlist([]);
      return null;
    } finally {
      setWatchlistLoading(false);
    }
  }

  useEffect(() => {
    void reloadWorkspace();
  }, [symbol, periods.market, periods.macro, periods.technical]);

  useEffect(() => {
    void reloadWatchlist();
  }, [watchlistKey]);

  useVisibilityPolling(reloadWorkspace, {
    intervalMs: 60_000,
    backgroundIntervalMs: 300_000,
    runImmediately: false,
    deps: [symbol, periods.market, periods.macro, periods.technical],
  });

  useVisibilityPolling(reloadWatchlist, {
    intervalMs: 60_000,
    backgroundIntervalMs: 300_000,
    runImmediately: false,
    deps: [watchlistKey],
  });

  return {
    workspace,
    watchlist,
    loading,
    watchlistLoading,
    error,
    reloadWorkspace,
    reloadWatchlist,
  };
}
