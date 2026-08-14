"use client";

import { fetchAuth } from "@/lib/api/auth";

const ONBOARDING_STATUS_CACHE_KEY = "tt_onboarding_status_cache_v2";
const ONBOARDING_STATUS_CACHE_TTL_MS = 5 * 60 * 1000;

function readOnboardingStatusCache(maxAgeMs = ONBOARDING_STATUS_CACHE_TTL_MS) {
  if (typeof window === "undefined") return null;

  try {
    const raw = sessionStorage.getItem(ONBOARDING_STATUS_CACHE_KEY);
    if (!raw) return null;

    const parsed = JSON.parse(raw);
    if (!parsed?.value || !parsed?.savedAt) return null;
    if (Date.now() - Number(parsed.savedAt) > maxAgeMs) return null;
    return parsed.value;
  } catch {
    return null;
  }
}

export function cacheOnboardingStatus(status) {
  if (typeof window === "undefined" || !status) return;

  try {
    sessionStorage.setItem(
      ONBOARDING_STATUS_CACHE_KEY,
      JSON.stringify({
        value: status,
        savedAt: Date.now(),
      })
    );
  } catch {
    // Silent cache failure
  }
}

export function clearOnboardingStatusCache() {
  if (typeof window === "undefined") return;

  try {
    sessionStorage.removeItem(ONBOARDING_STATUS_CACHE_KEY);
  } catch {
    // Silent cache failure
  }
}

export function getCachedOnboardingStatus(maxAgeMs = ONBOARDING_STATUS_CACHE_TTL_MS) {
  return readOnboardingStatusCache(maxAgeMs);
}

//
// =======================================================
// 🧭 Onboarding status (USER-SPECIFIC → AUTH)
// =======================================================
//

// 📌 Huidige onboarding status ophalen
export const getOnboardingStatus = async (options = {}) => {
  const { preferCache = false, maxAgeMs = ONBOARDING_STATUS_CACHE_TTL_MS } = options;

  if (preferCache) {
    const cached = readOnboardingStatusCache(maxAgeMs);
    if (cached) return cached;
  }

  const status = await fetchAuth(`/api/onboarding/status`, {
    method: "GET",
  });
  cacheOnboardingStatus(status);
  return status;
};

//
// =======================================================
// ✅ Stappen afronden
// =======================================================
//

// ✔ Eén onboarding stap afronden
export const completeOnboardingStep = async (step) => {
  if (!step) return;

  const result = await fetchAuth(`/api/onboarding/complete_step`, {
    method: "POST",
    body: JSON.stringify({ step }),
  });
  return result;
};

// 🏁 Onboarding expliciet afronden (finish-knop)
export const finishOnboarding = async () => {
  const result = await fetchAuth(`/api/onboarding/finish`, {
    method: "POST",
  });
  return result;
};

//
// =======================================================
// 🔄 Reset (alleen dev / testen)
// =======================================================
//

// ♻️ Onboarding resetten
export const resetOnboarding = async () => {
  const result = await fetchAuth(`/api/onboarding/reset`, {
    method: "POST",
  });
  cacheOnboardingStatus({
    has_profile: false,
    has_asset: false,
    has_market: false,
    has_macro: false,
    has_technical: false,
    has_setup: false,
    has_strategy: false,
    has_bot: false,
    onboarding_complete: false,
    current_phase: "profile",
    next_action: "complete_profile",
    next_route: "/onboarding/profile",
    phases_completed: {
      profile: false,
      analysis: false,
      plan: false,
      automation: false,
      complete: false,
    },
    phases_unlocked: {
      profile: true,
      analysis: false,
      plan: false,
      automation: false,
      complete: false,
    },
    phase_missing: {
      profile: ["profile_preferences"],
      analysis: ["asset", "market_indicator", "macro_indicator", "technical_indicator"],
      plan: ["setup", "strategy"],
      automation: ["exchange_connection", "bot"],
      complete: [],
    },
  });
  return result;
};
