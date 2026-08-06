"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  fetchMacroDataByDay,
  fetchMacroDataByWeek,
  fetchMacroDataByMonth,
  fetchMacroDataByQuarter,
  getMacroIndicatorNames,
  getScoreRulesForMacroIndicator,
  macroDataAdd,
  deleteMacroIndicator,
  getMacroPreferences,
  bootstrapMacroPreferences,
  syncMacroPreferences,
} from "@/lib/api/macro";

const MACRO_INDICATOR_NAMES_CACHE_TTL_MS = 5 * 60 * 1000;
let macroIndicatorNamesCache = [];
let macroIndicatorNamesCacheUpdatedAt = 0;
let macroIndicatorNamesInFlightPromise = null;

function hasFreshMacroIndicatorNamesCache() {
  return Date.now() - macroIndicatorNamesCacheUpdatedAt < MACRO_INDICATOR_NAMES_CACHE_TTL_MS;
}

async function loadMacroIndicatorNamesShared(forceFresh = false) {
  if (!forceFresh && hasFreshMacroIndicatorNamesCache()) {
    return macroIndicatorNamesCache;
  }

  if (!macroIndicatorNamesInFlightPromise) {
    macroIndicatorNamesInFlightPromise = getMacroIndicatorNames()
      .then((list) => {
        macroIndicatorNamesCache = Array.isArray(list) ? list : [];
        macroIndicatorNamesCacheUpdatedAt = Date.now();
        return macroIndicatorNamesCache;
      })
      .finally(() => {
        macroIndicatorNamesInFlightPromise = null;
      });
  }

  return macroIndicatorNamesInFlightPromise;
}

/* ============================================================
   ⭐ OFFICIËLE MACRO HOOK — ACTION-DRIVEN (FIXED)
   - Volledig in lijn met Technical & Market
   - action = advies (single source of truth)
============================================================ */
export function useMacroData(activeTab = "Dag", symbol = "BTC") {
  /* ------------------------------------------------------------
     STATE
  ------------------------------------------------------------ */
  const [macroData, setMacroData] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const [indicatorNames, setIndicatorNames] = useState(() => (
    hasFreshMacroIndicatorNamesCache() ? macroIndicatorNamesCache : []
  ));
  const [scoreRules, setScoreRules] = useState([]);
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

  /* ------------------------------------------------------------
     🔑 Helpers
  ------------------------------------------------------------ */
  const activeMacroIndicatorNames = macroData.map((m) => m.name);
  const configuredMacroIndicatorNames = Array.isArray(preferences.indicators)
    ? preferences.indicators.map((item) => item.indicator).filter(Boolean)
    : [];
  const assetClass = preferences.assetClass || null;

  const loadPreferences = useCallback(async () => {
    setPreferencesLoading(true);
    try {
      const payload = await getMacroPreferences({ symbol: normalizedSymbol });
      setPreferences({
        scope: payload?.scope || "default",
        symbol: payload?.symbol || normalizedSymbol,
        assetClass: payload?.asset_class || null,
        indicators: Array.isArray(payload?.indicators) ? payload.indicators : [],
      });
      return payload;
    } catch (err) {
      console.error(`❌ Fout bij macro preferences (${normalizedSymbol}):`, err);
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

  /* ------------------------------------------------------------
     📌 1. Indicatornamen laden
  ------------------------------------------------------------ */
  useEffect(() => {
    async function loadIndicators() {
      try {
        const list = await loadMacroIndicatorNamesShared();
        setIndicatorNames(Array.isArray(list) ? list : []);
      } catch (err) {
        console.error("❌ Fout bij ophalen macro indicatornamen:", err);
      }
    }
    loadIndicators();
  }, []);

  /* ------------------------------------------------------------
     📌 2. Macrodata laden per tab
  ------------------------------------------------------------ */
  useEffect(() => {
    loadPreferences();
  }, [loadPreferences]);

  useEffect(() => {
    loadData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeTab, normalizedSymbol]);

  useEffect(() => {
    const hasConfiguredIndicators = configuredMacroIndicatorNames.length > 0;
    const hasLoadedSignals = activeMacroIndicatorNames.length > 0;
    const syncKey = `${normalizedSymbol}:${preferences.scope}:${configuredMacroIndicatorNames.join(",")}`;
    if (!hasConfiguredIndicators || hasLoadedSignals) return;
    if (preferencesLoading || loading || syncing) return;
    if (autoSyncedRef.current.has(syncKey)) return;

    autoSyncedRef.current.add(syncKey);
    setSyncing(true);
    syncMacroPreferences(normalizedSymbol)
      .then(() => loadData({ preserveExisting: true }))
      .catch((err) => {
        console.error(`❌ Fout bij macro auto-sync (${normalizedSymbol}):`, err);
      })
      .finally(() => setSyncing(false));
  }, [
    activeMacroIndicatorNames.length,
    configuredMacroIndicatorNames,
    loading,
    normalizedSymbol,
    preferences.scope,
    preferencesLoading,
    syncing,
  ]);

  async function loadData(options = {}) {
    const { preserveExisting = false } = options;
    setLoading(true);
    setError("");

    try {
      let raw;
      const normalizedTab = String(activeTab || "day").toLowerCase();

      switch (normalizedTab) {
        case "dag":
        case "day":
          raw = await fetchMacroDataByDay(normalizedSymbol);
          break;
        case "week":
          raw = await fetchMacroDataByWeek(normalizedSymbol);
          break;
        case "maand":
        case "month":
          raw = await fetchMacroDataByMonth(normalizedSymbol);
          break;
        case "kwartaal":
        case "quarter":
          raw = await fetchMacroDataByQuarter(normalizedSymbol);
          break;
        default:
          raw = await fetchMacroDataByDay(normalizedSymbol);
      }

      if (!Array.isArray(raw)) {
        throw new Error("Macrodata is geen array");
      }

      // ✅ DEFINITIEVE NORMALISATIE
      const normalized = raw.map((item) => ({
        name: item.name || item.indicator || "–",
        value: item.value ?? item.waarde ?? null,
        score: item.score ?? null,
        trend: item.trend ?? null,
        interpretation: item.interpretation ?? item.uitleg ?? null,

        // 🔥 DE FIX: action = advies (ENIGE JUISTE VELD)
        action: item.action ?? null,

        timestamp: item.timestamp ?? null,
      }));

      setMacroData(normalized);
      return true;
    } catch (err) {
      console.error("❌ Macrodata load error:", err);
      if (!preserveExisting) {
        setMacroData([]);
      }
      setError("Fout bij laden van macrodata");
      return false;
    } finally {
      setLoading(false);
    }
  }

  /* ------------------------------------------------------------
     📌 3. Scoreregels ophalen (read-only)
  ------------------------------------------------------------ */
  async function loadScoreRules(indicator) {
    if (!indicator) return;

    try {
      const rules = await getScoreRulesForMacroIndicator(indicator);
      setScoreRules(Array.isArray(rules) ? rules : []);
    } catch (err) {
      console.error("❌ Fout bij macro scoreregels:", err);
    }
  }

  /* ------------------------------------------------------------
     ➕ 4. Macro-indicator toevoegen (duplicate-safe)
  ------------------------------------------------------------ */
  async function addMacroIndicator(name) {
    if (!name) {
      return { ok: false, reason: "missing_name" };
    }

    if (activeMacroIndicatorNames.includes(name)) {
      return { ok: true, duplicate: true, refreshed: true };
    }

    try {
      await macroDataAdd(name, normalizedSymbol);
      await loadPreferences();
      const refreshed = await loadData({ preserveExisting: true });

      if (!refreshed) {
        setMacroData((prev) => {
          if (prev.some((item) => item.name === name)) {
            return prev;
          }

          return [
            ...prev,
            {
              name,
              value: null,
              score: null,
              trend: null,
              interpretation: null,
              action: null,
              timestamp: null,
            },
          ];
        });
      }

      return { ok: true, duplicate: false, refreshed };
    } catch (err) {
      console.error("❌ Fout bij toevoegen macro-indicator:", err);

      if (err?.status === 409) {
        return { ok: true, duplicate: true, refreshed: true };
      }

      return { ok: false, reason: "request_failed", error: err };
    }
  }

  /* ------------------------------------------------------------
     🗑️ 5. Macro-indicator verwijderen
  ------------------------------------------------------------ */
  async function removeMacroIndicator(name) {
    if (!name || name === "–") {
      return { ok: false, reason: "missing_name" };
    }

    try {
      await deleteMacroIndicator(name, normalizedSymbol);
      await loadPreferences();
      setMacroData((prev) => prev.filter((m) => m.name !== name));
      return { ok: true };
    } catch (err) {
      console.error("❌ Fout bij verwijderen macro-indicator:", err);
      return { ok: false, reason: "request_failed", error: err };
    }
  }

  async function applyRecommendedPreset(scope = "asset_class") {
    const effectiveScope = scope === "default" ? "default" : scope === "symbol" ? "symbol" : "asset_class";
    setSyncing(true);
    try {
      await bootstrapMacroPreferences({
        symbol: normalizedSymbol,
        assetClass,
        scope: effectiveScope,
      });
      await loadPreferences();
      await syncMacroPreferences(normalizedSymbol);
      await loadData({ preserveExisting: true });
    } finally {
      setSyncing(false);
    }
  }

  /* ------------------------------------------------------------
     🔄 EXPORT
  ------------------------------------------------------------ */
  return {
    macroData,
    loading,
    error,

    indicatorNames,
    scoreRules,
    loadScoreRules,

    addMacroIndicator,
    removeMacroIndicator,

    activeMacroIndicatorNames,
    configuredMacroIndicatorNames,
    preferences,
    preferencesLoading,
    syncing,
    assetClass,
    applyRecommendedPreset,
    reload: loadData,
  };
}
