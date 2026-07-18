'use client';

import { fetchAuth } from '@/lib/api/auth';  // ✅ JUISTE AUTH

const DAILY_SCORES_TTL_MS = 30_000;
const dailyScoresCache = new Map();
const inflightDailyScoreRequests = new Map();

//
// =====================================================
// 🔹 1. Dagelijkse scores ophalen (met veilige fallback)
// =====================================================
export async function getDailyScores(symbol = "BTC") {
  const normalizedSymbol = String(symbol || "BTC").toUpperCase();
  const cached = dailyScoresCache.get(normalizedSymbol);
  if (cached && Date.now() - cached.timestamp < DAILY_SCORES_TTL_MS) {
    return cached.data;
  }

  if (inflightDailyScoreRequests.has(normalizedSymbol)) {
    return inflightDailyScoreRequests.get(normalizedSymbol);
  }

  const request = (async () => {
  try {
    const data = await fetchAuth(`/api/scores/daily?symbol=${normalizedSymbol}`);

    if (!data || typeof data !== 'object') {
      console.warn(`⚠️ getDailyScores(): backend gaf leeg resultaat voor ${normalizedSymbol} → fallback`);
      return fallbackScores();
    }

    dailyScoresCache.set(normalizedSymbol, {
      data,
      timestamp: Date.now(),
    });
    return data;
  } catch (err) {
    console.error('❌ getDailyScores ERROR:', err);
    return fallbackScores();
  }
  })();

  inflightDailyScoreRequests.set(normalizedSymbol, request);

  try {
    return await request;
  } finally {
    inflightDailyScoreRequests.delete(normalizedSymbol);
  }
}

//
// =====================================================
// 🔹 2. AI Master Score ophalen
// =====================================================
export async function getAiMasterScore(symbol = "BTC") {
  try {
    const data = await fetchAuth(`/api/ai/master_score?symbol=${symbol}`);
    return data || { master_score: 50 };
  } catch (err) {
    console.error('❌ getAiMasterScore ERROR:', err);
    return { master_score: 50 };
  }
}

//
// =====================================================
// 🔹 3. Macro summary ophalen (Blijft globaal)
// =====================================================
export async function getMacroSummary() {
  try {
    const data = await fetchAuth(`/api/macro/summary`);
    return data || [];
  } catch (err) {
    console.error('❌ getMacroSummary ERROR:', err);
    return [];
  }
}

//
// =====================================================
// 🔹 4. Score History ophalen (Analytics)
// =====================================================
export async function getScoreHistory(days = 30, symbol = "BTC") {
  try {
    const data = await fetchAuth(`/api/scores/history?days=${days}&symbol=${symbol}`);
    return data || [];
  } catch (err) {
    console.error('❌ getScoreHistory ERROR:', err);
    return [];
  }
}

//
// =====================================================
// 🔹 5. Intelligence Weights bijwerken
// =====================================================
export async function updateIntelligenceWeights(weights) {
  try {
    const data = await fetchAuth(`/api/user/intelligence-weights`, {
      method: 'POST',
      body: JSON.stringify({ weights }),
    });
    return data;
  } catch (err) {
    console.error('❌ updateIntelligenceWeights ERROR:', err);
    return { status: 'error' };
  }
}

//
// =====================================================
// 🔹 Fallback scores (gebruikt bij errors)
// =====================================================
function fallbackScores() {
  return {
    macro: { score: 50, interpretation: "Licht neutraal", top_contributors: [] },
    technical: { score: 50, interpretation: "Licht neutraal", top_contributors: [] },
    market: { score: 50, interpretation: "Licht neutraal", top_contributors: [] },
    setup: { score: 50, interpretation: "Licht neutraal", top_contributors: [], active_setups: [] }
  };
}
