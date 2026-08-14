"use client";

import { useState, useEffect, useCallback, useMemo } from "react";
import { usePathname } from "next/navigation";

import {
  getOnboardingStatus,
  getCachedOnboardingStatus,
  completeOnboardingStep,
  finishOnboarding,
  resetOnboarding,
  cacheOnboardingStatus,
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
    const cached = getCachedOnboardingStatus(30_000);
    if (cached) {
      setStatus(cached);
      setLoading(false);
    }

    try {
      if (!cached) {
        setLoading(true);
      }
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
      cacheOnboardingStatus({
        ...(status || {}),
        [`has_${step}`]: true,
      });
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
      cacheOnboardingStatus({
        ...(status || {}),
        onboarding_complete: true,
      });
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

    return {
      profile: !!status.has_profile,
      asset: !!status.has_asset,
      market: !!status.has_market,
      macro: !!status.has_macro,
      technical: !!status.has_technical,
      setup: !!status.has_setup,
      strategy: !!status.has_strategy,
      bot: !!status.has_bot,
      has_profile: !!status.has_profile,
      has_asset: !!status.has_asset,
      has_market: !!status.has_market,
      has_macro: !!status.has_macro,
      has_technical: !!status.has_technical,
      has_setup: !!status.has_setup,
      has_strategy: !!status.has_strategy,
      has_bot: !!status.has_bot,
    };
  }, [status]);

  const phaseStatus = useMemo(() => {
    if (!status) return null;
    const backendPhases = status.phases_completed;
    if (backendPhases) return backendPhases;

    return {
      profile: !!status.has_profile,
      analysis: !!status.has_asset && !!status.has_market && !!status.has_macro && !!status.has_technical,
      plan: !!status.has_setup && !!status.has_strategy,
      automation: !!status.has_bot,
      complete:
        !!status.has_profile &&
        !!status.has_asset &&
        !!status.has_market &&
        !!status.has_macro &&
        !!status.has_technical &&
        !!status.has_setup &&
        !!status.has_strategy &&
        !!status.has_bot,
    };
  }, [status]);

  const phaseUnlocks = useMemo(() => {
    if (!status) return null;
    if (status.phases_unlocked) return status.phases_unlocked;

    return {
      profile: true,
      analysis: !!phaseStatus?.profile,
      plan: !!phaseStatus?.analysis,
      automation: !!phaseStatus?.plan,
      complete: !!phaseStatus?.automation,
    };
  }, [status, phaseStatus]);

  const phaseMissing = useMemo(() => {
    if (!status) return null;
    return status.phase_missing || {
      profile: phaseStatus?.profile ? [] : ["profile_preferences"],
      analysis: [
        !status.has_asset ? "asset" : null,
        !status.has_market ? "market_indicator" : null,
        !status.has_macro ? "macro_indicator" : null,
        !status.has_technical ? "technical_indicator" : null,
      ].filter(Boolean),
      plan: [
        !status.has_setup ? "setup" : null,
        !status.has_strategy ? "strategy" : null,
      ].filter(Boolean),
      automation: [
        !status.has_bot ? "bot" : null,
      ].filter(Boolean),
      complete: [],
    };
  }, [status, phaseStatus]);

  // =====================================================
  // 4️⃣ Onboarding & pipeline status
  // =====================================================
  const onboardingComplete = useMemo(() => {
    if (!status && !stepStatus && !phaseStatus) return false;
    return Boolean(
      status?.onboarding_complete ??
      phaseStatus?.complete ??
      (
        stepStatus &&
        stepStatus.asset &&
        stepStatus.market &&
        stepStatus.macro &&
        stepStatus.technical &&
        stepStatus.setup &&
        stepStatus.strategy &&
        stepStatus.bot
      )
    );
  }, [status, stepStatus, phaseStatus]);

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
    asset: stepStatus?.profile ?? false,
    market: stepStatus?.asset ?? false,
    macro: stepStatus?.market ?? false,
    technical: stepStatus?.macro ?? false,
    setup: stepStatus?.technical ?? false,
    strategy: stepStatus?.setup ?? false,
    bot: stepStatus?.strategy ?? false,
  };

  const currentPhase = status?.current_phase || (
    !phaseStatus?.profile ? "profile" :
    !phaseStatus?.analysis ? "analysis" :
    !phaseStatus?.plan ? "plan" :
    !phaseStatus?.automation ? "automation" :
    "complete"
  );
  const nextAction = status?.next_action || (
    currentPhase === "profile" ? "complete_profile" :
    currentPhase === "analysis" && !status?.has_asset ? "select_asset" :
    currentPhase === "analysis" && !status?.has_market ? "add_market_indicator" :
    currentPhase === "analysis" && !status?.has_macro ? "add_macro_indicator" :
    currentPhase === "analysis" && !status?.has_technical ? "add_technical_indicator" :
    currentPhase === "plan" && !status?.has_setup ? "create_setup" :
    currentPhase === "plan" && !status?.has_strategy ? "create_strategy" :
    currentPhase === "automation" && !status?.has_bot ? "create_bot" :
    "go_to_analysis"
  );
  const nextRoute = status?.next_route || "/onboarding";
  const activeAsset = status?.active_asset || "";

  // =====================================================
  // 6️⃣ Export
  // =====================================================
  return {
    status,
    stepStatus,
    phaseStatus,
    phaseUnlocks,
    phaseMissing,

    loading,
    saving,
    error,

    onboardingComplete,
    currentPhase,
    nextAction,
    nextRoute,
    activeAsset,
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
