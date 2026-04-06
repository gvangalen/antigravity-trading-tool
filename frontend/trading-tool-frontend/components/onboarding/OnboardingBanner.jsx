"use client";

import Link from "next/link";
import { useOnboarding } from "@/hooks/useOnboarding";

import {
  BarChart3,
  Globe,
  Activity,
  Wand2,
  Bot,
} from "lucide-react";

// ------------------------------------------------------
// ICONS PER STEP
// ------------------------------------------------------
const ICONS = {
  market: BarChart3,
  macro: Globe,
  technical: Activity,
  setup: Wand2,
  strategy: Bot,
};

// ------------------------------------------------------
// TEKSTEN
// ------------------------------------------------------
const STEP_TEXT = {
  market: {
    title: "Stap 1 van 5 — Market data",
    action: "De tool moet jouw eerste automatische market-run uitvoeren.",
  },
  macro: {
    title: "Stap 2 van 5 — Macro data",
    action: "Voeg minstens één macro-indicator toe.",
  },
  technical: {
    title: "Stap 3 van 5 — Technische data",
    action: "Voeg minimaal één technische indicator toe.",
  },
  setup: {
    title: "Stap 4 van 5 — Setup aanmaken",
    action: "Maak minstens één setup aan om door te gaan.",
  },
  strategy: {
    title: "Stap 5 van 5 — Strategie genereren",
    action: "Genereer jouw eerste AI-strategie.",
  },
};

export default function OnboardingBanner({ step }) {
  const {
    status,
    loading,
    onboardingComplete,
  } = useOnboarding();

  // ⛔ Nog laden
  if (loading || !status) return null;

  // ⛔ Onboarding afgerond → geen banner
  if (onboardingComplete) return null;

  const Icon = ICONS[step];
  const conf = STEP_TEXT[step];

  if (!Icon || !conf) return null;

  return (
    <div className="w-full mb-6 rounded-xl border border-border bg-gradient-to-br from-blue-50/60 to-blue-100/40 dark:from-blue-950/50 dark:to-blue-900/40 shadow-sm p-5 relative overflow-hidden">
      <div className="absolute -top-10 -right-10 h-28 w-28 bg-blue-400/20 dark:bg-blue-300/10 rounded-full blur-3xl pointer-events-none" />

      <div className="flex items-center gap-4 relative z-10">
        <div className="p-3 rounded-lg bg-blue-500/10 dark:bg-blue-400/10 border border-blue-300/30 dark:border-blue-500/20">
          <Icon className="h-6 w-6 text-blue-600 dark:text-blue-300" />
        </div>

        <div className="flex-1">
          <h3 className="font-semibold text-lg text-blue-900 dark:text-blue-200">
            {conf.title}
          </h3>
          <p className="text-sm text-blue-800/80 dark:text-blue-200/70 mt-1">
            {conf.action}
          </p>
        </div>

        <Link
          href="/onboarding"
          className="px-4 py-2 rounded-md text-sm font-medium bg-blue-600 text-white hover:bg-blue-700 transition-all shadow-sm"
        >
          Onboarding →
        </Link>
      </div>
    </div>
  );
}
