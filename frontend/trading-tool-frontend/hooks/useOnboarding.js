"use client";

import { useState, useEffect, useCallback, useMemo } from "react";

import {
  getOnboardingStatus,
  completeOnboardingStep,
  finishOnboarding,
  resetOnboarding,
} from "@/lib/api/onboarding";

/**
 * =====================================================
 * 🧭 useOnboarding (OFFICIËLE VERSIE + DEBUG LOGGING)
 * - Praat ALLEEN met lib/api/onboarding
 * - Pipeline-aware
 * - EXTRA logging voor debugging
 * =====================================================
 */
export function useOnboarding() {
  const [status, setStatus] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);

  // =====================================================
  // 1️⃣ Status ophalen
  // =====================================================
  const fetchStatus = useCallback(async () => {
    try {
      console.log("🧭 [Onboarding] Fetch status...");
      setLoading(true);
      setError(null);

      const data = await getOnboardingStatus();

      console.log("🧭 [Onboarding] Status ontvangen:", data);
      setStatus(data);

    } catch (err) {
      console.error("❌ [Onboarding] Failed to load status:", err);
      setError("Kon onboarding-status niet laden.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchStatus();
  }, [fetchStatus]);

  // =====================================================
  // 2️⃣ Acties
  // =====================================================
  const completeStep = async (step) => {
    try {
      console.log(`🧭 [Onboarding] completeStep("${step}") gestart`);
      setSaving(true);
      setError(null);

      await completeOnboardingStep(step);

      console.log(`✅ [Onboarding] Step "${step}" succesvol gemarkeerd`);
      await fetchStatus();

    } catch (err) {
      console.error(
        `❌ [Onboarding] Complete step failed (${step}):`,
        err
      );
      setError("Stap kon niet worden voltooid.");
    } finally {
      setSaving(false);
    }
  };

  const finish = async () => {
    try {
      console.log("🧭 [Onboarding] finishOnboarding gestart");
      setSaving(true);
      setError(null);

      await finishOnboarding();

      console.log("✅ [Onboarding] finishOnboarding succesvol");
      await fetchStatus();

    } catch (err) {
      console.error("❌ [Onboarding] Finish onboarding failed:", err);
      setError("Onboarding afronden mislukt.");
    } finally {
      setSaving(false);
    }
  };

  const reset = async () => {
    try {
      console.log("🧭 [Onboarding] resetOnboarding gestart");
      setSaving(true);
      setError(null);

      await resetOnboarding();

      console.log("🔁 [Onboarding] Onboarding gereset");
      await fetchStatus();

    } catch (err) {
      console.error("❌ [Onboarding] Reset onboarding failed:", err);
      setError("Onboarding reset mislukt.");
    } finally {
      setSaving(false);
    }
  };

  // =====================================================
  // 3️⃣ Stap-status
  // =====================================================
  const stepStatus = useMemo(() => {
    if (!status) return null;

    const steps = {
      market: !!status.has_market,
      macro: !!status.has_macro,
      technical: !!status.has_technical,
      setup: !!status.has_setup,
      strategy: !!status.has_strategy,
    };

    console.log("🧭 [Onboarding] stepStatus:", steps);
    return steps;
  }, [status]);

  // =====================================================
  // 4️⃣ Onboarding & pipeline status
  // =====================================================
  const onboardingComplete = useMemo(() => {
    if (!stepStatus) return false;
    const done = Object.values(stepStatus).every(Boolean);
    console.log("🧭 [Onboarding] onboardingComplete =", done);
    return done;
  }, [stepStatus]);

  const pipelineStarted = !!status?.pipeline_started;

  const pipelineRunning =
    onboardingComplete && !pipelineStarted;

  const dashboardReady =
    onboardingComplete && pipelineStarted;

  // =====================================================
  // 5️⃣ Unlock logic (volgorde)
  // =====================================================
  const allowedSteps = {
    market: true,
    macro: stepStatus?.market ?? false,
    technical: stepStatus?.macro ?? false,
    setup: stepStatus?.technical ?? false,
    strategy: stepStatus?.setup ?? false,
  };

  console.log("🧭 [Onboarding] allowedSteps:", allowedSteps);

  // =====================================================
  // 6️⃣ Export
  // =====================================================
  return {
    status,
    stepStatus,

    loading,
    saving,
    error,

    onboardingComplete,
    pipelineStarted,
    pipelineRunning,
    dashboardReady,

    allowedSteps,

    completeStep,
    finish,
    reset,
    refresh: fetchStatus,
  };
}
