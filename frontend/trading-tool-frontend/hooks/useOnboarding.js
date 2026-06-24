"use client";

import { useState, useEffect, useCallback, useMemo } from "react";
import { usePathname } from "next/navigation";

import {
  getOnboardingStatus,
  completeOnboardingStep,
  finishOnboarding,
  resetOnboarding,
} from "@/lib/api/onboarding";
import { trackAssistantEvent } from "@/lib/api/assistantAnalytics";

export function useOnboarding() {
  const pathname = usePathname();
  const [status, setStatus] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);

  // =====================================================
  // 1️⃣ Status ophalen
  // =====================================================
  const fetchStatus = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);

      const data = await getOnboardingStatus();
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
      setSaving(true);
      setError(null);

      await completeOnboardingStep(step);
      trackAssistantEvent({
        event_name: "onboarding_step_completed",
        page: pathname || "/onboarding",
        surface: "web",
        flow_type: "onboarding",
        action_type: step,
      });
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
      setSaving(true);
      setError(null);

      await finishOnboarding();
      trackAssistantEvent({
        event_name: "onboarding_completed",
        page: pathname || "/onboarding",
        surface: "web",
        flow_type: "onboarding",
      });
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
      setSaving(true);
      setError(null);

      await resetOnboarding();
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
      profile: !!status.has_profile,
      market: !!status.has_market,
      macro: !!status.has_macro,
      technical: !!status.has_technical,
      setup: !!status.has_setup,
      strategy: !!status.has_strategy,
    };
    return steps;
  }, [status]);

  // =====================================================
  // 4️⃣ Onboarding & pipeline status
  // =====================================================
  const onboardingComplete = useMemo(() => {
    if (!status && !stepStatus) return false;
    const done = Boolean(
      status?.onboarding_complete ?? (
        stepStatus &&
        stepStatus.market &&
        stepStatus.macro &&
        stepStatus.technical &&
        stepStatus.setup &&
        stepStatus.strategy
      )
    );
    return done;
  }, [status, stepStatus]);

  const pipelineStarted = !!status?.pipeline_started;

  const pipelineRunning =
    onboardingComplete && !pipelineStarted;

  const dashboardReady =
    onboardingComplete && pipelineStarted;

  // =====================================================
  // 5️⃣ Unlock logic (volgorde)
  // =====================================================
  const allowedSteps = {
    profile: true,
    market: stepStatus?.profile ?? false,
    macro: stepStatus?.market ?? false,
    technical: stepStatus?.macro ?? false,
    setup: stepStatus?.technical ?? false,
    strategy: stepStatus?.setup ?? false,
  };

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
