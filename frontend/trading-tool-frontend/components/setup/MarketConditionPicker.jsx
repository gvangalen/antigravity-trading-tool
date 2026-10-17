"use client";

import { MARKET_CONDITIONS } from "@/lib/setup/scoreConditions.mjs";

export default function MarketConditionPicker({ choice, onChange, copy = {}, disabled = false, existingLimits = false, previousChoice = null, children }) {
  const selected = MARKET_CONDITIONS.find((item) => item.id === choice);
  return (
    <fieldset disabled={disabled} className="min-w-0 space-y-4">
      <legend className="text-base font-black text-slate-900">{copy.title}</legend>
      <p className="text-sm leading-relaxed text-slate-600">{copy.help}</p>
      <label className={`flex cursor-pointer items-start gap-3 rounded-2xl border p-4 transition ${choice === "off" ? "border-blue-600 bg-blue-50" : "border-slate-200 bg-white hover:border-blue-300"}`}>
        <input type="radio" name="market-condition" checked={choice === "off"} onChange={() => onChange("off")} className="mt-1 accent-blue-600" />
        <span><strong className="block text-sm text-slate-900">{existingLimits ? copy.offClearsTitle : copy.offTitle}</strong><span className="mt-1 block text-xs leading-relaxed text-slate-600">{existingLimits ? copy.offClearsExisting : copy.offDescription}</span></span>
      </label>
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
        {MARKET_CONDITIONS.map((band) => (
          <label key={band.id} className={`flex min-h-32 cursor-pointer flex-col rounded-2xl border p-4 transition ${choice === band.id ? "border-blue-600 bg-blue-50 ring-2 ring-blue-100" : "border-slate-200 bg-white hover:border-blue-300"}`}>
            <span className="flex items-start gap-2">
              <input type="radio" name="market-condition" checked={choice === band.id} onChange={() => onChange(band.id)} className="mt-1 shrink-0 accent-blue-600" />
              <strong className="text-sm leading-snug text-slate-900">{copy.options?.[band.id]?.title}</strong>
            </span>
            <span className="mt-3 pl-5 text-xs leading-relaxed text-slate-600">{copy.options?.[band.id]?.description}</span>
          </label>
        ))}
        <label className={`flex min-h-32 cursor-pointer flex-col rounded-2xl border p-4 transition ${choice === "custom" ? "border-blue-600 bg-blue-50 ring-2 ring-blue-100" : "border-slate-200 bg-white hover:border-blue-300"}`}>
          <span className="flex items-start gap-2">
            <input type="radio" name="market-condition" checked={choice === "custom"} onChange={() => onChange("custom")} className="mt-1 shrink-0 accent-blue-600" />
            <strong className="text-sm leading-snug text-slate-900">{copy.customTitle}</strong>
          </span>
          <span className="mt-3 pl-5 text-xs leading-relaxed text-slate-600">{copy.customDescription}</span>
        </label>
      </div>
      {choice ? (
        <div aria-live="polite" className="rounded-2xl bg-blue-50 px-4 py-3 text-sm leading-relaxed text-slate-800">
          <strong>{copy.ruleTitle}</strong> {choice === "off" ? (existingLimits ? copy.offClearsExisting : copy.offRule) : selected ? copy.selectedRule?.replace("{situation}", copy.options?.[choice]?.title?.toLowerCase() || "") : copy.customRule}
        </div>
      ) : null}
      {existingLimits && selected && choice !== previousChoice ? <p className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-xs leading-relaxed text-amber-900">{copy.presetReplacesExisting}</p> : null}
      <details key={choice === "custom" ? "custom" : "preset"} defaultOpen={choice === "custom"} className="rounded-2xl border border-slate-200 bg-white p-4">
        <summary className="cursor-pointer text-sm font-semibold text-blue-700">{copy.advancedTitle}</summary>
        <p className="mt-3 text-xs leading-relaxed text-slate-600">{copy.advancedHelp}</p>
        {choice === "custom" ? <p className="mt-2 text-xs font-semibold text-slate-700">{copy.customSelected}</p> : null}
        {choice === "custom" ? <div className="mt-4">{children}</div> : null}
        {selected ? <p className="mt-3 text-xs text-slate-500">{copy.scoreExplanation?.replace("{min}", selected.min).replace("{max}", selected.max)}</p> : null}
      </details>
    </fieldset>
  );
}
