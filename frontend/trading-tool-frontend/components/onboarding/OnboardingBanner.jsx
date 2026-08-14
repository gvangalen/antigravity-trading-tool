"use client";

import Link from "next/link";
import { ArrowRight, BrainCircuit, Bot, CheckCircle2, ClipboardList, Sparkles, User } from "lucide-react";

import { useTranslation } from "@/app/providers/I18nProvider";
import { useOnboarding } from "@/hooks/useOnboarding";

const STEP_PHASE_MAP = {
  profile: "profile",
  asset: "analysis",
  market: "analysis",
  macro: "analysis",
  technical: "analysis",
  setup: "plan",
  strategy: "plan",
  bot: "automation",
};

const PHASE_META = {
  profile: { icon: User, label: "profile" },
  analysis: { icon: BrainCircuit, label: "analysis" },
  plan: { icon: ClipboardList, label: "plan" },
  automation: { icon: Bot, label: "automation" },
};

const STEP_LABELS = {
  profile: "profile preferences",
  asset: "asset selection",
  market: "market indicator",
  macro: "macro indicator",
  technical: "technical indicator",
  setup: "setup",
  strategy: "strategy",
  bot: "bot configuration",
};

const STEP_BODIES = {
  profile:
    "Start by storing the profile details FINN actually uses: experience, style, risk and goals.",
  asset:
    "You are inside Analysis. Add one real asset first so everything else on this workspace stays anchored to the same symbol.",
  market:
    "You are inside Analysis. Open the configuration block and attach one market indicator so FINN gets the first live market evidence for this asset.",
  macro:
    "You are still inside Analysis. Add one macro indicator, such as DXY, so FINN can place the same asset inside the right regime.",
  technical:
    "You are still inside Analysis. Add one technical indicator, such as RSI or MA 200, so FINN can explain trend, momentum, and timing.",
  setup:
    "You are inside My Plan. Create one simple setup for the same asset so your analysis turns into explicit trading conditions.",
  strategy:
    "You are still inside My Plan. Create one strategy for that setup so entries, invalidation, and risk become a real execution plan.",
  bot:
    "You are inside Automation. Create one bot for the same plan and keep it safe with paper or paused mode unless you deliberately want live execution.",
};

function humanizeToken(token) {
  return String(token || "")
    .replace(/_/g, " ")
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

export default function OnboardingBanner({ step }) {
  const { t } = useTranslation();
  const bannerCopy = t?.traderProfile?.onboardingBanner || {};
  const {
    currentPhase,
    loading,
    onboardingComplete,
    phaseMissing,
    phaseStatus,
    phaseUnlocks,
  } = useOnboarding();

  const stepPhase = STEP_PHASE_MAP[step];
  const meta = PHASE_META[stepPhase];
  const Icon = meta?.icon;
  const phaseOrder = ["profile", "analysis", "plan", "automation"];
  const missing = phaseMissing?.[stepPhase] || [];
  const isPhaseComplete = Boolean(phaseStatus?.[stepPhase]);
  const completedPhaseCount = phaseOrder.filter((phase) => Boolean(phaseStatus?.[phase])).length;
  const progressPercent = Math.round((completedPhaseCount / phaseOrder.length) * 100);

  if (loading || onboardingComplete || !stepPhase || !meta || !Icon) return null;

  const phaseLabels = bannerCopy?.phaseLabels || {};
  const stepBodies = bannerCopy?.stepBodies || {};
  const label = phaseLabels?.[stepPhase] || meta.label;
  const headline = isPhaseComplete
    ? `${label} ${bannerCopy?.completeSuffix || "complete"}`
    : stepPhase === currentPhase
      ? `${label} ${bannerCopy?.inProgressSuffix || "in progress"}`
      : `${label} ${bannerCopy?.unlockedSuffix || "unlocked"}`;

  const body = (() => {
    if (stepPhase === "profile") {
      return isPhaseComplete
        ? bannerCopy?.profileComplete || "Your profile is saved. FINN can now guide the rest of the product flow around your preferences."
        : stepBodies?.profile || STEP_BODIES.profile;
    }
    if (stepPhase === "analysis") {
      return isPhaseComplete
        ? bannerCopy?.analysisComplete || "The first analysis basis is configured. FINN can now combine your asset and indicators into live context."
        : stepBodies?.[step] || STEP_BODIES[step] || `${bannerCopy?.finishPrefix || "Finish the current sub-step for"} ${STEP_LABELS[step] || "analysis"}.`;
    }
    if (stepPhase === "plan") {
      return isPhaseComplete
        ? bannerCopy?.planComplete || "Your setup and strategy are in place for the chosen asset."
        : stepBodies?.[step] || STEP_BODIES[step] || `${bannerCopy?.finishPrefix || "Finish the current sub-step for"} ${STEP_LABELS[step] || "planning"}.`;
    }
    return isPhaseComplete
      ? bannerCopy?.automationComplete || "Automation is configured. The final bot can stay paused until you deliberately activate it."
      : stepBodies?.[step] || STEP_BODIES[step] || `${bannerCopy?.finishPrefix || "Finish the current sub-step for"} ${STEP_LABELS[step] || "automation"}.`;
  })();

  const nextTaskLabel = missing.length > 0
    ? humanizeToken(missing[0])
    : STEP_LABELS[step] || stepPhase;

  return (
    <div className="mb-10 overflow-hidden rounded-[30px] border border-blue-100 bg-white shadow-[0_16px_50px_-35px_rgba(37,99,235,0.28)] dark:border-slate-800 dark:bg-[#0f172a]">
      <div className="border-b border-slate-100 px-6 py-5 dark:border-slate-800">
        <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_280px]">
          <div className="flex items-start gap-4">
            <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-blue-600 text-white shadow-lg shadow-blue-600/20">
              {isPhaseComplete ? <CheckCircle2 size={20} /> : <Icon size={20} />}
            </div>
            <div className="min-w-0">
              <div className="flex items-center gap-2 text-[10px] font-black uppercase tracking-[0.24em] text-blue-600 dark:text-blue-400">
                <Sparkles size={12} />
                {bannerCopy?.eyebrow || "Guided onboarding"}
              </div>
              <h3 className="mt-2 text-2xl font-black tracking-tight text-slate-950 dark:text-slate-50">
                {headline}
              </h3>
              <p className="mt-2 max-w-3xl text-sm font-medium leading-6 text-slate-500 dark:text-slate-400">
                {body}
              </p>
            </div>
          </div>

          <div className="rounded-[24px] border border-blue-100 bg-blue-50/70 p-5 dark:border-blue-900/40 dark:bg-blue-950/20">
            <div className="flex items-center justify-between gap-3">
              <div className="text-[10px] font-black uppercase tracking-[0.24em] text-blue-600 dark:text-blue-300">
                {bannerCopy?.progressLabel || "Progress"}
              </div>
              <div className="text-sm font-black text-blue-700 dark:text-blue-300">
                {completedPhaseCount}/{phaseOrder.length}
              </div>
            </div>
            <div className="mt-3 h-2 overflow-hidden rounded-full bg-blue-100 dark:bg-blue-950/40">
              <div
                className="h-full rounded-full bg-blue-600 transition-all"
                style={{ width: `${progressPercent}%` }}
              />
            </div>
            <div className="mt-4 text-[10px] font-black uppercase tracking-[0.24em] text-slate-500 dark:text-slate-400">
              {bannerCopy?.nextTaskLabel || "Do this now"}
            </div>
            <p className="mt-2 text-sm font-semibold leading-6 text-slate-700 dark:text-slate-200">
              {isPhaseComplete
                ? bannerCopy?.phaseReady || "This phase is stored. You can continue to the next guided step."
                : `${bannerCopy?.missingPrefix || "Missing"}: ${nextTaskLabel}`}
            </p>
            <Link
              href="/onboarding"
              className="mt-4 inline-flex items-center gap-2 text-[11px] font-black uppercase tracking-[0.2em] text-blue-700 transition hover:text-blue-800 dark:text-blue-300"
            >
              {bannerCopy?.viewCta || "View onboarding"}
              <ArrowRight size={13} />
            </Link>
          </div>
        </div>
      </div>

      <div className="grid gap-px bg-slate-100 dark:bg-slate-800 sm:grid-cols-4">
        {phaseOrder.map((phase, index) => {
          const phaseMeta = PHASE_META[phase];
          const PhaseIcon = phaseMeta.icon;
          const complete = Boolean(phaseStatus?.[phase]);
          const unlocked = Boolean(phaseUnlocks?.[phase]);
          const active = phase === stepPhase;

          return (
            <div key={phase} className="bg-white px-4 py-4 dark:bg-[#06101f]">
              <div className="flex items-center gap-3">
                <div
                  className={`flex h-10 w-10 items-center justify-center rounded-2xl ${
                    complete
                      ? "bg-emerald-100 text-emerald-700 dark:bg-emerald-950/30 dark:text-emerald-300"
                      : active
                        ? "bg-blue-600 text-white"
                        : unlocked
                          ? "bg-blue-50 text-blue-700 dark:bg-blue-950/20 dark:text-blue-300"
                          : "bg-slate-100 text-slate-400 dark:bg-slate-900 dark:text-slate-500"
                  }`}
                >
                  {complete ? <CheckCircle2 size={16} /> : <PhaseIcon size={16} />}
                </div>
                <div className="min-w-0">
                  <div className="text-[10px] font-black uppercase tracking-[0.2em] text-slate-400 dark:text-slate-500">
                    {index + 1}
                  </div>
                  <div className="text-sm font-black text-slate-950 dark:text-slate-50">{phaseMeta.label}</div>
                  <div className="text-[11px] font-semibold text-slate-500 dark:text-slate-400">
                    {complete
                      ? bannerCopy?.phaseDone || "Done"
                      : active
                        ? bannerCopy?.phaseCurrent || "Current"
                        : unlocked
                          ? bannerCopy?.phaseOpen || "Open"
                          : bannerCopy?.phaseLocked || "Locked"}
                  </div>
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
