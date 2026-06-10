"use client";

import { useEffect, useMemo } from "react";
import { useRouter } from "next/navigation";
import { 
  CheckCircle2, 
  Circle, 
  Lock, 
  ArrowRight, 
  Activity, 
  Globe, 
  LineChart, 
  Zap, 
  Bot,
  Terminal,
  Cpu,
  Rocket
} from "lucide-react";
import { useOnboarding } from "@/hooks/useOnboarding";
import { trackAssistantEvent } from "@/lib/api/assistantAnalytics";

export default function OnboardingPage() {
  const router = useRouter();
  const {
    status,
    loading,
    saving,
    onboardingComplete,
    allowedSteps,
  } = useOnboarding();

  useEffect(() => {
    if (loading || !status) return;
    const stepsComplete = [
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
      <div className="flex items-center justify-center min-h-[60vh]">
        <div className="flex flex-col items-center gap-4">
          <div className="w-12 h-12 border-4 border-blue-600/30 border-t-blue-600 rounded-full animate-spin" />
          <p className="text-xs font-black uppercase tracking-[0.2em] text-slate-500">Initializing System...</p>
        </div>
      </div>
    );
  }

  /* ⭐ Step Icons Map */
  const ICONS = {
    market: Globe,
    macro: Activity,
    technical: LineChart,
    setup: Zap,
    strategy: Bot,
  };

  const steps = [
    {
      key: "market",
      title: "Market Intelligence",
      description: "Establishing live feed from global price & volume indices.",
      done: status.has_market,
      link: "/market",
      unlocked: allowedSteps.market,
    },
    {
      key: "macro",
      title: "Macro Environment",
      description: "Calibrating DXY, Bond Yields, and Liquidity benchmarks.",
      done: status.has_macro,
      link: "/macro",
      unlocked: allowedSteps.macro,
    },
    {
      key: "technical",
      title: "Technical Matrix",
      description: "Initializing RSI, Momentum, and Structural volatility maps.",
      done: status.has_technical,
      link: "/technical",
      unlocked: allowedSteps.technical,
    },
    {
      key: "setup",
      title: "Core Setups",
      description: "Configuring entry clusters and risk management parameters.",
      done: status.has_setup,
      link: "/setup",
      unlocked: allowedSteps.setup,
    },
    {
      key: "strategy",
      title: "Strategy Engine",
      description: "Generating AI-driven execution models based on your setup.",
      done: status.has_strategy,
      link: "/strategy",
      unlocked: allowedSteps.strategy,
    },
  ];

  /* Calculation for progress ring */
  const completedCount = steps.filter(s => s.done).length;
  const progressPercent = (completedCount / steps.length) * 100;

  return (
    <div className="max-w-4xl mx-auto py-8 animate-fade-in relative z-10">
      
      {/* 🚀 HUB HEADER */}
      <div className="mb-16 flex flex-col md:flex-row items-center gap-12">
        {/* PROGRESS RING */}
        <div className="relative w-48 h-48 group">
          <div className="absolute inset-0 bg-blue-600/10 rounded-full blur-2xl group-hover:bg-blue-600/20 transition-all" />
          <svg className="w-full h-full -rotate-90">
            <circle
              cx="96"
              cy="96"
              r="80"
              stroke="currentColor"
              strokeWidth="4"
              fill="transparent"
              className="text-slate-900"
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
              className="text-blue-600 drop-shadow-[0_0_8px_rgba(37,99,235,0.5)] transition-all duration-1000 ease-out"
              strokeLinecap="round"
            />
          </svg>
          <div className="absolute inset-x-0 inset-y-0 flex flex-col items-center justify-center">
            <span className="text-4xl font-black tracking-tight">{Math.round(progressPercent)}%</span>
            <span className="text-[10px] font-bold uppercase tracking-[0.2em] text-slate-500">Initialized</span>
            
            {/* 🚩 NEXT MILESTONE LABEL */}
            {!onboardingComplete && (
               <div className="absolute top-[180px] w-max animate-pulse">
                  <p className="text-[9px] font-black uppercase tracking-[0.3em] text-blue-600/60">
                     Next Milestone: <span className="text-blue-500">{steps.find(s => !s.done)?.title || 'Complete Protocol'}</span>
                  </p>
               </div>
            )}
          </div>
        </div>

        <div className="flex-1 text-center md:text-left">
           <div className="flex items-center gap-3 justify-center md:justify-start mb-4">
              <Terminal size={14} className="text-blue-600" />
              <span className="text-[12px] font-black uppercase tracking-[0.3em] text-blue-600">System Core Ready</span>
           </div>
           <h2 className="text-4xl font-black tracking-tight mb-4">System Initialization</h2>
           <p className="text-slate-400 font-medium max-w-lg leading-relaxed">
             Establish your core data streams to unlock the Live Trading Cockpit. 
             Once the protocol is complete, your dashboard will immediately populate 
             with real-time AI signals and market intelligence.
           </p>
        </div>
      </div>

      {/* 🧱 SYSTEM MODULES GRID */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {steps.map((step, idx) => {
          const Icon = ICONS[step.key];
          const isDone = !!step.done;
          const isUnlocked = !!step.unlocked;

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
              className={`
                group relative p-8 rounded-3xl border-2 transition-all duration-300 overflow-hidden cursor-pointer
                ${isDone 
                  ? "border-emerald-500/20 bg-emerald-500/[0.02]" 
                  : isUnlocked 
                    ? "border-slate-800 bg-[#0f172a] hover:border-blue-600/50 hover:bg-[#11192d] hover:shadow-2xl hover:shadow-blue-600/10" 
                    : "border-slate-800 opacity-40 grayscale cursor-not-allowed"
                }
              `}
            >
              {/* STATUS LABEL */}
              <div className="absolute top-8 right-8 flex items-center gap-2">
                <div className={`w-1.5 h-1.5 rounded-full ${isDone ? 'bg-emerald-500' : isUnlocked ? 'bg-blue-600 animate-pulse' : 'bg-slate-700'}`} />
                <span className={`text-[9px] font-black uppercase tracking-[0.2em] ${isDone ? 'text-emerald-500' : isUnlocked ? 'text-blue-600' : 'text-slate-600'}`}>
                  {isDone ? 'ACTIVE' : isUnlocked ? 'READY' : 'ENCRYPTED'}
                </span>
              </div>

              {/* MODULE CONTENT */}
              <div className="relative z-10">
                <div className={`p-4 w-fit rounded-2xl mb-6 shadow-xl border ${isDone ? 'bg-emerald-500/10 border-emerald-500/20' : 'bg-slate-900 border-slate-800'}`}>
                   <Icon className={`w-6 h-6 ${isDone ? 'text-emerald-500' : 'text-blue-600'}`} />
                </div>
                
                <h3 className="text-xl font-black tracking-tight mb-3">
                  {step.title}
                </h3>
                <p className="text-sm font-medium text-slate-500 leading-relaxed mb-8 max-w-[200px]">
                  {step.description}
                </p>

                <div className="flex items-center gap-3">
                   {isDone ? (
                     <div className="flex items-center gap-2 text-emerald-500">
                        <CheckCircle2 size={16} />
                        <span className="text-[10px] font-black uppercase tracking-widest">Initialization Complete</span>
                     </div>
                   ) : isUnlocked ? (
                     <div className="btn-v2-primary py-3 px-6 rounded-xl flex items-center gap-2 group/btn">
                        <span className="text-[10px] font-black uppercase tracking-widest">Initiate Step</span>
                        <ArrowRight size={14} className="group-hover/btn:translate-x-1 transition-transform" />
                     </div>
                   ) : (
                     <div className="flex items-center gap-2 text-slate-600">
                        <Lock size={14} />
                        <span className="text-[10px] font-black uppercase tracking-widest leading-none">Complete {steps[idx-1]?.title || 'previous step'} to unlock</span>
                     </div>
                   )}
                </div>
              </div>

              {/* DYNAMIC BG GLOW */}
              <div className={`absolute bottom-0 right-0 w-32 h-32 blur-[80px] pointer-events-none transition-opacity duration-500 ${isDone ? 'bg-emerald-500/10 opacity-100' : isUnlocked ? 'bg-blue-600/10 opacity-40 group-hover:opacity-100' : 'opacity-0'}`} />
            </div>
          );
        })}
      </div>

      {/* FOOTER ACTION */}
      {onboardingComplete && (
         <div className="mt-16 animate-slide-up">
            <div className="p-10 rounded-3xl bg-emerald-500/5 border-2 border-emerald-500/20 flex flex-col md:flex-row items-center justify-between gap-8">
               <div className="flex items-center gap-6">
                  <div className="p-4 bg-emerald-500 rounded-2xl shadow-2xl shadow-emerald-500/30">
                     <Rocket className="w-8 h-8 text-white" />
                  </div>
                  <div>
                     <h2 className="text-2xl font-black tracking-tight mb-1">Final Authorization Complete</h2>
                     <p className="text-emerald-500/60 font-medium text-sm">System ready for live operation.</p>
                  </div>
               </div>
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
                 className="w-full md:w-auto px-10 py-5 bg-emerald-500 hover:bg-emerald-600 text-white font-black uppercase tracking-[0.2em] text-xs rounded-2xl shadow-xl shadow-emerald-500/20 active:scale-95 transition-all text-center"
               >
                 Activate Dashboard →
               </button>
            </div>
         </div>
      )}
    </div>
  );
}
