"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useVisibilityPolling } from "@/hooks/useVisibilityPolling";
import { useTranslation } from "@/app/providers/I18nProvider";

import {
  fetchMarketData7d,
  fetchLatestPrice,
  fetchForwardReturnsWeek,
  fetchForwardReturnsMonth,
  fetchForwardReturnsQuarter,
  fetchForwardReturnsYear,
  fetchMarketDayData,
  fetchMarketWeekData,
  fetchMarketMonthData,
  fetchMarketQuarterData,
  getMarketIndicatorNames,
  getScoreRulesForMarketIndicator,
  marketIndicatorAdd,
  marketIndicatorDelete,
  getUserMarketIndicators,
  getMarketPreferences,
  bootstrapMarketPreferences,
  syncMarketPreferences,
} from "@/lib/api/market";

import { getDailyScores } from "@/lib/api/scores";

const MARKET_INDICATOR_NAMES_CACHE_TTL_MS = 5 * 60 * 1000;
let marketIndicatorNamesCache = [];
let marketIndicatorNamesCacheUpdatedAt = 0;
let marketIndicatorNamesInFlightPromise = null;

function hasFreshMarketIndicatorNamesCache() {
  return Date.now() - marketIndicatorNamesCacheUpdatedAt < MARKET_INDICATOR_NAMES_CACHE_TTL_MS;
}

async function loadMarketIndicatorNamesShared(forceFresh = false) {
  if (!forceFresh && hasFreshMarketIndicatorNamesCache()) {
    return marketIndicatorNamesCache;
  }

  if (!marketIndicatorNamesInFlightPromise) {
    marketIndicatorNamesInFlightPromise = getMarketIndicatorNames()
      .then((list) => {
        marketIndicatorNamesCache = Array.isArray(list) ? list : [];
        marketIndicatorNamesCacheUpdatedAt = Date.now();
        return marketIndicatorNamesCache;
      })
      .finally(() => {
        marketIndicatorNamesInFlightPromise = null;
      });
  }

  return marketIndicatorNamesInFlightPromise;
}

/* --------------------------------------------------------
   Advies logica
-------------------------------------------------------- */
const getAdvies = (score, commonT = {}) =>
  score >= 75
    ? `🟢 ${commonT.bullish}`
    : score <= 25
    ? `🔴 ${commonT.bearish}`
    : `⚖️ ${commonT.neutral}`;

/* ========================================================
   MAIN HOOK
======================================================== */
export function useMarketData(symbol = "BTC", options = {}) {
  const { t } = useTranslation();
  const commonT = t?.common || {};
  const {
    includeExtendedData = true,
    mode = "full",
    includeSevenDayData,
    includeForwardData,
    includeDailyScores,
    includeMarketDayData,
    includeIndicators,
    timeframe = "day",
  } = options;
  const [sevenDayData, setSevenDayData] = useState([]);
  const [btcLive, setBtcLive] = useState(null);

  const [forwardReturns, setForwardReturns] = useState({
    week: [],
    month: [],
    quarter: [],
    year: [],
  });

  const [marketScore, setMarketScore] = useState("N/A");
  const [advies, setAdviesState] = useState(() => getAdvies(50, commonT));

  const [marketDayData, setMarketDayData] = useState([]);
  const [activeMarketIndicators, setActiveMarketIndicators] = useState([]);
  const normalizedSymbol = useMemo(() => String(symbol || "BTC").toUpperCase(), [symbol]);
  const [preferences, setPreferences] = useState({
    scope: "default",
    symbol: normalizedSymbol,
    assetClass: null,
    indicators: [],
  });
  const [preferencesLoading, setPreferencesLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const autoSyncedRef = useRef(new Set());

  const activeMarketIndicatorNames = useMemo(
    () => (activeMarketIndicators || []).map((i) => i?.name).filter(Boolean),
    [activeMarketIndicators]
  );
  const configuredMarketIndicatorNames = Array.isArray(preferences.indicators)
    ? preferences.indicators.map((item) => item.indicator).filter(Boolean)
    : [];
  const assetClass = preferences.assetClass || null;

  const [availableIndicators, setAvailableIndicators] = useState([]);
  const [selectedIndicator, setSelectedIndicator] = useState(null);
  const [scoreRules, setScoreRules] = useState([]);

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const livePriceFetchingRef = useRef(false);

  const shouldLoadExtended = mode !== "live" && includeExtendedData !== false;
  const shouldLoadSevenDayData = includeSevenDayData ?? shouldLoadExtended;
  const shouldLoadForwardData = includeForwardData ?? shouldLoadExtended;
  const shouldLoadDailyScores = includeDailyScores ?? shouldLoadExtended;
  const shouldLoadMarketDayData = includeMarketDayData ?? shouldLoadExtended;
  const shouldLoadIndicators = includeIndicators ?? shouldLoadExtended;

  const unwrapSettled = (result, fallback) =>
    result?.status === "fulfilled" ? result.value : fallback;

  const loadPreferences = useCallback(async () => {
    setPreferencesLoading(true);
    try {
      const payload = await getMarketPreferences({ symbol: normalizedSymbol });
      setPreferences({
        scope: payload?.scope || "default",
        symbol: payload?.symbol || normalizedSymbol,
        assetClass: payload?.asset_class || null,
        indicators: Array.isArray(payload?.indicators) ? payload.indicators : [],
      });
      return payload;
    } catch (err) {
      console.error(`❌ Fout bij market preferences (${normalizedSymbol}):`, err);
      setPreferences({
        scope: "default",
        symbol: normalizedSymbol,
        assetClass: null,
        indicators: [],
      });
      return null;
    } finally {
      setPreferencesLoading(false);
    }
  }, [normalizedSymbol]);

  /* --------------------------------------------------------
     INIT
  -------------------------------------------------------- */
  useEffect(() => {
    loadAll();
  }, [normalizedSymbol, timeframe]);

  useEffect(() => {
    loadPreferences();
  }, [loadPreferences]);

  useVisibilityPolling(loadLivePrice, {
    intervalMs: 60000,
    backgroundIntervalMs: 300000,
    runImmediately: false,
    deps: [normalizedSymbol],
  });

  /* --------------------------------------------------------
     LOAD ALLES
  -------------------------------------------------------- */
  const loadAll = useCallback(async () => {
    setLoading(true);
    setError("");

    try {
      // Laat de live prijs niet de rest van de overview blokkeren.
      void loadLivePrice({ forceFresh: false });

      if (!shouldLoadExtended) {
        setLoading(false);
        return;
      }

      const normalizedTimeframe = String(timeframe || "day").toLowerCase();
      const marketPeriodRequest = {
        day: fetchMarketDayData,
        week: fetchMarketWeekData,
        month: fetchMarketMonthData,
        quarter: fetchMarketQuarterData,
      }[normalizedTimeframe] || fetchMarketDayData;

      const settledResults = await Promise.allSettled([
        shouldLoadSevenDayData ? fetchMarketData7d(normalizedSymbol) : Promise.resolve(null),
        shouldLoadForwardData ? fetchForwardReturnsWeek(normalizedSymbol) : Promise.resolve(null),
        shouldLoadForwardData ? fetchForwardReturnsMonth(normalizedSymbol) : Promise.resolve(null),
        shouldLoadForwardData ? fetchForwardReturnsQuarter(normalizedSymbol) : Promise.resolve(null),
        shouldLoadForwardData ? fetchForwardReturnsYear(normalizedSymbol) : Promise.resolve(null),
        shouldLoadDailyScores ? getDailyScores(normalizedSymbol) : Promise.resolve(null),
        shouldLoadMarketDayData ? marketPeriodRequest(normalizedSymbol) : Promise.resolve(null),
        shouldLoadIndicators ? getUserMarketIndicators(normalizedSymbol) : Promise.resolve(null),
        shouldLoadIndicators ? loadMarketIndicatorNamesShared() : Promise.resolve(null),
      ]);

      const [
        sevenDayResult,
        forwardWeekResult,
        forwardMonthResult,
        forwardQuarterResult,
        forwardYearResult,
        dailyScoresResult,
        marketDayResult,
        activeIndicatorsResult,
        indicatorNamesResult,
      ] = settledResults;

      if (shouldLoadSevenDayData) {
        setSevenDayData(unwrapSettled(sevenDayResult, []));
      } else {
        setSevenDayData([]);
      }

      if (shouldLoadForwardData) {
        setForwardReturns({
          week: unwrapSettled(forwardWeekResult, []),
          month: unwrapSettled(forwardMonthResult, []),
          quarter: unwrapSettled(forwardQuarterResult, []),
          year: unwrapSettled(forwardYearResult, []),
        });
      } else {
        setForwardReturns({
          week: [],
          month: [],
          quarter: [],
          year: [],
        });
      }

      if (shouldLoadDailyScores) {
        const dailyScores = unwrapSettled(dailyScoresResult, null);
        const rawScore = dailyScores?.market?.score;
        const score = Number.isFinite(Number(rawScore)) ? Number(rawScore) : null;
        setMarketScore(score);
        setAdviesState(score === null ? null : getAdvies(score, commonT));
      }

      if (shouldLoadMarketDayData) {
        setMarketDayData(unwrapSettled(marketDayResult, []) || []);
      } else {
        setMarketDayData([]);
      }

      if (shouldLoadIndicators) {
        setActiveMarketIndicators(unwrapSettled(activeIndicatorsResult, []) || []);
        setAvailableIndicators(unwrapSettled(indicatorNamesResult, []) || []);
      } else {
        setActiveMarketIndicators([]);
        setAvailableIndicators([]);
      }

      const failedResults = settledResults.filter((result, idx) => {
        if (result.status !== "rejected") return false;
        const enabledFlags = [
          shouldLoadSevenDayData,
          shouldLoadForwardData,
          shouldLoadForwardData,
          shouldLoadForwardData,
          shouldLoadForwardData,
          shouldLoadDailyScores,
          shouldLoadMarketDayData,
          shouldLoadIndicators,
          shouldLoadIndicators,
        ];
        return enabledFlags[idx];
      });

      if (failedResults.length > 0) {
        console.warn(`⚠️ loadAll partial failures (${normalizedSymbol}):`, failedResults);
        setError(t?.pages?.market?.partialLoadError);
      }
    } catch (err) {
      console.error(`❌ loadAll error (${normalizedSymbol}):`, err);
      setError(t?.pages?.market?.loadError);
    } finally {
      setLoading(false);
    }
  }, [
    commonT,
    normalizedSymbol,
    shouldLoadDailyScores,
    shouldLoadExtended,
    shouldLoadForwardData,
    shouldLoadIndicators,
    shouldLoadMarketDayData,
    shouldLoadSevenDayData,
    t?.pages?.market?.loadError,
    t?.pages?.market?.partialLoadError,
    timeframe,
  ]);

  useEffect(() => {
    const hasConfiguredIndicators = configuredMarketIndicatorNames.length > 0;
    const hasLoadedSignals = activeMarketIndicatorNames.length > 0;
    const syncKey = `${normalizedSymbol}:${preferences.scope}:${configuredMarketIndicatorNames.join(",")}`;
    if (!hasConfiguredIndicators || hasLoadedSignals) return;
    if (preferencesLoading || loading || syncing) return;
    if (autoSyncedRef.current.has(syncKey)) return;

    autoSyncedRef.current.add(syncKey);
    setSyncing(true);
    syncMarketPreferences(normalizedSymbol)
      .then(() => loadAll())
      .catch((err) => {
        console.error(`❌ Fout bij market auto-sync (${normalizedSymbol}):`, err);
      })
      .finally(() => setSyncing(false));
  }, [
    activeMarketIndicatorNames.length,
    configuredMarketIndicatorNames,
    loadAll,
    loading,
    normalizedSymbol,
    preferences.scope,
    preferencesLoading,
    syncing,
  ]);

  /* --------------------------------------------------------
     SYNC HISTORY
  -------------------------------------------------------- */
  async function syncHistory(targetSymbol = symbol) {
    setLoading(true);
    try {
      await syncMarketData7d(targetSymbol, true);
      await loadAll();
    } catch (err) {
      console.error(`❌ syncHistory error (${targetSymbol}):`, err);
      setError(t?.pages?.market?.syncHistoryError);
    } finally {
      setLoading(false);
    }
  }

  /* --------------------------------------------------------
     LIVE PRICE
  -------------------------------------------------------- */
  async function loadLivePrice(options = { forceFresh: true }) {
    if (livePriceFetchingRef.current) return;
    livePriceFetchingRef.current = true;
    try {
      setBtcLive(await fetchLatestPrice(normalizedSymbol, options));
    } catch {
      setBtcLive(null);
    } finally {
      livePriceFetchingRef.current = false;
    }
  }

  /* --------------------------------------------------------
     SCORE RULES
  -------------------------------------------------------- */
  async function selectIndicator(indicatorObj) {
    if (!indicatorObj?.name) return;

    setSelectedIndicator(indicatorObj);
    try {
      const rules = await getScoreRulesForMarketIndicator(indicatorObj.name);
      setScoreRules(rules || []);
    } catch (e) {
      console.error("❌ score rules error:", e);
      setScoreRules([]);
    }
  }

  /* --------------------------------------------------------
     REFRESH HELPERS
  -------------------------------------------------------- */
  async function refreshDay() {
    setMarketDayData((await fetchMarketDayData(normalizedSymbol)) || []);
  }

  async function refreshActive() {
    setActiveMarketIndicators((await getUserMarketIndicators(normalizedSymbol)) || []);
  }

  /* --------------------------------------------------------
     ➕ ADD
  -------------------------------------------------------- */
  async function addMarket(indicatorName) {
    if (!indicatorName) return;

    if (activeMarketIndicatorNames.includes(indicatorName)) {
      // UI doet snackbar
      return;
    }

    await marketIndicatorAdd(indicatorName, normalizedSymbol);
    await loadPreferences();

    // refresh
    await refreshActive();
    await refreshDay();
  }

  /* --------------------------------------------------------
     ❌ REMOVE (zoals macro: GEEN MODAL HIER)
     - doet echt delete
     - update state direct (optimistic) + refresh
  -------------------------------------------------------- */
  async function removeMarket(indicatorName) {
    if (!indicatorName) return;

    const normalized = String(indicatorName).trim().toLowerCase();

    // 1) API delete
    await marketIndicatorDelete(normalized, normalizedSymbol);
    await loadPreferences();

    // 2) Optimistic state update (direct uit UI halen)
    setMarketDayData((prev) =>
      (prev || []).filter(
        (r) => String(r?.name || "").trim().toLowerCase() !== normalized
      )
    );

    setActiveMarketIndicators((prev) =>
      (prev || []).filter(
        (r) => String(r?.name || "").trim().toLowerCase() !== normalized
      )
    );

    // 3) Hard refresh (zekerheid)
    await refreshActive();
    await refreshDay();
  }

  async function applyRecommendedPreset(scope = "asset_class") {
    const effectiveScope = scope === "default" ? "default" : scope === "symbol" ? "symbol" : "asset_class";
    setSyncing(true);
    try {
      await bootstrapMarketPreferences({
        symbol: normalizedSymbol,
        assetClass,
        scope: effectiveScope,
      });
      await loadPreferences();
      await syncMarketPreferences(normalizedSymbol);
      await loadAll();
    } finally {
      setSyncing(false);
    }
  }

  return {
    loading,
    error,

    btcLive,
    marketScore,
    advies,

    sevenDayData,
    forwardReturns,

    marketDayData,

    activeMarketIndicators,
    activeMarketIndicatorNames,
    configuredMarketIndicatorNames,
    preferences,
    preferencesLoading,
    syncing,
    assetClass,

    addMarket,
    removeMarket,
    applyRecommendedPreset,
    syncHistory,
    reload: loadAll,

    availableIndicators,
    selectedIndicator,
    scoreRules,
    selectIndicator,
  };
}
