"use client";

import { fetchAuth } from "@/lib/api/auth";

//
// =======================================================
// 🧭 Onboarding status (USER-SPECIFIC → AUTH)
// =======================================================
//

// 📌 Huidige onboarding status ophalen
export const getOnboardingStatus = async () => {
  return await fetchAuth(`/api/onboarding/status`, {
    method: "GET",
  });
};

//
// =======================================================
// ✅ Stappen afronden
// =======================================================
//

// ✔ Eén onboarding stap afronden
export const completeOnboardingStep = async (step) => {
  if (!step) return;

  return await fetchAuth(`/api/onboarding/complete_step`, {
    method: "POST",
    body: JSON.stringify({ step }),
  });
};

// 🏁 Onboarding expliciet afronden (finish-knop)
export const finishOnboarding = async () => {
  return await fetchAuth(`/api/onboarding/finish`, {
    method: "POST",
  });
};

//
// =======================================================
// 🔄 Reset (alleen dev / testen)
// =======================================================
//

// ♻️ Onboarding resetten
export const resetOnboarding = async () => {
  return await fetchAuth(`/api/onboarding/reset`, {
    method: "POST",
  });
};
