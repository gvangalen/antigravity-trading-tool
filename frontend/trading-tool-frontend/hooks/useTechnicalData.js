"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "@/app/providers/I18nProvider";

import {
  technicalDataDay,
  technicalDataWeek,
  technicalDataMonth,
  technicalDataQuarter,
  getIndicatorNames,
  getScoreRulesForIndicator,
  technicalDataAdd,
  deleteTechnicalIndicator,
  getTechnicalPreferences,
  bootstrapTechnicalPreferences,
  syncTechnicalPreferences,
} from "@/lib/api/technical";

import { getDailyScores } from "@/lib/api/scores";

const TECHNICAL_INDICATOR_NAMES_CACHE_TTL_MS = 5 * 60 * 1000;
let technicalIndicatorNamesCache = [];
let technicalIndicatorNamesCacheUpdatedAt = 0;
let technicalIndicatorNamesInFlightPromise = null;

function hasFreshTechnicalIndicatorNamesCache() {
  return Date.now() - technicalIndicatorNamesCacheUpdatedAt < TECHNICAL_INDICATOR_NAMES_CACHE_TTL_MS;
}

async function loadTechnicalIndicatorNamesShared(forceFresh = false) {
  if (!forceFresh && hasFreshTechnicalIndicatorNamesCache()) {
    return technicalIndicatorNamesCache;
  }

  if (!technicalIndicatorNamesInFlightPromise) {
    technicalIndicatorNamesInFlightPromise = getIndicatorNames()
      .then((list) => {
        technicalIndicatorNamesCache = Array.isArray(list) ? list : [];
        technicalIndicatorNamesCacheUpdatedAt = Date.now();
        return technicalIndicatorNamesCache;
      })
      .finally(() => {
        technicalIndicatorNamesInFlightPromise = null;
      });
  }

  return technicalIndicatorNamesInFlightPromise;
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
   MAIN HOOK — TECHNICAL (CONSISTENT MET MARKET & MACRO)
======================================================== */
export function useTechnicalData(activeTab = "day", symbol = "BTC", options = {}) {
  const { t } = useTranslation();
  const commonT = t?.common || {};
  const { includeScoreSummary = true } = options;
  const normalizedSymbol = useMemo(() => String(symbol || "BTC").toUpperCase(), [symbol]);
  const [technicalData, setTechnicalData] = useState([]);
  const [avgScore, setAvgScore] = useState("N/A");
  const [advies, setAdvies] = useState(() => getAdvies(50, commonT));
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [preferences, setPreferences] = useState({
    scope: "default",
    symbol: normalizedSymbol,
    assetClass: null,
    indicators: [],
  });
  const [preferencesLoading, setPreferencesLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const autoSyncedRef = useRef(new Set());

  const [indicatorNames, setIndicatorNames] = useState(() => (
    hasFreshTechnicalIndicatorNamesCache() ? technicalIndicatorNamesCache : []
  ));
  const [scoreRules, setScoreRules] = useState([]);

  /* --------------------------------------------------------
     🔹 Afgeleide helpers (BELANGRIJK)
  -------------------------------------------------------- */
  const activeTechnicalIndicatorNames = Array.isArray(technicalData)
    ? technicalData.map((i) => i.name)
    : [];
  const configuredTechnicalIndicatorNames = Array.isArray(preferences.indicators)
    ? preferences.indicators.map((item) => item.indicator).filter(Boolean)
    : [];
  const assetClass = preferences.assetClass || null;

  const loadPreferences = useCallback(async () => {
    setPreferencesLoading(true);
    try {
      const payload = await getTechnicalPreferences({ symbol: normalizedSymbol });
      setPreferences({
        scope: payload?.scope || "default",
        symbol: payload?.symbol || normalizedSymbol,
        assetClass: payload?.asset_class || null,
        indicators: Array.isArray(payload?.indicators) ? payload.indicators : [],
      });
      return payload;
    } catch (err) {
      console.error(`❌ Fout bij technical preferences (${normalizedSymbol}):`, err);
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

  /* ======================================================
     LADEN VAN TECHNICAL DATA
  ====================================================== */
  const loadData = useCallback(async () => {
    setLoading(true);
    setError("");

    try {
      let raw;

      const tab = activeTab.toLowerCase();

      if (tab === "dag" || tab === "day") raw = await technicalDataDay(normalizedSymbol);
      else if (tab === "week") raw = await technicalDataWeek(normalizedSymbol);
      else if (tab === "maand" || tab === "month") raw = await technicalDataMonth(normalizedSymbol);
      else if (tab === "kwartaal" || tab === "quarter") raw = await technicalDataQuarter(normalizedSymbol);

      const dataList = Array.isArray(raw) ? raw : [];

      const normalized = dataList.map((item) => ({
        name: item.indicator ?? item.name ?? "–",
        value: item.waarde ?? item.value ?? "–",
        score: item.score ?? null,
        action: item.advies ?? item.action ?? "–",
        interpretation: item.uitleg ?? item.interpretation ?? "–",
        timestamp: item.timestamp
          ? new Date(item.timestamp)
          : item.date
          ? new Date(item.date)
          : null,
      }));

      setTechnicalData(normalized);

      /* --------------------------------------------------
         DAGELIJKSE TECHNICAL SCORE
      -------------------------------------------------- */
      if (includeScoreSummary) {
        const scores = await getDailyScores(normalizedSymbol);
        const backendScore = scores?.technical?.score ?? null;

        if (backendScore !== null) {
          const rounded = parseFloat(backendScore).toFixed(1);
          setAvgScore(rounded);
          setAdvies(getAdvies(backendScore, commonT));
        } else {
          updateScore(normalized);
        }
      } else {
        updateScore(normalized);
      }
    } catch (err) {
      console.error(`❌ Fout bij technical data (${normalizedSymbol}):`, err);
      setTechnicalData([]);
      setAvgScore("N/A");
      setAdvies(getAdvies(50, commonT));
      setError(t?.pages?.technical?.loadError);
    } finally {
      setLoading(false);
    }
  }, [activeTab, commonT, includeScoreSummary, normalizedSymbol, t?.pages?.technical?.loadError]);

  /* --------------------------------------------------------
     INIT
  -------------------------------------------------------- */
  useEffect(() => {
    loadData();
  }, [loadData]);

  useEffect(() => {
    loadIndicatorNames();
  }, []);

  useEffect(() => {
    loadPreferences();
  }, [loadPreferences]);

  useEffect(() => {
    const hasConfiguredIndicators = configuredTechnicalIndicatorNames.length > 0;
    const hasLoadedSignals = activeTechnicalIndicatorNames.length > 0;
    const syncKey = `${normalizedSymbol}:${preferences.scope}:${configuredTechnicalIndicatorNames.join(",")}`;

    if (!hasConfiguredIndicators || hasLoadedSignals) return;
    if (preferencesLoading || loading || syncing) return;
    if (autoSyncedRef.current.has(syncKey)) return;

    autoSyncedRef.current.add(syncKey);
    setSyncing(true);

    syncTechnicalPreferences(normalizedSymbol)
      .then(() => loadData())
      .catch((err) => {
        console.error(`❌ Fout bij technical auto-sync (${normalizedSymbol}):`, err);
      })
      .finally(() => {
        setSyncing(false);
      });
  }, [
    activeTechnicalIndicatorNames.length,
    configuredTechnicalIndicatorNames,
    loadData,
    loading,
    normalizedSymbol,
    preferences.scope,
    preferencesLoading,
    syncing,
  ]);

  /* ======================================================
     INDICATOR NAMEN
  ====================================================== */
  async function loadIndicatorNames() {
    try {
      const list = await loadTechnicalIndicatorNamesShared();
      setIndicatorNames(Array.isArray(list) ? list : []);
    } catch (err) {
      console.error("❌ Fout bij indicator-namen:", err);
    }
  }

  /* ======================================================
     SCOREREGELS
  ====================================================== */
  async function loadScoreRules(indicatorName) {
    if (!indicatorName) return;

    try {
      const rules = await getScoreRulesForIndicator(indicatorName);
      setScoreRules(Array.isArray(rules) ? rules : []);
    } catch (err) {
      console.error("❌ Fout bij scoreregels:", err);
    }
  }

  /* ======================================================
     ➕ INDICATOR TOEVOEGEN (DUPLICATE SAFE)
  ====================================================== */
  async function addTechnicalIndicator(indicatorName) {
    if (!indicatorName) return;

    // 🛑 Dubbele bescherming
    if (activeTechnicalIndicatorNames.includes(indicatorName)) {
      return;
    }

    await technicalDataAdd(indicatorName, normalizedSymbol);
    await loadPreferences();
    await loadData();
  }

  /* ======================================================
     ❌ INDICATOR VERWIJDEREN
  ====================================================== */
  async function removeTechnicalIndicator(indicatorName) {
    await deleteTechnicalIndicator(indicatorName, normalizedSymbol);
    await loadPreferences();
    await loadData();
  }

  async function applyRecommendedPreset(scope = "asset_class") {
    const effectiveScope = scope === "default" ? "default" : scope === "symbol" ? "symbol" : "asset_class";
    setSyncing(true);

    try {
      await bootstrapTechnicalPreferences({
        symbol: normalizedSymbol,
        assetClass,
        scope: effectiveScope,
      });
      await loadPreferences();
      await syncTechnicalPreferences(normalizedSymbol);
      await loadData();
    } finally {
      setSyncing(false);
    }
  }

  /* ======================================================
     FALLBACK SCORE BEREKENING
  ====================================================== */
  function updateScore(list) {
    const nums = list.map((i) => Number(i.score)).filter((v) => !isNaN(v));
    if (nums.length === 0) return;

    const avg = (nums.reduce((a, b) => a + b, 0) / nums.length).toFixed(1);
    setAvgScore(avg);
    setAdvies(getAdvies(avg, commonT));
  }

  /* ======================================================
     EXPORT
  ====================================================== */
  return {
    technicalData,
    avgScore,
    advies,
    loading,
    error,

    indicatorNames,
    scoreRules,
    loadScoreRules,

    addTechnicalIndicator,
    removeTechnicalIndicator,

    // 👇 ESSENTIEEL VOOR UI (zoals Market)
    activeTechnicalIndicatorNames,
    configuredTechnicalIndicatorNames,
    preferences,
    preferencesLoading,
    syncing,
    assetClass,
    applyRecommendedPreset,
    reload: loadData,
  };
}
