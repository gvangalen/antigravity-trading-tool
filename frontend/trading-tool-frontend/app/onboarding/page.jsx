"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useTranslation } from "@/app/providers/I18nProvider";
import {
  CheckCircle2,
  Lock,
  ArrowRight,
  Activity,
  Globe,
  LineChart,
  Zap,
  Bot,
  Sparkles,
  LayoutDashboard,
  FileText,
  ShieldCheck,
  TimerReset,
  Shield,
  TrendingUp,
  User,
} from "lucide-react";
import { useOnboarding } from "@/hooks/useOnboarding";
import { trackAssistantEvent } from "@/lib/api/assistantAnalytics";

const ICONS = {
  profile: User,
  market: Globe,
  macro: Activity,
  technical: LineChart,
  setup: Zap,
  strategy: Bot,
};

export default function OnboardingPage() {
  const router = useRouter();
  const { t } = useTranslation();
  const { status, loading, onboardingComplete, allowedSteps } = useOnboarding();

  useEffect(() => {
    if (loading || !status) return;
    const stepsComplete = [
      status.has_profile,
      status.has_market,
      status.has_macro,
      status.has_technical,
      status.has_setup,
      status.has_strategy,
    ].filter(Boolean).length;

    trackAssistantEvent({
      event_name: "screen_view",
      page: "/onboarding",
      surface: "web",
      flow_type: "onboarding",
      metadata: {
        onboarding_complete: Boolean(onboardingComplete),
        steps_complete: stepsComplete,
      },
    });
  }, [loading, status, onboardingComplete]);

  if (loading || !status) {
    return (
      <div className="flex min-h-[60vh] items-center justify-center">
        <div className="flex flex-col items-center gap-4">
          <div className="h-12 w-12 animate-spin rounded-full border-4 border-blue-600/30 border-t-blue-600" />
          <p className="text-xs font-black uppercase tracking-[0.2em] text-slate-500">
            {t?.traderProfile?.onboardingOverview?.loading}
          </p>
        </div>
      </div>
    );
  }

  const stepText = t?.traderProfile?.onboardingOverview?.steps || {};
  const statusText = t?.traderProfile?.onboardingOverview?.status || {};

  const steps = [
    {
      key: "profile",
      title: stepText?.profile?.title,
      description: stepText?.profile?.description,
      finnHelp: stepText?.profile?.finnHelp,
      unlocks: stepText?.profile?.unlocks,
      done: status.has_profile,
      link: "/onboarding/profile",
      unlocked: allowedSteps.profile,
    },
    {
      key: "market",
      title: stepText?.market?.title,
      description: stepText?.market?.description,
      finnHelp: stepText?.market?.finnHelp,
      unlocks: stepText?.market?.unlocks,
      done: status.has_market,
      link: "/market",
      unlocked: allowedSteps.market,
    },
    {
      key: "macro",
      title: stepText?.macro?.title,
      description: stepText?.macro?.description,
      finnHelp: stepText?.macro?.finnHelp,
      unlocks: stepText?.macro?.unlocks,
      done: status.has_macro,
      link: "/macro",
      unlocked: allowedSteps.macro,
    },
    {
      key: "technical",
      title: stepText?.technical?.title,
      description: stepText?.technical?.description,
      finnHelp: stepText?.technical?.finnHelp,
      unlocks: stepText?.technical?.unlocks,
      done: status.has_technical,
      link: "/technical",
      unlocked: allowedSteps.technical,
    },
    {
      key: "setup",
      title: stepText?.setup?.title,
      description: stepText?.setup?.description,
      finnHelp: stepText?.setup?.finnHelp,
      unlocks: stepText?.setup?.unlocks,
      done: status.has_setup,
      link: "/setup",
      unlocked: allowedSteps.setup,
    },
    {
      key: "strategy",
      title: stepText?.strategy?.title,
      description: stepText?.strategy?.description,
      finnHelp: stepText?.strategy?.finnHelp,
      unlocks: stepText?.strategy?.unlocks,
      done: status.has_strategy,
      link: "/strategy",
      unlocked: allowedSteps.strategy,
    },
  ];

  const completedCount = steps.filter((step) => step.done).length;
  const progressPercent = (completedCount / steps.length) * 100;
  const nextStep = steps.find((step) => !step.done) || null;

  return (
    <div className="relative z-10 mx-auto max-w-5xl py-8 animate-fade-in">
      <div className="mb-16 flex flex-col items-center gap-12 md:flex-row">
        <div className="group relative h-48 w-48">
          <div className="absolute inset-0 rounded-full bg-blue-600/10 blur-2xl transition-all group-hover:bg-blue-600/20" />
          <svg className="h-full w-full -rotate-90">
            <circle
              cx="96"
              cy="96"
              r="80"
              stroke="currentColor"
              strokeWidth="4"
              fill="transparent"
              className="text-slate-200"
            />
            <circle
              cx="96"
              cy="96"
              r="80"
              stroke="currentColor"
              strokeWidth="8"
              fill="transparent"
              strokeDasharray={502.4}
              strokeDashoffset={502.4 - (502.4 * progressPercent) / 100}
              className="text-blue-600 drop-shadow-[0_0_8px_rgba(37,99,235,0.25)] transition-all duration-1000 ease-out"
              strokeLinecap="round"
            />
          </svg>
          <div className="absolute inset-0 flex flex-col items-center justify-center">
            <span className="text-4xl font-black tracking-tight text-slate-900">
              {Math.round(progressPercent)}%
            </span>
            <span className="text-[10px] font-bold uppercase tracking-[0.2em] text-slate-500">
              {statusText?.done}
            </span>
            {!onboardingComplete && (
              <div className="absolute top-[180px] w-max animate-pulse">
                <p className="text-[9px] font-black uppercase tracking-[0.3em] text-blue-600/60">
                  {t?.traderProfile?.onboardingOverview?.nextStep}{" "}
                  <span className="text-blue-500">{nextStep?.title || "Dashboard"}</span>
                </p>
              </div>
            )}
          </div>
        </div>

        <div className="flex-1 text-center md:text-left">
          <div className="mb-4 flex items-center justify-center gap-3 md:justify-start">
            <Sparkles size={14} className="text-blue-600" />
            <span className="text-[12px] font-black uppercase tracking-[0.3em] text-blue-600">
              {t?.traderProfile?.onboardingOverview?.finnLabel}
            </span>
          </div>
          <h2 className="mb-4 text-4xl font-black tracking-tight text-slate-900">
            {t?.traderProfile?.onboardingOverview?.title}
          </h2>
          <p className="max-w-2xl text-slate-500 font-medium leading-relaxed">
            {t?.traderProfile?.onboardingOverview?.description}
          </p>

          <div className="mt-5 flex flex-wrap gap-2 text-[11px] font-bold">
            <span className="inline-flex items-center gap-2 rounded-full border border-slate-200 bg-white px-3 py-1.5 text-slate-700 shadow-sm">
              <TimerReset size={12} />
              {t?.traderProfile?.onboardingOverview?.chips?.duration}
            </span>
            <span className="inline-flex items-center gap-2 rounded-full border border-slate-200 bg-white px-3 py-1.5 text-slate-700 shadow-sm">
              <Shield size={12} />
              {t?.traderProfile?.onboardingOverview?.chips?.noLiveTrades}
            </span>
            <span className="inline-flex items-center gap-2 rounded-full border border-slate-200 bg-white px-3 py-1.5 text-slate-700 shadow-sm">
              <Sparkles size={12} />
              {t?.traderProfile?.onboardingOverview?.chips?.finnHelps}
            </span>
          </div>

          <div className="mt-6 rounded-2xl border border-blue-100 bg-blue-50 px-5 py-4 text-left shadow-sm">
            <div className="flex items-center gap-2 text-[10px] font-black uppercase tracking-[0.2em] text-blue-600">
              <Sparkles size={14} />
              {t?.traderProfile?.onboardingOverview?.finnLabel}
            </div>
            <p className="mt-2 text-sm font-semibold leading-relaxed text-slate-700">
              {onboardingComplete
                ? t?.traderProfile?.onboardingOverview?.finnComplete
                : `${nextStep?.title || ""} ${nextStep?.finnHelp || ""}`}
            </p>
          </div>
        </div>
      </div>

      {!onboardingComplete && nextStep && (
        <div className="mb-10 rounded-3xl border border-slate-200 bg-white p-6 shadow-sm">
          <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
            <div>
              <div className="text-[10px] font-black uppercase tracking-[0.25em] text-slate-500">
                {t?.traderProfile?.onboardingOverview?.recommendedRoute}
              </div>
              <h3 className="mt-2 text-2xl font-black tracking-tight text-slate-900">{nextStep.title}</h3>
              <p className="mt-2 max-w-2xl text-sm font-medium leading-relaxed text-slate-500">
                {nextStep.description}
              </p>
              <div className="mt-3 inline-flex items-center gap-2 rounded-full border border-blue-100 bg-blue-50 px-3 py-1.5 text-[11px] font-bold text-blue-700">
                <TrendingUp size={12} />
                {t?.traderProfile?.onboardingOverview?.unlocksPrefix} {nextStep.unlocks}
              </div>
            </div>
            <button
              onClick={() => router.push(nextStep.link)}
              className="inline-flex items-center justify-center gap-2 rounded-2xl bg-blue-600 px-5 py-3 text-[11px] font-black uppercase tracking-[0.18em] text-white shadow-lg shadow-blue-500/20 transition hover:bg-blue-700 active:scale-95"
            >
              {t?.traderProfile?.onboardingOverview?.openStep}
              <ArrowRight size={14} />
            </button>
          </div>
        </div>
      )}

      <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
        {steps.map((step, idx) => {
          const Icon = ICONS[step.key];
          const isDone = !!step.done;
          const isUnlocked = !!step.unlocked;
          const isRecommended = step.key === nextStep?.key;

          return (
            <div
              key={step.key}
              onClick={() => {
                if (!isUnlocked) return;
                trackAssistantEvent({
                  event_name: "onboarding_step_clicked",
                  page: "/onboarding",
                  surface: "web",
                  flow_type: "onboarding",
                  action_type: step.key,
                  metadata: {
                    done: isDone,
                    target_page: step.link,
                    title: step.title,
                  },
                });
                router.push(step.link);
              }}
              className={`group relative cursor-pointer overflow-hidden rounded-3xl border-2 p-8 transition-all duration-300 ${
                isDone
                  ? "border-emerald-500/20 bg-emerald-500/[0.02]"
                  : isUnlocked
                    ? isRecommended
                      ? "border-blue-200 bg-white shadow-lg shadow-blue-500/10 hover:border-blue-300"
                      : "border-slate-200 bg-white hover:border-blue-200 hover:shadow-xl hover:shadow-blue-500/5"
                    : "cursor-not-allowed border-slate-200 bg-slate-50 opacity-60"
              }`}
            >
              <div className="absolute right-8 top-8 flex items-center gap-2">
                <div
                  className={`h-1.5 w-1.5 rounded-full ${
                    isDone ? "bg-emerald-500" : isUnlocked ? "animate-pulse bg-blue-600" : "bg-slate-400"
                  }`}
                />
                <span
                  className={`text-[9px] font-black uppercase tracking-[0.2em] ${
                    isDone ? "text-emerald-500" : isUnlocked ? "text-blue-600" : "text-slate-500"
                  }`}
                >
                  {isDone
                    ? statusText?.done
                    : isUnlocked
                      ? (isRecommended ? statusText?.recommended : statusText?.available)
                      : statusText?.locked}
                </span>
              </div>

              <div className="relative z-10">
                <div
                  className={`mb-6 w-fit rounded-2xl border p-4 shadow-sm ${
                    isDone
                      ? "border-emerald-500/20 bg-emerald-500/10"
                      : isUnlocked
                        ? "border-blue-100 bg-blue-50"
                        : "border-slate-200 bg-white"
                  }`}
                >
                  <Icon className={`h-6 w-6 ${isDone ? "text-emerald-500" : isUnlocked ? "text-blue-600" : "text-slate-400"}`} />
                </div>

                <h3 className="mb-3 text-xl font-black tracking-tight text-slate-900">{step.title}</h3>
                <p className="mb-4 max-w-[340px] text-sm font-medium leading-relaxed text-slate-500">
                  {step.description}
                </p>
                <p className="mb-8 text-[13px] font-semibold leading-relaxed text-slate-600">
                  <span className="text-blue-600">Finn helpt:</span> {step.finnHelp}
                </p>

                <div className="mb-8 flex flex-wrap gap-2">
                  <span className="rounded-full border border-slate-200 bg-slate-50 px-3 py-1.5 text-[10px] font-bold uppercase tracking-[0.14em] text-slate-600">
                    Ontgrendelt
                  </span>
                  <span className="rounded-full border border-blue-100 bg-blue-50 px-3 py-1.5 text-[11px] font-bold text-blue-700">
                    {step.unlocks}
                  </span>
                </div>

                <div className="flex items-center gap-3">
                  {isDone ? (
                    <div className="flex items-center gap-2 text-emerald-500">
                      <CheckCircle2 size={16} />
                      <span className="text-[10px] font-black uppercase tracking-widest">Stap afgerond</span>
                    </div>
                  ) : isUnlocked ? (
                    <div className="rounded-xl bg-blue-600 px-5 py-3 text-white shadow-md transition group-hover:bg-blue-700">
                      <div className="flex items-center gap-2">
                        <span className="text-[10px] font-black uppercase tracking-widest">Open stap</span>
                        <ArrowRight size={14} className="transition-transform group-hover:translate-x-1" />
                      </div>
                    </div>
                  ) : (
                    <div className="flex items-center gap-2 text-slate-500">
                      <Lock size={14} />
                      <span className="text-[10px] font-black uppercase tracking-widest leading-none">
                        Rond eerst {steps[idx - 1]?.title || "de vorige stap"} af
                      </span>
                    </div>
                  )}
                </div>
              </div>

              <div
                className={`pointer-events-none absolute bottom-0 right-0 h-32 w-32 blur-[80px] transition-opacity duration-500 ${
                  isDone
                    ? "bg-emerald-500/10 opacity-100"
                    : isUnlocked
                      ? "bg-blue-600/10 opacity-40 group-hover:opacity-100"
                      : "opacity-0"
                }`}
              />
            </div>
          );
        })}
      </div>

      {onboardingComplete && (
        <div className="mt-10 rounded-3xl border border-emerald-200 bg-emerald-50 p-6 shadow-sm">
          <div className="flex flex-col gap-5 md:flex-row md:items-start md:justify-between">
            <div className="max-w-2xl">
              <div className="flex items-center gap-2 text-[10px] font-black uppercase tracking-[0.22em] text-emerald-600">
                <ShieldCheck size={14} />
                Basis staat
              </div>
              <h3 className="mt-2 text-2xl font-black tracking-tight text-slate-900">
                Je kunt nu echt met Tradamind werken
              </h3>
              <p className="mt-2 text-sm font-medium leading-relaxed text-slate-600">
                Je onboarding is klaar. Open nu je dashboard voor het totaalbeeld, bekijk je report
                voor samenvatting en vraag Finn om je eerste concrete volgende stap.
              </p>
              <div className="mt-4 flex flex-wrap gap-2 text-[11px] font-bold">
                <span className="rounded-full border border-emerald-200 bg-white px-3 py-1.5 text-emerald-700">
                  Dashboard openen
                </span>
                <span className="rounded-full border border-emerald-200 bg-white px-3 py-1.5 text-emerald-700">
                  Report lezen
                </span>
                <span className="rounded-full border border-emerald-200 bg-white px-3 py-1.5 text-emerald-700">
                  Vraag Finn om je volgende stap
                </span>
              </div>
            </div>
            <div className="flex flex-wrap gap-3">
              <button
                onClick={() => {
                  trackAssistantEvent({
                    event_name: "onboarding_dashboard_activated",
                    page: "/onboarding",
                    surface: "web",
                    flow_type: "first_session",
                    action_type: "activate_dashboard",
                  });
                  router.push("/dashboard");
                }}
                className="inline-flex items-center gap-2 rounded-2xl bg-slate-900 px-5 py-3 text-[11px] font-black uppercase tracking-[0.18em] text-white shadow-md transition hover:bg-slate-800"
              >
                <LayoutDashboard size={14} />
                Dashboard
              </button>
              <button
                onClick={() => router.push("/report")}
                className="inline-flex items-center gap-2 rounded-2xl border border-slate-200 bg-white px-5 py-3 text-[11px] font-black uppercase tracking-[0.18em] text-slate-700 shadow-sm transition hover:border-slate-300"
              >
                <FileText size={14} />
                Report
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
