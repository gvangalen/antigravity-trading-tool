"use client";

import Link from "next/link";
import { useTranslation } from "@/app/providers/I18nProvider";
import { useOnboarding } from "@/hooks/useOnboarding";
import { BarChart3, Globe, Activity, Wand2, Bot, Sparkles, User, Coins } from "lucide-react";

const ICONS = {
  profile: User,
  asset: Coins,
  market: BarChart3,
  macro: Globe,
  technical: Activity,
  setup: Wand2,
  strategy: Bot,
  bot: Bot,
};

export default function OnboardingBanner({ step }) {
  const { t } = useTranslation();
  const { status, loading, onboardingComplete } = useOnboarding();

  const Icon = ICONS[step];
  const bannerConf = t?.traderProfile?.banner?.steps?.[step];
  const overviewConf = t?.traderProfile?.onboardingOverview?.steps?.[step];
  const conf = {
    title: overviewConf?.title || bannerConf?.title,
    action: bannerConf?.action || overviewConf?.description,
    help: bannerConf?.help || overviewConf?.finnHelp,
    unlocks: overviewConf?.unlocks || bannerConf?.unlocks,
  };
  const isComplete = status?.[`has_${step}`];

  if (loading || !status || onboardingComplete || !Icon || !conf) return null;

  return (
    <div
      className={`group relative mb-12 w-full overflow-hidden rounded-3xl border transition-all duration-500 shadow-sm ${
        isComplete ? "border-emerald-200 bg-emerald-50" : "border-blue-100 bg-white"
      }`}
    >
      <div
        className={`pointer-events-none absolute right-0 top-0 h-64 w-64 blur-[100px] transition-colors ${
          isComplete ? "bg-emerald-500/10" : "bg-blue-600/5 group-hover:bg-blue-600/10"
        }`}
      />

      <div className="relative z-10 flex flex-col items-center gap-8 p-8 md:flex-row">
        <div
          className={`rounded-2xl p-5 shadow-sm transition-all duration-500 ${
            isComplete ? "bg-emerald-500 shadow-emerald-500/20" : "bg-blue-600 shadow-blue-600/10"
          }`}
        >
          <Icon className="h-8 w-8 text-white" />
        </div>

        <div className="flex-1 text-center md:text-left">
          <div className="mb-2 flex items-center justify-center gap-3 md:justify-start">
            <div className={`h-1.5 w-1.5 rounded-full ${isComplete ? "bg-emerald-400" : "animate-pulse bg-blue-400"}`} />
                <span className={`text-[10px] font-black uppercase tracking-[0.3em] ${isComplete ? "text-emerald-600" : "text-blue-600"}`}>
              {isComplete ? t?.traderProfile?.banner?.completeLabel : t?.traderProfile?.banner?.recommendedLabel}
                </span>
          </div>
          <h3 className="text-2xl font-black tracking-tight text-slate-900">
            {isComplete ? t?.traderProfile?.banner?.completeTitle : conf?.title}
          </h3>
          <p className="mt-2 max-w-xl text-[15px] font-medium leading-relaxed text-slate-600">
            {isComplete
              ? t?.traderProfile?.banner?.completeBody
              : conf?.action}
          </p>
          {!isComplete && (
            <>
              <p className="mt-3 text-sm font-semibold leading-relaxed text-slate-500">
                <span className="text-blue-600">{t?.traderProfile?.banner?.finnHelps}</span> {conf?.help}
              </p>
              <div className="mt-3 inline-flex items-center gap-2 rounded-full border border-blue-100 bg-blue-50 px-3 py-1.5 text-[11px] font-bold text-blue-700">
                <Sparkles size={12} />
                {t?.traderProfile?.banner?.unlocksPrefix} {conf?.unlocks}
              </div>
            </>
          )}
        </div>

        <Link
          href="/onboarding"
          className={`w-full whitespace-nowrap rounded-2xl px-10 py-5 text-center text-[11px] font-black uppercase tracking-[0.2em] shadow-sm transition-all active:scale-95 md:w-auto ${
            isComplete
              ? "bg-emerald-500 text-white hover:bg-emerald-600 shadow-emerald-500/20"
              : "bg-blue-600 text-white hover:bg-blue-700 shadow-blue-600/20"
          }`}
        >
          {isComplete ? t?.traderProfile?.banner?.backToOverviewCta : t?.traderProfile?.banner?.overviewCta}
        </Link>
      </div>
    </div>
  );
}
