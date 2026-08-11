'use client';

import { useEffect, useState } from 'react';
import { getDailyScores, getAiMasterScore, getScoreHistory, updateIntelligenceWeights } from '@/lib/api/scores';
import { useTranslation } from "@/app/providers/I18nProvider";
import {
  fetchCachedResource,
  getCachedResourceSnapshot,
  markCachedResourceStale,
  subscribeCachedResource,
} from "@/lib/clientDataCache";

const SCORE_CACHE_TTL_MS = 30_000;
const scoreCache = new Map();
const inflightScoreRequests = new Map();
const DEFAULT_CONTEXT_WEIGHTS = {
  macro: 1 / 3,
  market: 1 / 3,
  technical: 1 / 3,
};

const normalizeContextWeights = (weights) => {
  const next = Object.fromEntries(
    Object.keys(DEFAULT_CONTEXT_WEIGHTS).map((key) => {
      const value = Number(weights?.[key]);
      return [key, Number.isFinite(value) && value >= 0 ? value : DEFAULT_CONTEXT_WEIGHTS[key]];
    })
  );
  const total = Object.values(next).reduce((sum, value) => sum + value, 0);
  if (!total) return { ...DEFAULT_CONTEXT_WEIGHTS };
  return Object.fromEntries(Object.entries(next).map(([key, value]) => [key, value / total]));
};

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
      weights: { ...DEFAULT_CONTEXT_WEIGHTS }
    },
    history: []
  });

  const [loading, setLoading] = useState(true);
  const [hasData, setHasData] = useState(false);
  const [error, setError] = useState(null);

  const cacheKey = `${symbol}:history:${includeHistory ? "1" : "0"}:master:${includeMaster ? "1" : "0"}:fallback:${fallbackOnError ? "1" : "0"}:locale:${String(locale || "nl").toLowerCase()}`;
  const resourceKey = `scores:${cacheKey}`;

  async function loadScores(forceRefresh = false) {
    return fetchCachedResource(resourceKey, {
      ttlMs: SCORE_CACHE_TTL_MS,
      forceFresh: forceRefresh,
      initialData: null,
      keepStaleOnError: true,
      fetcher: async () => {
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

      const toFiniteScore = (...values) => {
        for (const value of values) {
          if (value === null || value === undefined || value === '') continue;
          const parsed = Number(value);
          if (Number.isFinite(parsed)) return Math.max(0, Math.min(100, parsed));
        }
        return null;
      };

      const macroScore = toFiniteScore(daily.macro?.score, mData.score);
      const technicalScore = toFiniteScore(daily.technical?.score, tData.score);
      const marketScore = toFiniteScore(daily.market?.score, mkData.score);
      const setupScore = toFiniteScore(daily.setup?.score, sData.score);

      const weights = normalizeContextWeights(master?.weights);
      const hasCompleteContext = [macroScore, technicalScore, marketScore].every(Number.isFinite);
      const calculatedMasterScore = hasCompleteContext
        ? Math.round(
            macroScore * weights.macro +
            technicalScore * weights.technical +
            marketScore * weights.market
          )
        : null;

      const nextScores = {
        macro: {
          score: macroScore,
          trend: mData.trend ?? 'Stable',
          bias: mData.bias ?? daily.macro?.advies ?? gaugesT.macro,
          risk: mData.risk ?? 'Low',
          uitleg: daily.macro?.interpretation ?? gaugesT.emptyState?.macro,
          advies: macroScore === null ? gaugesT.insufficientData : getAdvies(macroScore),
          top_contributors: normalizeArray(daily.macro?.top_contributors),
        },
        technical: {
          score: technicalScore,
          trend: tData.trend ?? 'Stable',
          bias: tData.bias ?? daily.technical?.advies ?? gaugesT.technical,
          risk: tData.risk ?? 'Low',
          uitleg: daily.technical?.interpretation ?? gaugesT.emptyState?.technical,
          advies: technicalScore === null ? gaugesT.insufficientData : getAdvies(technicalScore),
          top_contributors: normalizeArray(daily.technical?.top_contributors),
        },
        market: {
          score: marketScore,
          trend: mkData.trend ?? 'Stable',
          bias: mkData.bias ?? daily.market?.advies ?? gaugesT.market,
          risk: mkData.risk ?? 'Low',
          uitleg: daily.market?.interpretation ?? gaugesT.emptyState?.market,
          advies: marketScore === null ? gaugesT.insufficientData : getAdvies(marketScore),
          top_contributors: normalizeArray(daily.market?.top_contributors),
        },
        setup: {
          score: setupScore,
          trend: sData.trend ?? 'Stable',
          bias: sData.bias ?? daily.setup?.advies ?? gaugesT.setup,
          risk: sData.risk ?? 'Low',
          uitleg: daily.setup?.interpretation ?? gaugesT.emptyState?.setup,
          advies: setupScore === null ? gaugesT.insufficientData : getAdvies(setupScore),
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

      return nextScores;
      },
    });
  }

  async function fetchScores(forceRefresh = false) {
    const snapshot = getCachedResourceSnapshot(resourceKey, null);
    if (!snapshot.hasData) {
      setLoading(true);
    }
    setError(null);
    try {
      const nextScores = await loadScores(forceRefresh);
      if (nextScores) {
        setScores(nextScores);
        setHasData(true);
      } else {
        setHasData(snapshot.hasData);
      }
    } catch (loadError) {
      setHasData(snapshot.hasData);
      setError(loadError);
    } finally {
      setLoading(false);
    }
  }

  const saveWeights = async (newWeights) => {
    setLoading(true);
    await updateIntelligenceWeights(newWeights);
    markCachedResourceStale(resourceKey);
    await fetchScores(true);
  };

  useEffect(() => {
    const unsubscribe = subscribeCachedResource(resourceKey, () => {
      const snapshot = getCachedResourceSnapshot(resourceKey, null);
      if (snapshot.data) {
        setScores(snapshot.data);
        setHasData(true);
      }
    });
    fetchScores();
    return unsubscribe;
  }, [locale, resourceKey, symbol]);

  return { ...scores, loading, hasData, error, saveWeights, refresh: fetchScores };
}
