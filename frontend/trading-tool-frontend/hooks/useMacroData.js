"use client";

import { useEffect, useState } from "react";

import {
  fetchMacroDataByDay,
  fetchMacroDataByWeek,
  fetchMacroDataByMonth,
  fetchMacroDataByQuarter,
  getMacroIndicatorNames,
  getScoreRulesForMacroIndicator,
  macroDataAdd,
  deleteMacroIndicator,
} from "@/lib/api/macro";

/* ============================================================
   ⭐ OFFICIËLE MACRO HOOK — ACTION-DRIVEN (FIXED)
   - Volledig in lijn met Technical & Market
   - action = advies (single source of truth)
============================================================ */
export function useMacroData(activeTab = "Dag") {
  /* ------------------------------------------------------------
     STATE
  ------------------------------------------------------------ */
  const [macroData, setMacroData] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const [indicatorNames, setIndicatorNames] = useState([]);
  const [scoreRules, setScoreRules] = useState([]);

  /* ------------------------------------------------------------
     🔑 Helpers
  ------------------------------------------------------------ */
  const activeMacroIndicatorNames = macroData.map((m) => m.name);

  /* ------------------------------------------------------------
     📌 1. Indicatornamen laden
  ------------------------------------------------------------ */
  useEffect(() => {
    async function loadIndicators() {
      try {
        const list = await getMacroIndicatorNames();
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
    loadData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeTab]);

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
          raw = await fetchMacroDataByDay();
          break;
        case "week":
          raw = await fetchMacroDataByWeek();
          break;
        case "maand":
        case "month":
          raw = await fetchMacroDataByMonth();
          break;
        case "kwartaal":
        case "quarter":
          raw = await fetchMacroDataByQuarter();
          break;
        default:
          raw = await fetchMacroDataByDay();
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
      await macroDataAdd(name);
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
      await deleteMacroIndicator(name);
      setMacroData((prev) => prev.filter((m) => m.name !== name));
      return { ok: true };
    } catch (err) {
      console.error("❌ Fout bij verwijderen macro-indicator:", err);
      return { ok: false, reason: "request_failed", error: err };
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
    reload: loadData,
  };
}
