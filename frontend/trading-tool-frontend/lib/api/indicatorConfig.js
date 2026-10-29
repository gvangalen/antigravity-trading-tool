'use client';

import { fetchAuth } from '@/lib/api/auth';

export async function getPairIndicatorConfig(marketId, category, indicator) {
  const params = new URLSearchParams({ market_id: String(marketId), category, indicator });
  return fetchAuth(`/api/workspace/exact-market/indicator-config?${params}`, { method: 'GET' });
}

export async function previewPairIndicatorImpact(marketId, category, indicator) {
  const params = new URLSearchParams({ market_id: String(marketId), category, indicator });
  return fetchAuth(`/api/workspace/exact-market/indicator-impact?${params}`, { method: 'GET' });
}

export async function savePairIndicatorConfig({ marketId, category, indicator, mode, draft }) {
  return fetchAuth('/api/workspace/exact-market/indicator-config', {
    method: 'PUT',
    body: JSON.stringify({ market_id: marketId, category, indicator, mode,
      score_mode: draft.score_mode, weight: draft.weight, rules: draft.rules }),
  });
}

export async function deletePairIndicatorConfig(marketId, category, indicator) {
  const params = new URLSearchParams({ market_id: String(marketId), category, indicator });
  return fetchAuth(`/api/workspace/exact-market/indicator-config?${params}`, { method: 'DELETE' });
}

export async function previewIndicatorImpact({ category, indicator, symbol }) {
  return fetchAuth('/api/indicator_config/preview', {
    method: 'POST',
    body: JSON.stringify({ category, indicator, symbol }),
  });
}

//
// ======================================================
// 🔹 1. Indicator config ophalen
// ======================================================
export async function getIndicatorConfig(category, indicator, symbol) {
  try {
    return await fetchAuth(
      `/api/indicator_config/${category}/${indicator}?symbol=${encodeURIComponent(symbol)}`
    );
  } catch (err) {
    console.error("❌ getIndicatorConfig:", err);
    return null;
  }
}

//
// ======================================================
// 🔹 2. Score mode + weight opslaan
// ======================================================
export async function updateIndicatorSettings({
  category,
  indicator,
  symbol,
  score_mode,
  weight,
}) {
  try {
    return await fetchAuth(`/api/indicator_config/settings`, {
      method: "PUT",
      body: JSON.stringify({
        category,
        indicator,
        symbol,
        score_mode,
        weight,
      }),
    });
  } catch (err) {
    console.error("❌ updateIndicatorSettings:", err);
    throw err;
  }
}

//
// ======================================================
// 🔹 3. Custom rules opslaan
// ======================================================
export async function saveCustomRules({
  category,
  indicator,
  symbol,
  rules,
  weight,
  create_only = false,
}) {
  try {
    return await fetchAuth(`/api/indicator_config/custom`, {
      method: "POST",
      body: JSON.stringify({
        category,
        indicator,
        symbol,
        rules,
        weight,
        create_only,
      }),
    });
  } catch (err) {
    console.error("❌ saveCustomRules:", err);
    throw err;
  }
}

//
// ======================================================
// 🔹 4. Reset naar standaard regels
// ======================================================
export async function resetIndicatorConfig(
  category,
  indicator,
  symbol,
) {
  try {
    return await fetchAuth(`/api/indicator_config/reset`, {
      method: "POST",
      body: JSON.stringify({
        category,
        indicator,
        symbol,
      }),
    });
  } catch (err) {
    console.error("❌ resetIndicatorConfig:", err);
    throw err;
  }
}
