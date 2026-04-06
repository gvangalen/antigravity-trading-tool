'use client';

import { fetchAuth } from '@/lib/api/auth';

//
// ======================================================
// 🔹 1. Indicator config ophalen
// ======================================================
export async function getIndicatorConfig(category, indicator) {
  try {
    return await fetchAuth(
      `/api/indicator_config/${category}/${indicator}`
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
  score_mode,
  weight,
}) {
  try {
    return await fetchAuth(`/api/indicator_config/settings`, {
      method: "PUT",
      body: JSON.stringify({
        category,
        indicator,
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
  rules,
}) {
  try {
    return await fetchAuth(`/api/indicator_config/custom`, {
      method: "POST",
      body: JSON.stringify({
        category,
        indicator,
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
  indicator
) {
  try {
    return await fetchAuth(`/api/indicator_config/reset`, {
      method: "POST",
      body: JSON.stringify({
        category,
        indicator,
      }),
    });
  } catch (err) {
    console.error("❌ resetIndicatorConfig:", err);
    throw err;
  }
}
