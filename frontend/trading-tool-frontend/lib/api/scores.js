'use client';

import { fetchAuth } from '@/lib/api/auth';  // ✅ JUISTE AUTH

//
// =====================================================
// 🔹 1. Dagelijkse scores ophalen (met veilige fallback)
// =====================================================
export async function getDailyScores() {
  try {
    const data = await fetchAuth(`/api/scores/daily`);

    if (!data || typeof data !== 'object') {
      console.warn("⚠️ getDailyScores(): backend gaf leeg resultaat → fallback");
      return fallbackScores();
    }

    return data;
  } catch (err) {
    console.error('❌ getDailyScores ERROR:', err);
    return fallbackScores();
  }
}

//
// =====================================================
// 🔹 2. AI Master Score ophalen
// =====================================================
export async function getAiMasterScore() {
  try {
    const data = await fetchAuth(`/api/ai/master_score`);
    return data || { master_score: 50 };
  } catch (err) {
    console.error('❌ getAiMasterScore ERROR:', err);
    return { master_score: 50 };
  }
}

//
// =====================================================
// 🔹 3. Macro summary ophalen
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
