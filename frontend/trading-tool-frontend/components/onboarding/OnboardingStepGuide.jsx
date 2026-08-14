"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowDown, ArrowRight, CheckCircle2, Sparkles } from "lucide-react";

export default function OnboardingStepGuide({
  copy,
  anchorId,
  guidedMode = false,
  isComplete = false,
  nextHref = null,
  assistantFlow = null,
  assistantSuppressRestore = false,
}) {
  const router = useRouter();
  const [autoAdvanceCancelled, setAutoAdvanceCancelled] = useState(false);

  if (!copy) return null;

  const openFinnGuide = () => {
    if (typeof window === "undefined" || !copy.assistantPrompt) return;
    window.dispatchEvent(
      new CustomEvent("finn-action-trigger", {
        detail: {
          openAssistant: true,
          hiddenPrompt: copy.assistantPrompt,
          assistantFlow,
          assistantSuppressRestore,
        },
      })
    );
  };

  const showCompletedState = guidedMode && isComplete;
  const shouldAutoAdvance =
    showCompletedState && Boolean(nextHref) && !autoAdvanceCancelled;

  useEffect(() => {
    if (!showCompletedState) {
      setAutoAdvanceCancelled(false);
      return;
    }
    if (!nextHref || autoAdvanceCancelled) return;

    const timer = window.setTimeout(() => {
      router.push(nextHref);
    }, 1800);

    return () => window.clearTimeout(timer);
  }, [showCompletedState, nextHref, autoAdvanceCancelled, router]);

  const handleStayHere = () => {
    setAutoAdvanceCancelled(true);
    if (anchorId && typeof document !== "undefined") {
      document.getElementById(anchorId)?.scrollIntoView({
        behavior: "smooth",
        block: "start",
      });
    }
  };

  return (
    <div className="mb-10 overflow-hidden rounded-[2rem] border border-blue-100 bg-blue-50/70 shadow-sm">
      <div className="flex flex-col gap-6 p-8 lg:flex-row lg:items-center lg:justify-between">
        <div className="max-w-3xl">
          <div className="mb-2 flex flex-wrap items-center gap-2">
            <div className="text-[10px] font-black uppercase tracking-[0.3em] text-blue-600">
              {copy.eyebrow}
            </div>
            {guidedMode ? (
              <span className="inline-flex items-center gap-1 rounded-full border border-blue-200 bg-white px-3 py-1 text-[10px] font-black uppercase tracking-[0.18em] text-blue-700">
                <Sparkles size={12} />
                {copy.guidedBadge}
              </span>
            ) : null}
          </div>
          <h2 className="text-2xl font-black tracking-tight text-slate-900">
            {copy.title}
          </h2>
          <p className="mt-3 text-[15px] font-medium leading-relaxed text-slate-600">
            {copy.body}
          </p>

          {guidedMode && copy.guidedIntro ? (
            <div className="mt-4 rounded-2xl border border-blue-200 bg-white/90 px-4 py-3 shadow-sm">
              <p className="text-sm font-semibold leading-relaxed text-slate-700">
                {copy.guidedIntro}
              </p>
            </div>
          ) : null}

          {Array.isArray(copy.steps) && copy.steps.length > 0 ? (
            <ol className="mt-5 space-y-2 text-sm font-medium text-slate-600">
              {copy.steps.slice(0, 3).map((guideStep, index) => (
                <li key={guideStep} className="flex items-start gap-3">
                  <span className="mt-0.5 inline-flex h-5 w-5 flex-none items-center justify-center rounded-full bg-blue-600 text-[10px] font-black text-white">
                    {index + 1}
                  </span>
                  <span>{guideStep}</span>
                </li>
              ))}
            </ol>
          ) : null}

          {guidedMode && copy.completionHint ? (
            <div className="mt-5 flex items-start gap-3 rounded-2xl border border-emerald-200 bg-emerald-50 px-4 py-3">
              <CheckCircle2 size={16} className="mt-0.5 flex-none text-emerald-600" />
              <p className="text-sm font-semibold leading-relaxed text-emerald-800">
                {copy.completionHint}
              </p>
            </div>
          ) : null}

          {showCompletedState ? (
            <div className="mt-5 rounded-[1.5rem] border border-emerald-200 bg-white px-5 py-4 shadow-sm">
              <div className="flex items-start gap-3">
                <span className="inline-flex h-9 w-9 flex-none items-center justify-center rounded-full bg-emerald-100 text-emerald-700">
                  <CheckCircle2 size={18} />
                </span>
                <div>
                  <p className="text-sm font-black uppercase tracking-[0.18em] text-emerald-700">
                    {copy.completedEyebrow}
                  </p>
                  <h3 className="mt-1 text-lg font-black tracking-tight text-slate-900">
                    {copy.completedTitle}
                  </h3>
                  <p className="mt-2 text-sm font-medium leading-relaxed text-slate-600">
                    {copy.completedBody}
                  </p>
                </div>
              </div>
            </div>
          ) : null}

          {copy.finnHint ? (
            <p className="mt-5 text-sm font-semibold leading-relaxed text-slate-600">
              <span className="text-blue-600">{copy.finnLabel}</span> {copy.finnHint}
            </p>
          ) : null}
        </div>

        <div className="flex flex-col gap-3 lg:min-w-[220px]">
          {!showCompletedState ? (
            <div className="rounded-2xl border border-blue-200 bg-white px-4 py-3 text-sm font-semibold leading-relaxed text-slate-700 shadow-sm">
              <div className="text-[10px] font-black uppercase tracking-[0.2em] text-blue-600">
                {copy.actionLabel || "Best next action"}
              </div>
              <p className="mt-2">
                {copy.primaryActionHint || copy.primaryCta}
              </p>
            </div>
          ) : null}
          {showCompletedState && nextHref ? (
            <Link
              href={nextHref}
              className="rounded-2xl bg-emerald-600 px-6 py-4 text-center text-[11px] font-black uppercase tracking-[0.2em] text-white shadow-sm transition-all hover:bg-emerald-700 active:scale-95"
            >
              <span className="inline-flex items-center justify-center gap-2">
                <ArrowRight size={14} />
                {copy.nextCta}
              </span>
            </Link>
          ) : anchorId ? (
            <a
              href={`#${anchorId}`}
              className="rounded-2xl bg-blue-600 px-6 py-4 text-center text-[11px] font-black uppercase tracking-[0.2em] text-white shadow-sm transition-all hover:bg-blue-700 active:scale-95"
            >
              <span className="inline-flex items-center justify-center gap-2">
                <ArrowDown size={14} />
                {copy.primaryCta}
              </span>
            </a>
          ) : null}
          {showCompletedState ? (
            <button
              type="button"
              onClick={handleStayHere}
              className="rounded-2xl border border-emerald-200 bg-white px-6 py-4 text-center text-[11px] font-black uppercase tracking-[0.2em] text-emerald-700 shadow-sm transition-all hover:border-emerald-300 hover:bg-emerald-50 active:scale-95"
            >
              {copy.stayCta}
            </button>
          ) : null}
          {showCompletedState && copy.autoAdvanceHint ? (
            <p className="text-center text-[11px] font-bold leading-relaxed text-slate-500">
              {shouldAutoAdvance
                ? copy.autoAdvanceHint
                : copy.autoAdvanceStoppedHint}
            </p>
          ) : null}
          {copy.assistantPrompt && copy.assistantCta ? (
            <button
              type="button"
              onClick={openFinnGuide}
              className="rounded-2xl border border-blue-200 bg-white px-6 py-4 text-center text-[11px] font-black uppercase tracking-[0.2em] text-blue-700 shadow-sm transition-all hover:border-blue-300 hover:bg-blue-50 active:scale-95"
            >
              {copy.assistantCta}
            </button>
          ) : null}
          <Link
            href="/onboarding"
            className={`rounded-2xl border bg-white px-6 py-4 text-center text-[11px] font-black uppercase tracking-[0.2em] shadow-sm transition-all active:scale-95 ${
              showCompletedState
                ? "border-slate-200 text-slate-600 hover:border-slate-300 hover:bg-slate-50"
                : "border-blue-200 text-blue-700 hover:border-blue-300 hover:bg-blue-50"
            }`}
          >
            {copy.secondaryCta}
          </Link>
        </div>
      </div>
    </div>
  );
}
