"use client";

import { useEffect, useId, useState } from "react";
import { ArrowDownRight, ArrowUpRight, ChevronDown, Info, MoveRight, SlidersHorizontal } from "lucide-react";

import { MARKET_CONDITIONS } from "@/lib/setup/scoreConditions.mjs";
import styles from "./MarketConditionPicker.module.css";

const CONDITION_ICONS = [ArrowDownRight, ArrowDownRight, MoveRight, ArrowUpRight, ArrowUpRight];

export default function MarketConditionPicker({ choice, onChange, copy = {}, symbol = "", disabled = false, existingLimits = false, previousChoice = null, allowOff = true, children }) {
  const selected = MARKET_CONDITIONS.find((item) => item.id === choice);
  const [advancedOpen, setAdvancedOpen] = useState(choice === "custom" || choice === "off");
  const advancedId = useId();
  const radioName = useId();

  useEffect(() => {
    if (choice === "custom" || choice === "off") setAdvancedOpen(true);
  }, [choice]);

  const selectedTitle = selected
    ? copy.options?.[selected.id]?.title
    : choice === "custom"
      ? copy.customTitle
      : choice === "off"
        ? (existingLimits ? copy.offClearsTitle : copy.offTitle)
        : copy.summaryEmptyTitle;
  const selectedRule = selected
    ? copy.options?.[selected.id]?.rule || copy.selectedRule?.replace("{situation}", selectedTitle?.toLowerCase() || "")
    : choice === "custom"
      ? copy.customRule
      : choice === "off"
        ? (existingLimits ? copy.offClearsExisting : copy.offRule)
        : copy.summaryEmptyBody;
  const assetSymbol = String(symbol || "").toUpperCase();

  return (
    <fieldset disabled={disabled} className={`min-w-0 ${styles.container}`}>
      <legend className="text-2xl font-black tracking-tight text-slate-950">{copy.title}</legend>
      <p className="mt-2 mb-6 max-w-2xl text-sm leading-relaxed text-slate-600">{copy.help}</p>

      <div className={styles.columns}>
        <div className="min-w-0 space-y-2">
          {MARKET_CONDITIONS.map((band, index) => {
            const Icon = CONDITION_ICONS[index];
            const checked = choice === band.id;
            return (
              <label key={band.id} className={`flex min-h-[74px] cursor-pointer items-center gap-4 rounded-xl border px-4 py-3 transition-colors focus-within:ring-2 focus-within:ring-blue-200 ${checked ? "border-blue-600 bg-blue-50/80 shadow-sm" : "border-slate-200 bg-white hover:border-blue-300 hover:bg-slate-50/60"}`}>
                <input type="radio" name={radioName} checked={checked} onChange={() => onChange(band.id)} className="h-5 w-5 shrink-0 accent-blue-600" />
                <span className="min-w-0 flex-1">
                  <strong className="block text-sm font-bold leading-snug text-slate-900">{copy.options?.[band.id]?.title}</strong>
                  <span className="mt-0.5 block text-xs leading-relaxed text-slate-500">{copy.options?.[band.id]?.description}</span>
                </span>
                <Icon size={23} strokeWidth={1.5} aria-hidden="true" className={`shrink-0 ${checked ? "text-blue-700" : "text-slate-700"}`} />
              </label>
            );
          })}
        </div>

        <aside aria-live="polite" className="min-w-0 rounded-2xl bg-slate-50 px-5 py-6 sm:px-6">
          <h3 className="text-lg font-black tracking-tight text-slate-900">{copy.summaryTitle}</h3>
          {assetSymbol ? (
            <div className="mt-5 flex items-center gap-2.5 text-sm font-medium text-slate-600">
              <span aria-hidden="true" className={`flex h-9 w-9 items-center justify-center rounded-full text-base font-black text-white ${assetSymbol === "BTC" ? "bg-orange-500" : "bg-blue-600"}`}>
                {assetSymbol === "BTC" ? "₿" : assetSymbol.slice(0, 1)}
              </span>
              <span>{assetSymbol === "BTC" ? "Bitcoin" : assetSymbol}</span>
            </div>
          ) : null}
          <h4 className="mt-5 text-2xl font-black leading-tight tracking-tight text-slate-950">{selectedTitle}</h4>
          <p className="mt-3 text-sm leading-relaxed text-slate-700">{selectedRule}</p>
          <div className="mt-7 border-t border-slate-200 pt-6">
            <h5 className="text-sm font-bold text-slate-900">{copy.outcomeTitle}</h5>
            <p className="mt-2 text-sm leading-relaxed text-slate-600">{copy.outcomeBody}</p>
          </div>
        </aside>
      </div>

      {existingLimits && selected && choice !== previousChoice ? (
        <p className="mt-5 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-xs leading-relaxed text-amber-900">{copy.presetReplacesExisting}</p>
      ) : null}

      <div className="mt-6 border-y border-slate-200">
        <button type="button" aria-expanded={advancedOpen} aria-controls={advancedId} onClick={() => setAdvancedOpen((open) => !open)} className="flex w-full items-center gap-4 py-4 text-left text-slate-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500">
          <SlidersHorizontal size={21} strokeWidth={1.8} className="shrink-0 text-slate-700" aria-hidden="true" />
          <span className="min-w-0 flex-1">
            <strong className="block text-sm font-bold">{copy.advancedTitle}</strong>
            <span className="block text-xs text-slate-500">{copy.advancedSubtitle}</span>
          </span>
          <ChevronDown size={20} aria-hidden="true" className={`shrink-0 text-slate-700 transition-transform ${advancedOpen ? "rotate-180" : ""}`} />
        </button>
        <div id={advancedId} hidden={!advancedOpen} className="space-y-3 border-t border-slate-100 pb-5 pt-4">
            <label className={`flex cursor-pointer items-start gap-3 rounded-xl border px-4 py-3 ${choice === "custom" ? "border-blue-600 bg-blue-50/80" : "border-slate-200 bg-white hover:border-blue-300"}`}>
              <input type="radio" name={radioName} checked={choice === "custom"} onChange={() => onChange("custom")} className="mt-0.5 h-5 w-5 shrink-0 accent-blue-600" />
              <span>
                <strong className="block text-sm font-bold text-slate-900">{copy.customTitle}</strong>
                <span className="mt-1 block text-xs leading-relaxed text-slate-600">{copy.customDescription}</span>
              </span>
            </label>
            {allowOff ? (
              <label className={`flex cursor-pointer items-center gap-4 rounded-xl border px-4 py-3 transition-colors focus-within:ring-2 focus-within:ring-blue-200 ${choice === "off" ? "border-blue-600 bg-blue-50/80" : "border-slate-200 bg-white hover:border-blue-300"}`}>
                <input type="radio" name={radioName} checked={choice === "off"} onChange={() => onChange("off")} className="h-5 w-5 shrink-0 accent-blue-600" />
                <span className="min-w-0">
                  <strong className="block text-sm font-bold text-slate-900">{existingLimits ? copy.offClearsTitle : copy.offTitle}</strong>
                  <span className="mt-0.5 block text-xs leading-relaxed text-slate-500">{existingLimits ? copy.offClearsExisting : copy.offDescription}</span>
                </span>
              </label>
            ) : null}
            {choice === "custom" ? (
              <div className="mt-5">
                <p className="mb-3 text-xs font-semibold text-slate-700">{copy.customSelected}</p>
                {children}
              </div>
            ) : null}
        </div>
      </div>

      <details className="mt-4 text-xs leading-relaxed text-slate-600">
        <summary className="flex cursor-pointer list-none items-center gap-2 font-semibold text-blue-700 marker:hidden">
          <Info size={15} aria-hidden="true" /> {copy.explanationTitle}
        </summary>
        <p className="mt-3 max-w-3xl">{copy.advancedHelp}</p>
        {selected ? <p className="mt-2">{copy.scoreExplanation?.replace("{min}", selected.min).replace("{max}", selected.max)}</p> : null}
      </details>
    </fieldset>
  );
}
