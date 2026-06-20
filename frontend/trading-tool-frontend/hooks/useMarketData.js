"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useVisibilityPolling } from "@/hooks/useVisibilityPolling";

import {
  fetchMarketData7d,
  fetchLatestPrice,
  fetchForwardReturnsWeek,
  fetchForwardReturnsMonth,
  fetchForwardReturnsQuarter,
  fetchForwardReturnsYear,
  fetchMarketDayData,
  getMarketIndicatorNames,
  getScoreRulesForMarketIndicator,
  marketIndicatorAdd,
  marketIndicatorDelete,
  getUserMarketIndicators,
} from "@/lib/api/market";

import { getDailyScores } from "@/lib/api/scores";

/* --------------------------------------------------------
   Advies logica
-------------------------------------------------------- */
const getAdvies = (score) =>
  score >= 75 ? "🟢 Bullish" : score <= 25 ? "🔴 Bearish" : "⚖️ Neutraal";

/* ========================================================
   MAIN HOOK
======================================================== */
export function useMarketData(symbol = "BTC", options = {}) {
  const {
    includeExtendedData = true,
    mode = "full",
    includeSevenDayData,
    includeForwardData,
    includeDailyScores,
    includeMarketDayData,
    includeIndicators,
  } = options;
  const [sevenDayData, setSevenDayData] = useState([]);
  const [btcLive, setBtcLive] = useState(null);

  const [forwardReturns, setForwardReturns] = useState({
    week: [],
    maand: [],
    kwartaal: [],
    jaar: [],
  });

  const [marketScore, setMarketScore] = useState("N/A");
  const [advies, setAdviesState] = useState("⚖️ Neutraal");

  const [marketDayData, setMarketDayData] = useState([]);
  const [activeMarketIndicators, setActiveMarketIndicators] = useState([]);

  const activeMarketIndicatorNames = useMemo(
    () => (activeMarketIndicators || []).map((i) => i?.name).filter(Boolean),
    [activeMarketIndicators]
  );

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

  /* --------------------------------------------------------
     INIT
  -------------------------------------------------------- */
  useEffect(() => {
    loadAll();
  }, [symbol]);

  useVisibilityPolling(loadLivePrice, {
    intervalMs: 60000,
    backgroundIntervalMs: 300000,
    runImmediately: false,
    deps: [symbol],
  });

  /* --------------------------------------------------------
     LOAD ALLES
  -------------------------------------------------------- */
  async function loadAll() {
    setLoading(true);
    setError("");

    try {
      // Laat de live prijs niet de rest van de overview blokkeren.
      void loadLivePrice({ forceFresh: false });

      if (!shouldLoadExtended) {
        setLoading(false);
        return;
      }

      const settledResults = await Promise.allSettled([
        shouldLoadSevenDayData ? fetchMarketData7d(symbol) : Promise.resolve(null),
        shouldLoadForwardData ? fetchForwardReturnsWeek(symbol) : Promise.resolve(null),
        shouldLoadForwardData ? fetchForwardReturnsMonth(symbol) : Promise.resolve(null),
        shouldLoadForwardData ? fetchForwardReturnsQuarter(symbol) : Promise.resolve(null),
        shouldLoadForwardData ? fetchForwardReturnsYear(symbol) : Promise.resolve(null),
        shouldLoadDailyScores ? getDailyScores(symbol) : Promise.resolve(null),
        shouldLoadMarketDayData ? fetchMarketDayData(symbol) : Promise.resolve(null),
        shouldLoadIndicators ? getUserMarketIndicators(symbol) : Promise.resolve(null),
        shouldLoadIndicators ? getMarketIndicatorNames() : Promise.resolve(null),
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
          maand: unwrapSettled(forwardMonthResult, []),
          kwartaal: unwrapSettled(forwardQuarterResult, []),
          jaar: unwrapSettled(forwardYearResult, []),
        });
      } else {
        setForwardReturns({
          week: [],
          maand: [],
          kwartaal: [],
          jaar: [],
        });
      }

      if (shouldLoadDailyScores) {
        const dailyScores = unwrapSettled(dailyScoresResult, null);
        const score = dailyScores?.market?.score ?? 50;
        setMarketScore(score);
        setAdviesState(getAdvies(score));
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
        console.warn(`⚠️ loadAll partial failures (${symbol}):`, failedResults);
        setError("Een deel van de market data kon niet direct geladen worden.");
      }
    } catch (err) {
      console.error(`❌ loadAll error (${symbol}):`, err);
      setError("Kon market data niet laden.");
    } finally {
      setLoading(false);
    }
  }

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
      setError("Kon history niet synchroniseren.");
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
      setBtcLive(await fetchLatestPrice(symbol, options));
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
    setMarketDayData((await fetchMarketDayData(symbol)) || []);
  }

  async function refreshActive() {
    setActiveMarketIndicators((await getUserMarketIndicators(symbol)) || []);
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

    await marketIndicatorAdd(indicatorName, symbol);

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
    await marketIndicatorDelete(normalized, symbol);

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

    addMarket,
    removeMarket,
    syncHistory,

    availableIndicators,
    selectedIndicator,
    scoreRules,
    selectIndicator,
  };
}
