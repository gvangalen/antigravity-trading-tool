"use client";

import { useEffect, useMemo, useState } from "react";

import {
  fetchMarketData7d,
  fetchLatestBTC,
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
export function useMarketData() {
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

  /* --------------------------------------------------------
     INIT
  -------------------------------------------------------- */
  useEffect(() => {
    loadAll();
    const interval = setInterval(loadLiveBTC, 60000);
    return () => clearInterval(interval);
  }, []);

  /* --------------------------------------------------------
     LOAD ALLES
  -------------------------------------------------------- */
  async function loadAll() {
    setLoading(true);
    setError("");

    try {
      setSevenDayData(await fetchMarketData7d());

      const [week, maand, kwartaal, jaar] = await Promise.all([
        fetchForwardReturnsWeek(),
        fetchForwardReturnsMonth(),
        fetchForwardReturnsQuarter(),
        fetchForwardReturnsYear(),
      ]);
      setForwardReturns({ week, maand, kwartaal, jaar });

      const dailyScores = await getDailyScores();
      const score = dailyScores?.market?.score ?? 50;
      setMarketScore(score);
      setAdviesState(getAdvies(score));

      setMarketDayData((await fetchMarketDayData()) || []);
      setActiveMarketIndicators((await getUserMarketIndicators()) || []);
      setAvailableIndicators((await getMarketIndicatorNames()) || []);
    } catch (err) {
      console.error("❌ loadAll error:", err);
      setError("Kon market data niet laden.");
    } finally {
      setLoading(false);
    }
  }

  /* --------------------------------------------------------
     LIVE BTC
  -------------------------------------------------------- */
  async function loadLiveBTC() {
    try {
      setBtcLive(await fetchLatestBTC());
    } catch {
      setBtcLive(null);
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
    setMarketDayData((await fetchMarketDayData()) || []);
  }

  async function refreshActive() {
    setActiveMarketIndicators((await getUserMarketIndicators()) || []);
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

    await marketIndicatorAdd(indicatorName);

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
    await marketIndicatorDelete(normalized);

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

    availableIndicators,
    selectedIndicator,
    scoreRules,
    selectIndicator,
  };
}
