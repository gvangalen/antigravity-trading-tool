"use client";

import Link from "next/link";
import { useEffect } from "react";
import { useRouter } from "next/navigation";
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
// TEXTS
// ------------------------------------------------------
const STEP_TEXT = {
  market: {
    title: "Step 1 of 5 — Market Data",
    action: "The system needs to execute your first automated market analysis.",
  },
  macro: {
    title: "Step 2 of 5 — Macro Data",
    action: "Add at least one macro indicator.",
  },
  technical: {
    title: "Step 3 of 5 — Technical Data",
    action: "Add at least one technical indicator.",
  },
  setup: {
    title: "Step 4 of 5 — Setup Configuration",
    action: "Create at least one setup to proceed.",
  },
  strategy: {
    title: "Step 5 of 5 — Strategy Generation",
    action: "Generate your first AI-driven strategy.",
  },
};

export default function OnboardingBanner({ step }) {
  const {
    status,
    loading,
    onboardingComplete,
  } = useOnboarding();

  const Icon = ICONS[step];
  const conf = STEP_TEXT[step];

  const router = useRouter();
  const isComplete = status?.[`has_${step}`];


  if (loading || !status) return null;
  if (onboardingComplete) return null;
  if (!Icon || !conf) return null;

  return (
    <div className={`w-full mb-12 rounded-3xl border-2 transition-all duration-500 relative overflow-hidden group shadow-2xl ${isComplete ? 'border-emerald-500/30 bg-emerald-500/[0.02]' : 'border-blue-600/20 bg-[#0f172a]'}`}>
      {/* ✨ BACKGROUND GLOW */}
      <div className={`absolute top-0 right-0 w-64 h-64 blur-[100px] pointer-events-none transition-colors ${isComplete ? 'bg-emerald-500/10' : 'bg-blue-600/5 group-hover:bg-blue-600/10'}`} />
      
      <div className="flex flex-col md:flex-row items-center gap-8 p-8 relative z-10">
        <div className={`p-5 rounded-2xl shadow-xl transition-all duration-500 ${isComplete ? 'bg-emerald-500 shadow-emerald-500/20' : 'bg-blue-600 shadow-blue-600/20'}`}>
          <Icon className="h-8 w-8 text-white" />
        </div>

        <div className="flex-1 text-center md:text-left">
          <div className="flex items-center gap-3 justify-center md:justify-start mb-2">
            <div className={`w-1.5 h-1.5 rounded-full ${isComplete ? 'bg-emerald-400' : 'bg-blue-400 animate-pulse'}`} />
            <span className={`text-[10px] font-black uppercase tracking-[0.3em] ${isComplete ? 'text-emerald-500' : 'text-blue-400'}`}>
              {isComplete ? 'System Stabilized • Mission Successful' : 'Protocol Active • AI Pilot Online'}
            </span>
          </div>
          <h3 className="text-2xl font-black text-slate-100 tracking-tight">
            {isComplete ? 'Step Initialized' : conf.title}
          </h3>
          <p className="text-[15px] font-medium text-slate-400 mt-2 max-w-xl">
            {isComplete 
              ? `Success. Data-stream for ${step} is now established. Returning to Launch Center...` 
              : conf.action} 
            {!isComplete && <span className="text-blue-500 italic">Consult the AI Assistant for mission-specific guidance.</span>}
          </p>
        </div>

        <Link
          href="/onboarding"
          className={`w-full md:w-auto px-10 py-5 rounded-2xl text-[11px] font-black uppercase tracking-[0.2em] transition-all shadow-xl active:scale-95 whitespace-nowrap text-center ${
            isComplete 
              ? 'bg-emerald-500 text-white hover:bg-emerald-600 shadow-emerald-500/20' 
              : 'bg-blue-600 text-white hover:bg-blue-700 shadow-blue-600/20'
          }`}
        >
          {isComplete ? 'Return Now →' : 'Return to Launch Center →'}
        </Link>
      </div>
    </div>
  );
}
