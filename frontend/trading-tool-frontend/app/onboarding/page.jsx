"use client";

import { useEffect, useMemo } from "react";
import Link from "next/link";
import {
  ArrowRight,
  Bot,
  BrainCircuit,
  CheckCircle2,
  ClipboardList,
  Sparkles,
  User,
} from "lucide-react";

import { useTranslation } from "@/app/providers/I18nProvider";
import { useOnboarding } from "@/hooks/useOnboarding";
import { trackAssistantEvent } from "@/lib/api/assistantAnalytics";

const PHASE_ICONS = {
  profile: User,
  analysis: BrainCircuit,
  plan: ClipboardList,
  automation: Bot,
};

export default function OnboardingPage() {
  const { t } = useTranslation();
  const overviewCopy = t?.traderProfile?.onboardingOverview || {};
  const onboardingPageCopy = t?.traderProfile?.onboardingPage || {};
  const {
    loading,
    onboardingComplete,
    currentPhase,
    nextRoute,
    phaseStatus,
    phaseUnlocks,
    phaseMissing,
    activeAsset,
  } = useOnboarding();

  useEffect(() => {
    trackAssistantEvent({
      event_name: "screen_view",
      page: "/onboarding",
      surface: "web",
      flow_type: "onboarding_v2",
      metadata: {
        onboarding_complete: Boolean(onboardingComplete),
        current_phase: currentPhase,
        active_asset: activeAsset || null,
      },
    });
  }, [activeAsset, currentPhase, onboardingComplete]);

  const phaseMeta = useMemo(
    () => ({
      profile: {
        icon: PHASE_ICONS.profile,
        title: overviewCopy?.steps?.profile?.title || "Profile",
        description: overviewCopy?.steps?.profile?.description || "Profile",
      },
      analysis: {
        icon: PHASE_ICONS.analysis,
        title: overviewCopy?.steps?.asset?.title || "Analysis",
        description: overviewCopy?.steps?.asset?.description || "Analysis",
      },
      plan: {
        icon: PHASE_ICONS.plan,
        title: overviewCopy?.steps?.setup?.title || "My Plan",
        description: overviewCopy?.steps?.setup?.description || "My Plan",
      },
      automation: {
        icon: PHASE_ICONS.automation,
        title: overviewCopy?.steps?.bot?.title || "Automation",
        description: overviewCopy?.steps?.bot?.description || "Automation",
      },
    }),
    [overviewCopy],
  );

  function tokenLabel(phaseKey, token) {
    const labels = onboardingPageCopy?.tokenLabels?.[phaseKey];
    return labels?.[token] || token.replace(/_/g, " ");
  }

  const phases = useMemo(
    () => ["profile", "analysis", "plan", "automation"].map((key) => {
      const meta = phaseMeta[key];
      return {
        key,
        ...meta,
        complete: Boolean(phaseStatus?.[key]),
        unlocked: Boolean(phaseUnlocks?.[key]),
        missing: phaseMissing?.[key] || [],
      };
    }),
    [phaseMeta, phaseMissing, phaseStatus, phaseUnlocks],
  );

  const completedCount = phases.filter((phase) => phase.complete).length;
  const progressPercent = Math.round((completedCount / phases.length) * 100);
  const activePhase = phases.find((phase) => phase.key === currentPhase) || phases[0];

  if (loading) {
    return (
      <div className="flex min-h-[60vh] items-center justify-center">
          <div className="flex flex-col items-center gap-4">
          <div className="h-12 w-12 animate-spin rounded-full border-4 border-blue-600/30 border-t-blue-600" />
          <p className="text-xs font-black uppercase tracking-[0.2em] text-slate-500">
            {overviewCopy?.loading || "Loading onboarding"}
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="mx-auto flex w-full max-w-6xl flex-col gap-8 py-8">
      <section className="overflow-hidden rounded-[32px] border border-slate-200/80 bg-white shadow-[0_24px_80px_-45px_rgba(37,99,235,0.35)] dark:border-slate-800 dark:bg-[#0f172a]">
        <div className="border-b border-slate-100 px-8 py-6 dark:border-slate-800">
          <div className="flex flex-col gap-6 lg:flex-row lg:items-center lg:justify-between">
            <div className="max-w-3xl">
              <div className="flex items-center gap-2 text-[10px] font-black uppercase tracking-[0.28em] text-blue-600 dark:text-blue-400">
                <Sparkles size={13} />
                {onboardingPageCopy?.eyebrow || "Guided onboarding"}
              </div>
              <h1 className="mt-3 text-4xl font-black tracking-tight text-slate-950 dark:text-slate-50">
                {onboardingPageCopy?.title || "Set up the real product flow, step by step"}
              </h1>
              <p className="mt-3 text-sm font-medium leading-7 text-slate-500 dark:text-slate-400">
                {onboardingPageCopy?.description ||
                  "FINN guides you through the same workspaces you will use every day: Analysis, My Plan and Automation. Reflection stays outside onboarding and fills itself later."}
              </p>
              <div className="mt-4 flex flex-wrap gap-2">
                <span className="rounded-full border border-slate-200 bg-slate-50 px-3 py-1.5 text-[11px] font-bold text-slate-700 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300">
                  {onboardingPageCopy?.activeAssetLabel || "Asset"}: {activeAsset || "BTC"}
                </span>
                <span className="rounded-full border border-slate-200 bg-slate-50 px-3 py-1.5 text-[11px] font-bold text-slate-700 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300">
                  {completedCount}/{phases.length} {onboardingPageCopy?.phasesCompleteLabel || "phases complete"}
                </span>
              </div>
            </div>

            <div className="flex h-36 w-36 shrink-0 items-center justify-center rounded-full border-8 border-blue-100 bg-blue-50 text-center dark:border-blue-950/40 dark:bg-blue-950/20">
              <div>
                <div className="text-4xl font-black tracking-tight text-blue-700 dark:text-blue-300">
                  {progressPercent}%
                </div>
                <div className="text-[10px] font-black uppercase tracking-[0.26em] text-blue-600 dark:text-blue-400">
                  {onboardingPageCopy?.readyLabel || "Ready"}
                </div>
              </div>
            </div>
          </div>
        </div>

      </section>

      {onboardingComplete ? (
        <section className="rounded-[32px] border border-emerald-200 bg-white p-8 shadow-[0_20px_60px_-40px_rgba(16,185,129,0.35)] dark:border-emerald-900/50 dark:bg-[#0f172a]">
          <div className="flex flex-col gap-6 lg:flex-row lg:items-center lg:justify-between">
            <div className="max-w-3xl">
              <div className="text-[10px] font-black uppercase tracking-[0.28em] text-emerald-600 dark:text-emerald-400">
                {onboardingPageCopy?.completeEyebrow || "Onboarding complete"}
              </div>
              <h2 className="mt-2 text-3xl font-black tracking-tight text-slate-950 dark:text-slate-50">
                {onboardingPageCopy?.completeTitle || "You are ready to work with FINN"}
              </h2>
              <p className="mt-3 text-sm font-medium leading-7 text-slate-600 dark:text-slate-400">
                {onboardingPageCopy?.completeDescription ||
                  "Your profile, analysis flow, plan and automation are configured. FINN can now keep tracking your market context and help you follow the plan you set."}
              </p>
            </div>
            <Link
              href={activeAsset ? `/asset?symbol=${encodeURIComponent(activeAsset)}` : "/asset"}
              className="inline-flex items-center justify-center gap-2 rounded-2xl bg-emerald-600 px-6 py-4 text-[11px] font-black uppercase tracking-[0.22em] text-white shadow-lg shadow-emerald-600/20 transition hover:bg-emerald-700"
            >
              {onboardingPageCopy?.completeCta || "Go to Analysis"}
              <ArrowRight size={14} />
            </Link>
          </div>
        </section>
      ) : (
        <section className="rounded-[32px] border border-blue-200 bg-white p-8 shadow-[0_20px_70px_-45px_rgba(37,99,235,0.35)] dark:border-blue-900/40 dark:bg-[#0f172a]">
          <div className="flex flex-col gap-8 lg:flex-row lg:items-start lg:justify-between">
            <div className="max-w-3xl">
              <div className="text-[10px] font-black uppercase tracking-[0.28em] text-blue-600 dark:text-blue-400">
                {onboardingPageCopy?.phaseEyebrow || "FINN guides this phase"}
              </div>
              <h2 className="mt-2 text-3xl font-black tracking-tight text-slate-950 dark:text-slate-50">
                {activePhase.title}
              </h2>
              <p className="mt-3 text-sm font-medium leading-7 text-slate-600 dark:text-slate-400">
                {activePhase.description}
              </p>
              {activePhase.missing.length > 0 ? (
                <div className="mt-5 rounded-2xl border border-blue-100 bg-blue-50 px-5 py-4 dark:border-blue-900/40 dark:bg-blue-950/20">
                  <div className="text-[10px] font-black uppercase tracking-[0.22em] text-blue-600 dark:text-blue-400">
                    {onboardingPageCopy?.checklistLabel || "Checklist"}
                  </div>
                  <ul className="mt-3 space-y-2 text-sm font-semibold text-slate-700 dark:text-slate-300">
                    {activePhase.missing.map((token) => (
                      <li key={token} className="flex items-start gap-3">
                        <span className="mt-1 inline-flex h-2 w-2 rounded-full bg-blue-500" />
                        <span>{tokenLabel(activePhase.key, token)}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              ) : null}
            </div>

            <div className="flex w-full flex-col gap-3 lg:w-auto lg:min-w-[240px]">
              <Link
                href={nextRoute}
                className="inline-flex items-center justify-center gap-2 rounded-2xl bg-blue-600 px-6 py-4 text-[11px] font-black uppercase tracking-[0.22em] text-white shadow-lg shadow-blue-600/20 transition hover:bg-blue-700"
              >
                {onboardingPageCopy?.openStepCta || overviewCopy?.openStep || "Open step"}
                <ArrowRight size={14} />
              </Link>
              <p className="text-center text-[11px] font-bold leading-relaxed text-slate-500 dark:text-slate-400">
                {onboardingPageCopy?.helper ||
                  "FINN will explain the current action inside the workspace and highlight the right place to continue."}
              </p>
            </div>
          </div>
        </section>
      )}
    </div>
  );
}
