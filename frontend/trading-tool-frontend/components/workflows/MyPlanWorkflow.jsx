"use client";

import { useMemo } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Activity, ChevronRight, Layers, Sparkles } from "lucide-react";

import SetupsWorkspaceSection from "@/components/my-plan/SetupsWorkspaceSection";
import StrategiesWorkspaceSection from "@/components/my-plan/StrategiesWorkspaceSection";

const STEP_ORDER = ["setup", "strategy"];

function resolveActiveStep({ pathname, searchParams, initialStep = "setup" }) {
  const explicitStep = searchParams.get("step");
  if (STEP_ORDER.includes(explicitStep)) {
    return explicitStep;
  }

  if (pathname === "/strategy") return "strategy";
  if (pathname === "/setup") return "setup";

  return initialStep;
}

function buildStepHref(stepId, symbol) {
  const safeSymbol = encodeURIComponent(symbol || "BTC");

  if (stepId === "strategy") {
    return `/strategy?symbol=${safeSymbol}&step=strategy`;
  }

  return `/setup?symbol=${safeSymbol}&step=setup`;
}

function getStepMeta(symbol) {
  return {
    setup: {
      id: "setup",
      label: "Setups",
      icon: Layers,
      eyebrow: "Step 1",
      description: `Define setup logic, filters and market frameworks for ${symbol}.`,
    },
    strategy: {
      id: "strategy",
      label: "Strategies",
      icon: Activity,
      eyebrow: "Step 2",
      description: `Combine setups into executable strategy routines for ${symbol}.`,
    },
  };
}

export default function MyPlanWorkflow({ initialStep = "setup", symbol = "BTC" }) {
  const pathname = usePathname();
  const router = useRouter();
  const searchParams = useSearchParams();
  const activeSymbol = String(searchParams.get("symbol") || symbol || "BTC").toUpperCase();
  const activeStep = resolveActiveStep({ pathname, searchParams, initialStep });
  const stepMeta = useMemo(() => getStepMeta(activeSymbol), [activeSymbol]);

  const handleStepNavigation = (stepId) => {
    router.push(buildStepHref(stepId, activeSymbol), { scroll: false });
  };

  return (
    <div className="space-y-6">
      <section className="rounded-[28px] border border-slate-200/80 bg-white p-5 shadow-[0_18px_50px_-40px_rgba(15,23,42,0.28)] dark:border-slate-800 dark:bg-[#0f172a] lg:p-6">
        <div className="mb-5 flex flex-col gap-4 border-b border-slate-100 pb-5 dark:border-slate-800">
          <div className="text-[10px] font-black uppercase tracking-[0.28em] text-blue-600 dark:text-blue-400">
            Shared Workflow
          </div>
          <div className="flex flex-col gap-4 xl:flex-row xl:items-end xl:justify-between">
            <div>
              <h3 className="text-2xl font-black tracking-tight text-slate-950 dark:text-slate-50">
                Mijn Plan Workflow
              </h3>
              <p className="mt-1 text-sm font-medium text-slate-500 dark:text-slate-400">
                One workflow across setups and strategies so your plan stays in one place.
              </p>
            </div>
            <div className="inline-flex items-center gap-2 self-start rounded-full border border-emerald-200 bg-emerald-50 px-3 py-1.5 text-[10px] font-black uppercase tracking-[0.2em] text-emerald-700 dark:border-emerald-900/50 dark:bg-emerald-950/20 dark:text-emerald-300">
              <span className="h-2 w-2 rounded-full bg-emerald-500" />
              Workflow Linked To URL
            </div>
          </div>
        </div>

        <div className="grid gap-3 xl:grid-cols-2">
          {STEP_ORDER.map((stepId, index) => {
            const meta = stepMeta[stepId];
            const Icon = meta.icon;
            const isActive = activeStep === stepId;

            return (
              <button
                key={stepId}
                type="button"
                onClick={() => handleStepNavigation(stepId)}
                className={`rounded-[24px] border p-4 text-left transition-all ${
                  isActive
                    ? "border-blue-500 bg-blue-600 text-white shadow-lg shadow-blue-600/20"
                    : "border-slate-200 bg-slate-50/70 hover:border-blue-200 hover:bg-blue-50 dark:border-slate-800 dark:bg-slate-900/50 dark:hover:border-blue-900"
                }`}
              >
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <div className={`text-[10px] font-black uppercase tracking-[0.26em] ${isActive ? "text-white/75" : "text-slate-400"}`}>
                      {meta.eyebrow}
                    </div>
                    <div className="mt-2 flex items-center gap-2">
                      <span className={`flex h-9 w-9 items-center justify-center rounded-2xl ${isActive ? "bg-white/15" : "bg-white text-blue-600 shadow-sm dark:bg-slate-800"}`}>
                        <Icon size={18} />
                      </span>
                      <div>
                        <div className={`text-xs font-black uppercase tracking-[0.22em] ${isActive ? "text-white" : "text-slate-500"}`}>
                          {index + 1}
                        </div>
                        <div className={`text-base font-black tracking-tight ${isActive ? "text-white" : "text-slate-950 dark:text-slate-50"}`}>
                          {meta.label}
                        </div>
                      </div>
                    </div>
                  </div>
                  {isActive ? <ChevronRight size={18} className="text-white/80" /> : null}
                </div>
                <p className={`mt-4 text-sm font-medium leading-relaxed ${isActive ? "text-white/80" : "text-slate-500 dark:text-slate-400"}`}>
                  {meta.description}
                </p>
              </button>
            );
          })}
        </div>
      </section>

      {activeStep === "setup" ? <SetupsWorkspaceSection /> : null}
      {activeStep === "strategy" ? <StrategiesWorkspaceSection /> : null}
    </div>
  );
}
