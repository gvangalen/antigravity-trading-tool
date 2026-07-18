'use client';

import { useEffect, useState } from 'react';
import { getDailyScores, getAiMasterScore, getScoreHistory, updateIntelligenceWeights } from '@/lib/api/scores';
import { useTranslation } from "@/app/providers/I18nProvider";

const SCORE_CACHE_TTL_MS = 30_000;
const scoreCache = new Map();
const inflightScoreRequests = new Map();

// Zorg dat altijd een array terugkomt
const normalizeArray = (v) => {
  if (!v) return [];
  if (Array.isArray(v)) return v;
  try { return JSON.parse(v); } catch { return []; }
};

export function useScoresData(symbol = "BTC", options = {}) {
  const { t, locale } = useTranslation();
  const { includeHistory = true, includeMaster = true, fallbackOnError = true } = options;
  const gaugesT = t?.dashboard?.gauges || {};
  const commonT = t?.common || {};
  const adviceMap = {
    bullish: `📈 ${commonT.bullish}`,
    bearish: `📉 ${commonT.bearish}`,
    neutral: `⚖️ ${commonT.neutral}`,
  };
  const getAdvies = (score) =>
    score >= 75 ? adviceMap.bullish :
    score <= 25 ? adviceMap.bearish :
    adviceMap.neutral;
  const [scores, setScores] = useState({
    macro: { score: 0, uitleg: '', advies: adviceMap.neutral, top_contributors: [] },
    technical: { score: 0, uitleg: '', advies: adviceMap.neutral, top_contributors: [] },
    market: { score: 0, uitleg: '', advies: adviceMap.neutral, top_contributors: [] },
    setup: { score: 0, uitleg: '', advies: adviceMap.neutral, top_contributors: [] },
    master: { 
      score: 0, trend: '–', bias: '–', risk: '–', outlook: '–', summary: t?.dashboard?.brain?.noSpecificSignals,
      weights: { macro: 0.25, market: 0.25, technical: 0.25, setup: 0.25 }
    },
    history: []
  });

  const [loading, setLoading] = useState(true);
  const [hasData, setHasData] = useState(false);
  const [error, setError] = useState(null);

  const cacheKey = `${symbol}:history:${includeHistory ? "1" : "0"}:master:${includeMaster ? "1" : "0"}:fallback:${fallbackOnError ? "1" : "0"}:locale:${String(locale || "nl").toLowerCase()}`;

  async function loadScores(forceRefresh = false) {
    const cached = scoreCache.get(cacheKey);
    const cacheIsFresh =
      cached && Date.now() - cached.timestamp < SCORE_CACHE_TTL_MS;

    if (!forceRefresh && cacheIsFresh) {
      return cached.data;
    }

    if (!forceRefresh && inflightScoreRequests.has(cacheKey)) {
      return inflightScoreRequests.get(cacheKey);
    }

    const request = (async () => {
      const [dailyRes, masterRes, historyRes] = await Promise.allSettled([
        getDailyScores(symbol, { fallbackOnError }),
        includeMaster ? getAiMasterScore(symbol) : Promise.resolve(null),
        includeHistory ? getScoreHistory(30, symbol) : Promise.resolve([])
      ]);

      const daily = dailyRes.status === 'fulfilled' ? dailyRes.value : null;
      const master = masterRes.status === 'fulfilled' ? masterRes.value : null;
      const history = historyRes.status === 'fulfilled' ? historyRes.value : [];

      if (!daily) {
        console.warn(`❌ Daily scores niet geladen voor ${symbol}`);
        return null;
      }

      const mData = master?.domains?.macro || {};
      const tData = master?.domains?.technical || {};
      const mkData = master?.domains?.market || {};
      const sData = master?.domains?.setup || {};

      const macroScore = daily.macro?.score ?? mData.score ?? 0;
      const technicalScore = daily.technical?.score ?? tData.score ?? 0;
      const marketScore = daily.market?.score ?? mkData.score ?? 0;
      const setupScore = daily.setup?.score ?? sData.score ?? 0;

      const weights = master?.weights || { macro: 0.25, market: 0.25, technical: 0.25, setup: 0.25 };
      const calculatedMasterScore = Math.round(
        macroScore * (weights.macro ?? 0.25) +
        technicalScore * (weights.technical ?? 0.25) +
        marketScore * (weights.market ?? 0.25) +
        setupScore * (weights.setup ?? 0.25)
      );

      const nextScores = {
        macro: {
          score: macroScore,
          trend: mData.trend ?? 'Stable',
          bias: mData.bias ?? daily.macro?.advies ?? gaugesT.macro,
          risk: mData.risk ?? 'Low',
          uitleg: daily.macro?.interpretation ?? gaugesT.emptyState?.macro,
          advies: getAdvies(macroScore),
          top_contributors: normalizeArray(daily.macro?.top_contributors),
        },
        technical: {
          score: technicalScore,
          trend: tData.trend ?? 'Stable',
          bias: tData.bias ?? daily.technical?.advies ?? gaugesT.technical,
          risk: tData.risk ?? 'Low',
          uitleg: daily.technical?.interpretation ?? gaugesT.emptyState?.technical,
          advies: getAdvies(technicalScore),
          top_contributors: normalizeArray(daily.technical?.top_contributors),
        },
        market: {
          score: marketScore,
          trend: mkData.trend ?? 'Stable',
          bias: mkData.bias ?? daily.market?.advies ?? gaugesT.market,
          risk: mkData.risk ?? 'Low',
          uitleg: daily.market?.interpretation ?? gaugesT.emptyState?.market,
          advies: getAdvies(marketScore),
          top_contributors: normalizeArray(daily.market?.top_contributors),
        },
        setup: {
          score: setupScore,
          trend: sData.trend ?? 'Stable',
          bias: sData.bias ?? daily.setup?.advies ?? gaugesT.setup,
          risk: sData.risk ?? 'Low',
          uitleg: daily.setup?.interpretation ?? gaugesT.emptyState?.setup,
          advies: getAdvies(setupScore),
          top_contributors: normalizeArray(daily.setup?.top_contributors),
        },
        master: {
          score: calculatedMasterScore,
          trend: master?.master_trend ?? '–',
          bias: master?.master_bias ?? '–',
          risk: master?.master_risk ?? '–',
          outlook: master?.outlook ?? t?.dashboard?.brain?.noSpecificSignals,
          summary: master?.summary ?? t?.dashboard?.brain?.master_snippet,
          weights
        },
        history
      };

      scoreCache.set(cacheKey, { data: nextScores, timestamp: Date.now() });
      return nextScores;
    })();

    inflightScoreRequests.set(cacheKey, request);

    try {
      return await request;
    } finally {
      inflightScoreRequests.delete(cacheKey);
    }
  }

  async function fetchScores(forceRefresh = false) {
    setLoading(true);
    setError(null);
    try {
      const nextScores = await loadScores(forceRefresh);
      if (nextScores) {
        setScores(nextScores);
        setHasData(true);
      } else {
        setHasData(false);
      }
    } catch (loadError) {
      setHasData(false);
      setError(loadError);
    } finally {
      setLoading(false);
    }
  }

  const saveWeights = async (newWeights) => {
    setLoading(true);
    await updateIntelligenceWeights(newWeights);
    scoreCache.delete(cacheKey);
    inflightScoreRequests.delete(cacheKey);
    await fetchScores(true);
  };

  useEffect(() => {
    fetchScores();
  }, [locale, symbol]);

  return { ...scores, loading, hasData, error, saveWeights, refresh: fetchScores };
}
