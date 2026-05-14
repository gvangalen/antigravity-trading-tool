'use client';

import { useEffect, useState } from 'react';
import { getDailyScores, getAiMasterScore, getScoreHistory, updateIntelligenceWeights } from '@/lib/api/scores';

// Score → Advies
const getAdvies = (score) =>
  score >= 75 ? '📈 Bullish' :
  score <= 25 ? '📉 Bearish' :
  '⚖️ Neutraal';

// Zorg dat altijd een array terugkomt
const normalizeArray = (v) => {
  if (!v) return [];
  if (Array.isArray(v)) return v;
  try { return JSON.parse(v); } catch { return []; }
};

export function useScoresData(symbol = "BTC") {
  const [scores, setScores] = useState({
    macro: { score: 0, uitleg: '', advies: '⚖️ Neutraal', top_contributors: [] },
    technical: { score: 0, uitleg: '', advies: '⚖️ Neutraal', top_contributors: [] },
    market: { score: 0, uitleg: '', advies: '⚖️ Neutraal', top_contributors: [] },
    setup: { score: 0, uitleg: '', advies: '⚖️ Neutraal', top_contributors: [] },
    master: { 
      score: 0, trend: '–', bias: '–', risk: '–', outlook: '–', summary: 'Geen samenvatting beschikbaar',
      weights: { macro: 0.25, market: 0.25, technical: 0.25, setup: 0.25 }
    },
    history: []
  });

  const [loading, setLoading] = useState(true);

  async function fetchScores() {
    setLoading(true);
    const [dailyRes, masterRes, historyRes] = await Promise.allSettled([
      getDailyScores(symbol),
      getAiMasterScore(symbol),
      getScoreHistory(30, symbol)
    ]);

    const daily = dailyRes.status === 'fulfilled' ? dailyRes.value : null;
    const master = masterRes.status === 'fulfilled' ? masterRes.value : null;
    const history = historyRes.status === 'fulfilled' ? historyRes.value : [];

    if (!daily) {
      console.warn(`❌ Daily scores niet geladen voor ${symbol}`);
      setLoading(false);
      return;
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

    setScores({
      macro: {
        score: macroScore,
        trend: mData.trend ?? 'Stable',
        bias: mData.bias ?? daily.macro?.advies ?? 'Neutral',
        risk: mData.risk ?? 'Low',
        uitleg: daily.macro?.interpretation ?? 'Geen uitleg beschikbaar',
        advies: getAdvies(macroScore),
        top_contributors: normalizeArray(daily.macro?.top_contributors),
      },
      technical: {
        score: technicalScore,
        trend: tData.trend ?? 'Stable',
        bias: tData.bias ?? daily.technical?.advies ?? 'Neutral',
        risk: tData.risk ?? 'Low',
        uitleg: daily.technical?.interpretation ?? 'Geen uitleg beschikbaar',
        advies: getAdvies(technicalScore),
        top_contributors: normalizeArray(daily.technical?.top_contributors),
      },
      market: {
        score: marketScore,
        trend: mkData.trend ?? 'Stable',
        bias: mkData.bias ?? daily.market?.advies ?? 'Neutral',
        risk: mkData.risk ?? 'Low',
        uitleg: daily.market?.interpretation ?? 'Geen uitleg beschikbaar',
        advies: getAdvies(marketScore),
        top_contributors: normalizeArray(daily.market?.top_contributors),
      },
      setup: {
        score: setupScore,
        trend: sData.trend ?? 'Stable',
        bias: sData.bias ?? daily.setup?.advies ?? 'Neutral',
        risk: sData.risk ?? 'Low',
        uitleg: daily.setup?.interpretation ?? 'Geen uitleg beschikbaar',
        advies: getAdvies(setupScore),
        top_contributors: normalizeArray(daily.setup?.top_contributors),
      },
      master: {
        score: calculatedMasterScore,
        trend: master?.master_trend ?? '–',
        bias: master?.master_bias ?? '–',
        risk: master?.master_risk ?? '–',
        outlook: master?.outlook ?? 'Geen outlook',
        summary: master?.summary ?? 'Geen samenvatting beschikbaar',
        weights
      },
      history
    });

    setLoading(false);
  }

  const saveWeights = async (newWeights) => {
    setLoading(true);
    await updateIntelligenceWeights(newWeights);
    await fetchScores();
  };

  useEffect(() => {
    fetchScores();
  }, [symbol]);

  return { ...scores, loading, saveWeights, refresh: fetchScores };
}
