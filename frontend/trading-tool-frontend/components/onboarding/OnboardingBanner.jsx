"use client";

import Link from "next/link";
import { useOnboarding } from "@/hooks/useOnboarding";
import { BarChart3, Globe, Activity, Wand2, Bot, Sparkles, User } from "lucide-react";

const ICONS = {
  profile: User,
  market: BarChart3,
  macro: Globe,
  technical: Activity,
  setup: Wand2,
  strategy: Bot,
};

const STEP_TEXT = {
  profile: {
    title: "Stap 1 van 6 — Jouw tradingprofiel",
    action: "Vertel eerst wat voor trader je bent, welke horizon je gebruikt en waar Finn op moet letten.",
    help: "Finn gebruikt dit om setups, uitleg en risico-waarschuwingen op jouw stijl af te stemmen.",
    unlocks: "Persoonlijkere coaching",
  },
  market: {
    title: "Stap 2 van 6 — Marktcontext",
    action: "Open de marktpagina en laat Finn eerst het actuele marktbeeld neerzetten.",
    help: "Zonder marktcontext blijft Finn te algemeen in zijn volgende adviezen.",
    unlocks: "Eerste marktbriefing",
  },
  macro: {
    title: "Stap 3 van 6 — Macrobeeld",
    action: "Voeg macrocontext toe zodat Finn regime en risico beter kan wegen.",
    help: "Denk aan DXY, yields of liquiditeit: Finn gebruikt dit voor het grotere plaatje.",
    unlocks: "Betere risico-inschatting",
  },
  technical: {
    title: "Stap 4 van 6 — Technische signalen",
    action: "Controleer technische signalen zodat Finn entries en timing beter kan beoordelen.",
    help: "Deze stap geeft Finn bewijs voor trend, momentum en timing.",
    unlocks: "Sterkere timing-uitleg",
  },
  setup: {
    title: "Stap 5 van 6 — Setup maken",
    action: "Maak je eerste setup zodat Finn jouw regels aan concrete situaties kan koppelen.",
    help: "Hier wordt Finn specifieker: niet alleen context, maar ook jouw voorkeuren.",
    unlocks: "Persoonlijkere reviews",
  },
  strategy: {
    title: "Stap 6 van 6 — Strategie kiezen",
    action: "Maak je eerste strategie zodat dashboard, reviews en reports echt bruikbaar worden.",
    help: "Na deze stap kan Finn je beslissingen veel beter reviewen en prioriteren.",
    unlocks: "Volledige reviewflow",
  },
};

export default function OnboardingBanner({ step }) {
  const { status, loading, onboardingComplete } = useOnboarding();

  const Icon = ICONS[step];
  const conf = STEP_TEXT[step];
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
              {isComplete ? "Stap afgerond" : "Aanbevolen volgende stap"}
            </span>
          </div>
          <h3 className="text-2xl font-black tracking-tight text-slate-900">
            {isComplete ? "Goed, deze stap staat" : conf.title}
          </h3>
          <p className="mt-2 max-w-xl text-[15px] font-medium leading-relaxed text-slate-600">
            {isComplete
              ? "Je kunt door naar de volgende stap of terug naar je onboarding-overzicht."
              : conf.action}
          </p>
          {!isComplete && (
            <>
              <p className="mt-3 text-sm font-semibold leading-relaxed text-slate-500">
                <span className="text-blue-600">Finn helpt:</span> {conf.help}
              </p>
              <div className="mt-3 inline-flex items-center gap-2 rounded-full border border-blue-100 bg-blue-50 px-3 py-1.5 text-[11px] font-bold text-blue-700">
                <Sparkles size={12} />
                Daarna ontgrendel je: {conf.unlocks}
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
          {isComplete ? "Terug naar overzicht →" : "Bekijk onboarding →"}
        </Link>
      </div>
    </div>
  );
}
