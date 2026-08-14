"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { trackAssistantEvent } from "@/lib/api/assistantAnalytics";
import { useVisibilityPolling } from "@/hooks/useVisibilityPolling";
import { fetchAssetWorkspace } from "@/lib/api/workspace";
import { fetchLatestPrice } from "@/lib/api/market";
import { getDailyScores } from "@/lib/api/scores";
import { subscribeWorkspaceRefresh } from "@/lib/workspaceSync";
import { setWorkspaceSnapshot } from "@/lib/workspaceSnapshotStore";

const WORKSPACE_REQUEST_TIMEOUT_MS = 15000;
const WORKSPACE_CACHE_TTL_MS = 300_000;
const FOREGROUND_REFRESH_COOLDOWN_MS = 30_000;
const WORKSPACE_FORCE_REFRESH_COOLDOWN_MS = 2_500;

const workspaceCache = new Map();
const workspaceInFlightRequests = new Map();

function getFreshCache(cache, key, maxAgeMs) {
  const entry = cache.get(key);
  if (!entry) return null;
  if (Date.now() - entry.savedAt > maxAgeMs) return null;
  return entry.value;
}

function setFreshCache(cache, key, value) {
  cache.set(key, {
    value,
    savedAt: Date.now(),
  });
}

function normalizeQuotePayload(quote) {
  if (!quote || typeof quote !== "object") return null;
  const price = Number(quote.price);
  if (!Number.isFinite(price)) return null;
  const change24h = Number(quote.change_24h);
  const volume = Number(quote.volume);
  return {
    price,
    change_24h: Number.isFinite(change24h) ? change24h : null,
    volume: Number.isFinite(volume) ? volume : null,
    as_of: quote.timestamp ?? quote.as_of ?? null,
    source: "market_data",
    status: "available",
    stale: false,
    age_seconds: 0,
  };
}

function mergeQuoteBackfill(workspace, quoteMap, assetSymbol) {
  if (!workspace || !quoteMap || quoteMap.size === 0) return workspace;

  let changed = false;
  const nextWorkspace = { ...workspace };
  const activeQuote = quoteMap.get(assetSymbol);
  if (activeQuote && (!nextWorkspace.quote || nextWorkspace.quote.price === null || nextWorkspace.quote.price === undefined)) {
    nextWorkspace.quote = {
      ...(nextWorkspace.quote || {}),
      ...activeQuote,
    };
    changed = true;
  }

  if (Array.isArray(nextWorkspace?.watchlist?.rows)) {
    const nextRows = nextWorkspace.watchlist.rows.map((row) => {
      const rowSymbol = String(row?.symbol || "").toUpperCase();
      const backfilledQuote = quoteMap.get(rowSymbol);
      if (!backfilledQuote || (row?.price !== null && row?.price !== undefined)) {
        return row;
      }
      changed = true;
      return {
        ...row,
        price: backfilledQuote.price,
        change_24h: backfilledQuote.change_24h,
        quote: {
          ...(row?.quote || {}),
          ...backfilledQuote,
        },
      };
    });

    if (changed) {
      nextWorkspace.watchlist = {
        ...nextWorkspace.watchlist,
        rows: nextRows,
      };
    }
  }

  return changed ? nextWorkspace : workspace;
}

function hasFreshWorkspaceCache(key) {
  return Boolean(getFreshCache(workspaceCache, key, WORKSPACE_CACHE_TTL_MS));
}

function buildWorkspaceFallback(symbol, periods, quote, daily) {
  const marketScore = daily?.market?.score ?? null;
  const macroScore = daily?.macro?.score ?? null;
  const technicalScore = daily?.technical?.score ?? null;
  const availableScores = [marketScore, macroScore, technicalScore].filter((value) => Number.isFinite(Number(value)));
  const combined = availableScores.length
    ? Math.round(availableScores.reduce((sum, value) => sum + Number(value), 0) / availableScores.length)
    : null;
  const category = (score, interpretation) => ({
    rows: [],
    score: {
      score: Number.isFinite(Number(score)) ? Number(score) : null,
      period: "day",
      sample_size: null,
      status: Number.isFinite(Number(score)) ? "available" : "insufficient_data",
    },
    freshness: null,
    interpretation: interpretation || null,
  });

  return {
    symbol: String(symbol || "BTC").toUpperCase(),
    periods,
    quote: quote ? {
      price: quote.price ?? null,
      change_24h: quote.change_24h ?? null,
      volume: quote.volume ?? null,
      stale: false,
      age_seconds: null,
      as_of: quote.timestamp ?? quote.as_of ?? null,
      source: "market_data",
      status: "available",
    } : null,
    categories: {
      market: category(marketScore, daily?.market?.interpretation),
      macro: category(macroScore, daily?.macro?.interpretation),
      technical: category(technicalScore, daily?.technical?.interpretation),
    },
    combined: {
      score: combined,
      periods,
      basis: "daily_scores_fallback",
      weights: {},
      status: combined !== null ? "available" : "insufficient_data",
    },
    daily: daily || null,
    master: {
      weights: {},
      master_bias: "–",
      status: "fallback",
      reason: "workspace_request_timeout",
      date: null,
    },
    regime: {
      available: false,
      data_status: "fallback",
      reason: "workspace_request_timeout",
    },
    generated_at: new Date().toISOString(),
    ai_calls: 0,
  };
}

export function useAssetWorkspaceData(symbol, periods, watchlistSymbols) {
  const normalizedWatchlistSymbols = Array.from(
    new Set((watchlistSymbols || []).map((item) => String(item || "").toUpperCase()).filter(Boolean))
  );
  const watchlistKey = normalizedWatchlistSymbols.join(",");
  const workspaceKey = JSON.stringify({
    symbol: String(symbol || "BTC").toUpperCase(),
    market: periods?.market || "day",
    macro: periods?.macro || "day",
    technical: periods?.technical || "day",
    watchlist: watchlistKey,
  });
  const cachedWorkspace = getFreshCache(workspaceCache, workspaceKey, WORKSPACE_CACHE_TTL_MS);
  const cachedWatchlist = Array.isArray(cachedWorkspace?.watchlist?.rows)
    ? cachedWorkspace.watchlist.rows
    : [];

  const [workspace, setWorkspace] = useState(cachedWorkspace);
  const [watchlist, setWatchlist] = useState(cachedWatchlist);
  const [loading, setLoading] = useState(!cachedWorkspace);
  const [watchlistLoading, setWatchlistLoading] = useState(!cachedWorkspace);
  const [error, setError] = useState(null);
  const [isFallbackWorkspace, setIsFallbackWorkspace] = useState(false);
  const fallbackStartedAtRef = useRef(null);
  const activeReloadPromiseRef = useRef(null);
  const quoteBackfillRequestKeyRef = useRef("");
  const latestWorkspaceRef = useRef(cachedWorkspace || null);
  const latestWatchlistRef = useRef(cachedWatchlist);
  const lastForegroundRefreshAtRef = useRef(0);
  const lastSuccessfulRefreshAtRef = useRef(cachedWorkspace ? Date.now() : 0);
  const requestSequenceRef = useRef(0);
  const assetSymbol = String(symbol || "BTC").toUpperCase();

  useEffect(() => {
    const fallbackWorkspace = latestWorkspaceRef.current;
    const fallbackWatchlist = Array.isArray(fallbackWorkspace?.watchlist?.rows)
      ? fallbackWorkspace.watchlist.rows
      : latestWatchlistRef.current;
    const nextWorkspace = cachedWorkspace || fallbackWorkspace || null;
    const nextWatchlist = cachedWorkspace
      ? cachedWatchlist
      : Array.isArray(fallbackWatchlist)
        ? fallbackWatchlist
        : [];

    setWorkspace(nextWorkspace);
    setWatchlist(nextWatchlist);
    setLoading(!cachedWorkspace && !nextWorkspace);
    setWatchlistLoading(!cachedWorkspace && !nextWatchlist.length);
    setError(null);
    setIsFallbackWorkspace(false);
    fallbackStartedAtRef.current = null;
    latestWorkspaceRef.current = nextWorkspace;
    latestWatchlistRef.current = nextWatchlist;
    lastSuccessfulRefreshAtRef.current = cachedWorkspace ? Date.now() : 0;
  }, [cachedWatchlist, cachedWorkspace, workspaceKey]);

  useEffect(() => {
    latestWorkspaceRef.current = workspace || null;
    if (workspace) {
      setWorkspaceSnapshot(assetSymbol, workspace);
    }
  }, [workspace]);

  useEffect(() => {
    latestWatchlistRef.current = Array.isArray(watchlist) ? watchlist : [];
  }, [watchlist]);

  function trackWorkspaceTelemetry(eventName, metadata = {}) {
    void trackAssistantEvent({
      event_name: eventName,
      page: "/asset",
      surface: "web",
      asset: assetSymbol,
      flow_type: "asset_workspace",
      metadata: {
        market_period: periods?.market,
        macro_period: periods?.macro,
        technical_period: periods?.technical,
        ...metadata,
      },
    });
  }

  const reloadWorkspace = useCallback(async ({ forceNetwork = false } = {}) => {
    const cached = getFreshCache(workspaceCache, workspaceKey, WORKSPACE_CACHE_TTL_MS);
    if (cached && !forceNetwork) {
      setWorkspace(cached);
      setWatchlist(Array.isArray(cached?.watchlist?.rows) ? cached.watchlist.rows : []);
      setWatchlistLoading(false);
      setLoading(false);
      return cached;
    }

    if (activeReloadPromiseRef.current) {
      return activeReloadPromiseRef.current;
    }

    if (
      forceNetwork &&
      cached &&
      Date.now() - lastSuccessfulRefreshAtRef.current < WORKSPACE_FORCE_REFRESH_COOLDOWN_MS
    ) {
      setWorkspace(cached);
      setWatchlist(Array.isArray(cached?.watchlist?.rows) ? cached.watchlist.rows : []);
      setWatchlistLoading(false);
      setLoading(false);
      return cached;
    }

    const requestId = ++requestSequenceRef.current;
    if (!cached && !latestWorkspaceRef.current) {
      setLoading(true);
    }
    if (!cached && !latestWatchlistRef.current?.length) {
      setWatchlistLoading(true);
    }
    let request = workspaceInFlightRequests.get(workspaceKey);

    if (!request) {
      const controller = new AbortController();
      const timeoutId = window.setTimeout(() => controller.abort(), WORKSPACE_REQUEST_TIMEOUT_MS);
      const requestPromise = fetchAssetWorkspace(symbol, periods, {
        signal: controller.signal,
        forceFresh: forceNetwork,
        watchlistSymbols: normalizedWatchlistSymbols,
      }).finally(() => {
        window.clearTimeout(timeoutId);
        const activeRequest = workspaceInFlightRequests.get(workspaceKey);
        if (activeRequest?.promise === requestPromise) {
          workspaceInFlightRequests.delete(workspaceKey);
        }
      });
      request = {
        promise: requestPromise,
        forceNetwork,
      };
      workspaceInFlightRequests.set(workspaceKey, request);
    }

    const reloadPromise = (async () => {
      try {
      const payload = await request.promise;
      if (requestId !== requestSequenceRef.current) return payload;
      setFreshCache(workspaceCache, workspaceKey, payload);
      lastSuccessfulRefreshAtRef.current = Date.now();
      if (fallbackStartedAtRef.current) {
        trackWorkspaceTelemetry("asset_workspace_recovered", {
          fallback_duration_ms: Date.now() - fallbackStartedAtRef.current,
          recovery_source: "workspace_live",
        });
        fallbackStartedAtRef.current = null;
      }
      setWorkspace(payload);
      setWatchlist(Array.isArray(payload?.watchlist?.rows) ? payload.watchlist.rows : []);
      setError(null);
      setIsFallbackWorkspace(false);
      return payload;
    } catch (nextError) {
      if (requestId !== requestSequenceRef.current) {
        throw nextError;
      }
      const liveWorkspace = latestWorkspaceRef.current;
      if (liveWorkspace) {
        if (!fallbackStartedAtRef.current) {
          fallbackStartedAtRef.current = Date.now();
          trackWorkspaceTelemetry("asset_workspace_stale_workspace_retained", {
            error_name: nextError?.name || "unknown_error",
            reason: nextError?.name === "AbortError" ? "workspace_timeout" : "workspace_request_failed",
          });
        }
        setWorkspace(liveWorkspace);
        setWatchlist(Array.isArray(liveWorkspace?.watchlist?.rows) ? liveWorkspace.watchlist.rows : []);
        setError(nextError);
        setIsFallbackWorkspace(true);
        return liveWorkspace;
      }

      const [quoteResult, dailyScoresResult] = await Promise.allSettled([
        fetchLatestPrice(symbol, { forceFresh: false }),
        getDailyScores(symbol),
      ]);
      const fallback = buildWorkspaceFallback(
        symbol,
        periods,
        quoteResult.status === "fulfilled" ? quoteResult.value : null,
        dailyScoresResult.status === "fulfilled" ? dailyScoresResult.value : null,
      );
      if (!fallbackStartedAtRef.current) {
        fallbackStartedAtRef.current = Date.now();
        trackWorkspaceTelemetry("asset_workspace_fallback_served", {
          error_name: nextError?.name || "unknown_error",
          reason: nextError?.name === "AbortError" ? "workspace_timeout" : "workspace_request_failed",
          quote_available: quoteResult.status === "fulfilled",
          daily_scores_available: dailyScoresResult.status === "fulfilled",
        });
      }
      setWorkspace(fallback);
      setWatchlist(Array.isArray(latestWorkspaceRef.current?.watchlist?.rows)
        ? latestWorkspaceRef.current.watchlist.rows
        : Array.isArray(cached?.watchlist?.rows)
          ? cached.watchlist.rows
          : []);
      setError(nextError);
      setIsFallbackWorkspace(true);
      return fallback;
    } finally {
      if (requestId === requestSequenceRef.current) {
        if (!getFreshCache(workspaceCache, workspaceKey, WORKSPACE_CACHE_TTL_MS)) {
          setLoading(false);
          setWatchlistLoading(false);
        } else {
          setLoading(false);
          setWatchlistLoading(false);
        }
      }
      if (activeReloadPromiseRef.current === reloadPromise) {
        activeReloadPromiseRef.current = null;
      }
    }
    })();

    activeReloadPromiseRef.current = reloadPromise;
    return reloadPromise;
  }, [cachedWatchlist.length, normalizedWatchlistSymbols, periods, symbol, workspaceKey]);

  useEffect(() => {
    const baseWorkspace = latestWorkspaceRef.current;
    const baseWatchlist = Array.isArray(latestWatchlistRef.current) ? latestWatchlistRef.current : [];
    const symbolsNeedingQuotes = new Set();

    if (baseWorkspace && (baseWorkspace?.quote?.price === null || baseWorkspace?.quote?.price === undefined)) {
      symbolsNeedingQuotes.add(assetSymbol);
    }

    baseWatchlist.forEach((row) => {
      if (row?.price === null || row?.price === undefined) {
        const rowSymbol = String(row?.symbol || "").toUpperCase();
        if (rowSymbol) {
          symbolsNeedingQuotes.add(rowSymbol);
        }
      }
    });

    if (!symbolsNeedingQuotes.size) {
      quoteBackfillRequestKeyRef.current = "";
      return;
    }

    const sortedSymbols = Array.from(symbolsNeedingQuotes).sort();
    const requestKey = `${workspaceKey}:quote-backfill:${sortedSymbols.join(",")}`;
    if (quoteBackfillRequestKeyRef.current === requestKey) return;
    quoteBackfillRequestKeyRef.current = requestKey;

    let cancelled = false;

    (async () => {
      const settled = await Promise.allSettled(
        sortedSymbols.map(async (nextSymbol) => {
          const quote = await fetchLatestPrice(nextSymbol, { forceFresh: false });
          return [nextSymbol, normalizeQuotePayload(quote)];
        })
      );

      if (cancelled) return;

      const quoteMap = new Map(
        settled
          .filter((result) => result.status === "fulfilled" && result.value?.[1]?.price !== null)
          .map((result) => result.value)
      );

      if (!quoteMap.size) return;

      setWorkspace((currentWorkspace) => {
        const mergedWorkspace = mergeQuoteBackfill(
          currentWorkspace || latestWorkspaceRef.current,
          quoteMap,
          assetSymbol,
        );
        if (!mergedWorkspace) return currentWorkspace;

        latestWorkspaceRef.current = mergedWorkspace;
        const nextWatchlistRows = Array.isArray(mergedWorkspace?.watchlist?.rows)
          ? mergedWorkspace.watchlist.rows
          : latestWatchlistRef.current;
        latestWatchlistRef.current = nextWatchlistRows;
        setWatchlist(nextWatchlistRows);
        setFreshCache(workspaceCache, workspaceKey, mergedWorkspace);
        return mergedWorkspace;
      });
    })();

    return () => {
      cancelled = true;
    };
  }, [assetSymbol, workspaceKey, watchlist]);

  const refreshWorkspaceIfStale = useCallback(() => {
    const cached = getFreshCache(workspaceCache, workspaceKey, WORKSPACE_CACHE_TTL_MS);
    if (cached && !isFallbackWorkspace) {
      if (latestWorkspaceRef.current !== cached) {
        setWorkspace(cached);
        setWatchlist(Array.isArray(cached?.watchlist?.rows) ? cached.watchlist.rows : []);
        setWatchlistLoading(false);
        setLoading(false);
      }
      return Promise.resolve(cached);
    }

    const shouldForceNetwork = !cached || isFallbackWorkspace;
    return reloadWorkspace({ forceNetwork: shouldForceNetwork });
  }, [isFallbackWorkspace, reloadWorkspace, workspaceKey]);

  async function reloadWatchlist() {
    return reloadWorkspace({ forceNetwork: true });
  }

  useEffect(() => {
    void reloadWorkspace({ forceNetwork: false });
  }, [workspaceKey]);

  useEffect(() => {
    return subscribeWorkspaceRefresh((payload) => {
      if (String(payload?.symbol || "").toUpperCase() !== assetSymbol) return;
      void reloadWorkspace({ forceNetwork: true });
    });
  }, [assetSymbol, reloadWorkspace]);

  useEffect(() => {
    if (typeof window === "undefined") return undefined;

    const refreshIfNeeded = () => {
      const now = Date.now();
      if (now - lastForegroundRefreshAtRef.current < FOREGROUND_REFRESH_COOLDOWN_MS) return;
      if (hasFreshWorkspaceCache(workspaceKey) && !isFallbackWorkspace) return;
      lastForegroundRefreshAtRef.current = now;
      void refreshWorkspaceIfStale();
    };

    const handleFocus = () => refreshIfNeeded();

    window.addEventListener("focus", handleFocus);

    return () => {
      window.removeEventListener("focus", handleFocus);
    };
  }, [isFallbackWorkspace, refreshWorkspaceIfStale, workspaceKey]);

  useVisibilityPolling(() => refreshWorkspaceIfStale(), {
    intervalMs: 60_000,
    backgroundIntervalMs: 300_000,
    runImmediately: false,
    triggerOnVisible: false,
    deps: [symbol, periods.market, periods.macro, periods.technical, watchlistKey],
  });

  return {
    workspace,
    watchlist,
    loading,
    watchlistLoading,
    error,
    isFallbackWorkspace,
    reloadWorkspace,
    reloadWatchlist,
  };
}
