"use client";

import { useEffect, useState } from "react";
import { useVisibilityPolling } from "@/hooks/useVisibilityPolling";
import { fetchAssetWorkspace, fetchWorkspaceWatchlist } from "@/lib/api/workspace";
import { fetchLatestPrice } from "@/lib/api/market";
import { getDailyScores } from "@/lib/api/scores";

const WORKSPACE_REQUEST_TIMEOUT_MS = 15000;

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
    regime: null,
    generated_at: new Date().toISOString(),
    ai_calls: 0,
  };
}

export function useAssetWorkspaceData(symbol, periods, watchlistSymbols) {
  const [workspace, setWorkspace] = useState(null);
  const [watchlist, setWatchlist] = useState([]);
  const [loading, setLoading] = useState(true);
  const [watchlistLoading, setWatchlistLoading] = useState(true);
  const [error, setError] = useState(null);
  const [isFallbackWorkspace, setIsFallbackWorkspace] = useState(false);
  const watchlistKey = (watchlistSymbols || []).join(",");

  async function reloadWorkspace() {
    setLoading(true);
    const controller = new AbortController();
    const timeoutId = window.setTimeout(() => controller.abort(), WORKSPACE_REQUEST_TIMEOUT_MS);
    try {
      const payload = await fetchAssetWorkspace(symbol, periods, {
        signal: controller.signal,
        forceFresh: true,
      });
      setWorkspace(payload);
      setError(null);
      setIsFallbackWorkspace(false);
      return payload;
    } catch (nextError) {
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
      setWorkspace(fallback);
      setError(nextError);
      setIsFallbackWorkspace(true);
      return fallback;
    } finally {
      window.clearTimeout(timeoutId);
      setLoading(false);
    }
  }

  async function reloadWatchlist() {
    setWatchlistLoading(true);
    const controller = new AbortController();
    const timeoutId = window.setTimeout(() => controller.abort(), WORKSPACE_REQUEST_TIMEOUT_MS);
    try {
      const payload = await fetchWorkspaceWatchlist(watchlistSymbols || [], {
        signal: controller.signal,
        forceFresh: true,
      });
      setWatchlist(Array.isArray(payload?.rows) ? payload.rows : []);
      return payload;
    } catch {
      setWatchlist([]);
      return null;
    } finally {
      window.clearTimeout(timeoutId);
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
    isFallbackWorkspace,
    reloadWorkspace,
    reloadWatchlist,
  };
}
