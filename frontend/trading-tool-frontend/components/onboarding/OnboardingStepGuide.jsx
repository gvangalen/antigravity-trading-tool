"use client";

import Link from "next/link";

export default function OnboardingStepGuide({ copy, anchorId }) {
  if (!copy) return null;

  return (
    <div className="mb-10 overflow-hidden rounded-[2rem] border border-blue-100 bg-blue-50/70 shadow-sm">
      <div className="flex flex-col gap-6 p-8 lg:flex-row lg:items-center lg:justify-between">
        <div className="max-w-3xl">
          <div className="mb-2 text-[10px] font-black uppercase tracking-[0.3em] text-blue-600">
            {copy.eyebrow}
          </div>
          <h2 className="text-2xl font-black tracking-tight text-slate-900">
            {copy.title}
          </h2>
          <p className="mt-3 text-[15px] font-medium leading-relaxed text-slate-600">
            {copy.body}
          </p>

          {Array.isArray(copy.examples) && copy.examples.length > 0 ? (
            <div className="mt-4 flex flex-wrap gap-3">
              {copy.examples.map((example) => (
                <span
                  key={example}
                  className="rounded-full border border-blue-200 bg-white px-3 py-1.5 text-[11px] font-bold text-blue-700"
                >
                  {example}
                </span>
              ))}
            </div>
          ) : null}

          {Array.isArray(copy.steps) && copy.steps.length > 0 ? (
            <ol className="mt-5 space-y-2 text-sm font-medium text-slate-600">
              {copy.steps.map((guideStep) => (
                <li key={guideStep} className="flex items-start gap-3">
                  <span className="mt-0.5 inline-flex h-5 w-5 flex-none items-center justify-center rounded-full bg-blue-600 text-[10px] font-black text-white">
                    •
                  </span>
                  <span>{guideStep}</span>
                </li>
              ))}
            </ol>
          ) : null}

          {copy.finnHint ? (
            <p className="mt-5 text-sm font-semibold leading-relaxed text-slate-600">
              <span className="text-blue-600">{copy.finnLabel}</span> {copy.finnHint}
            </p>
          ) : null}
        </div>

        <div className="flex flex-col gap-3 lg:min-w-[220px]">
          {anchorId ? (
            <a
              href={`#${anchorId}`}
              className="rounded-2xl bg-blue-600 px-6 py-4 text-center text-[11px] font-black uppercase tracking-[0.2em] text-white shadow-sm transition-all hover:bg-blue-700 active:scale-95"
            >
              {copy.primaryCta}
            </a>
          ) : null}
          <Link
            href="/onboarding"
            className="rounded-2xl border border-blue-200 bg-white px-6 py-4 text-center text-[11px] font-black uppercase tracking-[0.2em] text-blue-700 shadow-sm transition-all hover:border-blue-300 hover:bg-blue-50 active:scale-95"
          >
            {copy.secondaryCta}
          </Link>
        </div>
      </div>
    </div>
  );
}
