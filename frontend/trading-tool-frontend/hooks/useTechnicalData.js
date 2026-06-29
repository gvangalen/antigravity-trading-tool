"use client";

import { useEffect, useState } from "react";
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
} from "@/lib/api/technical";

import { getDailyScores } from "@/lib/api/scores";

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
  const [technicalData, setTechnicalData] = useState([]);
  const [avgScore, setAvgScore] = useState("N/A");
  const [advies, setAdvies] = useState(() => getAdvies(50, commonT));
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const [indicatorNames, setIndicatorNames] = useState([]);
  const [scoreRules, setScoreRules] = useState([]);

  /* --------------------------------------------------------
     🔹 Afgeleide helpers (BELANGRIJK)
  -------------------------------------------------------- */
  const activeTechnicalIndicatorNames = Array.isArray(technicalData)
    ? technicalData.map((i) => i.name)
    : [];

  /* --------------------------------------------------------
     INIT
  -------------------------------------------------------- */
  useEffect(() => {
    loadData();
    loadIndicatorNames();
  }, [activeTab, symbol]);

  /* ======================================================
     LADEN VAN TECHNICAL DATA
  ====================================================== */
  async function loadData() {
    setLoading(true);
    setError("");

    try {
      let raw;

      const tab = activeTab.toLowerCase();

      if (tab === "dag" || tab === "day") raw = await technicalDataDay(symbol);
      else if (tab === "week") raw = await technicalDataWeek(symbol);
      else if (tab === "maand" || tab === "month") raw = await technicalDataMonth(symbol);
      else if (tab === "kwartaal" || tab === "quarter") raw = await technicalDataQuarter(symbol);

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
        const scores = await getDailyScores(symbol);
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
      console.error(`❌ Fout bij technical data (${symbol}):`, err);
      setTechnicalData([]);
      setAvgScore("N/A");
      setAdvies(getAdvies(50, commonT));
      setError(t?.pages?.technical?.loadError);
    } finally {
      setLoading(false);
    }
  }

  /* ======================================================
     INDICATOR NAMEN
  ====================================================== */
  async function loadIndicatorNames() {
    try {
      const list = await getIndicatorNames();
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

    await technicalDataAdd(indicatorName, symbol);
    await loadData();
  }

  /* ======================================================
     ❌ INDICATOR VERWIJDEREN
  ====================================================== */
  async function removeTechnicalIndicator(indicatorName) {
    await deleteTechnicalIndicator(indicatorName, symbol);
    await loadData();
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
    reload: loadData,
  };
}
