'use client';

import { fetchAuth } from '@/lib/api/auth';

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
}) {
  try {
    return await fetchAuth(`/api/indicator_config/custom`, {
      method: "POST",
      body: JSON.stringify({
        category,
        indicator,
        symbol,
        rules,
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
