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

export function useScoresData() {
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
    const [dailyRes, masterRes, historyRes] = await Promise.allSettled([
      getDailyScores(),
      getAiMasterScore(),
      getScoreHistory(30)
    ]);

    const daily = dailyRes.status === 'fulfilled' ? dailyRes.value : null;
    const master = masterRes.status === 'fulfilled' ? masterRes.value : null;
    const history = historyRes.status === 'fulfilled' ? historyRes.value : [];

    if (!daily) {
      console.warn("❌ Daily scores niet geladen");
      setLoading(false);
      return;
    }

    const mData = master?.domains?.macro || {};
    const tData = master?.domains?.technical || {};
    const mkData = master?.domains?.market || {};
    const sData = master?.domains?.setup || {};

    setScores({
      macro: {
        score: mData.score ?? daily.macro?.score ?? 0,
        trend: mData.trend ?? 'Stable',
        bias: mData.bias ?? daily.macro?.advies ?? 'Neutral',
        risk: mData.risk ?? 'Low',
        uitleg: daily.macro?.interpretation ?? 'Geen uitleg beschikbaar',
        advies: getAdvies(mData.score ?? daily.macro?.score ?? 0),
        top_contributors: normalizeArray(daily.macro?.top_contributors),
      },
      technical: {
        score: tData.score ?? daily.technical?.score ?? 0,
        trend: tData.trend ?? 'Stable',
        bias: tData.bias ?? daily.technical?.advies ?? 'Neutral',
        risk: tData.risk ?? 'Low',
        uitleg: daily.technical?.interpretation ?? 'Geen uitleg beschikbaar',
        advies: getAdvies(tData.score ?? daily.technical?.score ?? 0),
        top_contributors: normalizeArray(daily.technical?.top_contributors),
      },
      market: {
        score: mkData.score ?? daily.market?.score ?? 0,
        trend: mkData.trend ?? 'Stable',
        bias: mkData.bias ?? daily.market?.advies ?? 'Neutral',
        risk: mkData.risk ?? 'Low',
        uitleg: daily.market?.interpretation ?? 'Geen uitleg beschikbaar',
        advies: getAdvies(mkData.score ?? daily.market?.score ?? 0),
        top_contributors: normalizeArray(daily.market?.top_contributors),
      },
      setup: {
        score: sData.score ?? daily.setup?.score ?? 0,
        trend: sData.trend ?? 'Stable',
        bias: sData.bias ?? daily.setup?.advies ?? 'Neutral',
        risk: sData.risk ?? 'Low',
        uitleg: daily.setup?.interpretation ?? 'Geen uitleg beschikbaar',
        advies: getAdvies(sData.score ?? daily.setup?.score ?? 0),
        top_contributors: normalizeArray(daily.setup?.top_contributors),
      },
      master: {
        score: master?.master_score ?? 0,
        trend: master?.master_trend ?? '–',
        bias: master?.master_bias ?? '–',
        risk: master?.master_risk ?? '–',
        outlook: master?.outlook ?? 'Geen outlook',
        summary: master?.summary ?? 'Geen samenvatting beschikbaar',
        weights: master?.weights || { macro: 0.25, market: 0.25, technical: 0.25, setup: 0.25 }
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
  }, []);

  return { ...scores, loading, saveWeights, refresh: fetchScores };
}
