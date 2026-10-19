"use client";

import { useEffect, useState } from "react";
import { useTranslation } from "@/app/providers/I18nProvider";
import { formatCurrency } from "@/lib/i18n";

const VARIANTS = ["default", "conservative", "aggressive"];

export default function StrategyTestPanel({ bot, onBacktest }) {
  const { t, locale } = useTranslation();
  const copy = t?.botPage?.focus?.strategyTest || {};
  const [mode, setMode] = useState("default");
  const [results, setResults] = useState([]);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    setResults([]);
    setError("");
  }, [bot?.id]);

  async function runTest() {
    if (!bot?.id || !onBacktest || running) return;
    setRunning(true);
    setError("");
    setResults([]);
    const variants = mode === "compare" ? VARIANTS : ["default"];
    const outcomes = await Promise.allSettled(variants.map((variant) => onBacktest(bot.id, variant)));
    const successful = outcomes.flatMap((outcome, index) =>
      outcome.status === "fulfilled" && outcome.value?.ok ? [{ variant: variants[index], data: outcome.value }] : []);
    setResults(successful);
    if (successful.length !== variants.length) setError(copy.partialError);
    setRunning(false);
  }

  return (
    <section className="rounded-xl border border-blue-200 bg-blue-50/40 p-4 dark:border-blue-900 dark:bg-blue-950/20" aria-label={copy.title}>
      <h3 className="font-black text-slate-950 dark:text-white">{copy.title}</h3>
      <p className="mt-1 text-sm text-slate-600 dark:text-slate-300">{copy.description}</p>
      <label className="mt-4 block text-sm font-bold" htmlFor="bot-strategy-test-mode">{copy.modeLabel}</label>
      <select id="bot-strategy-test-mode" value={mode} disabled={running} onChange={(event) => { setMode(event.target.value); setResults([]); setError(""); }}
        className="mt-1 rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm dark:bg-slate-900">
        <option value="default">{copy.currentSettings}</option>
        <option value="compare">{copy.compareVariants}</option>
      </select>
      <button type="button" onClick={runTest} disabled={running || !onBacktest}
        className="ml-3 rounded-lg bg-blue-600 px-4 py-2 text-sm font-bold text-white disabled:opacity-50">
        {running ? copy.running : copy.start}
      </button>
      <p className="mt-3 text-xs text-slate-500">{copy.assumption}</p>
      {error && <p role="alert" className="mt-3 text-sm text-amber-800">{error}</p>}
      {results.length > 0 && <div className="mt-4 grid gap-3 md:grid-cols-3">
        {results.map(({ variant, data }) => {
          const count = Number(data.total_trades || 0);
          return <article key={variant} className="rounded-lg border border-slate-200 bg-white p-4 dark:bg-slate-900">
            <h4 className="font-bold">{copy.variants?.[variant] || variant}</h4>
            {count === 0 ? (
              <p className="mt-3 text-sm font-semibold text-amber-800 dark:text-amber-300">{copy.insufficientData}</p>
            ) : <>
              <p className="mt-1 text-xs text-slate-500">{copy.simulatedCapital}: {formatCurrency(Number(data.initial_balance), locale, "EUR")}</p>
              <p className="mt-3 text-sm">{copy.trades}: {count}</p>
              <p className="text-sm">{copy.return}: {data.return_pct}%</p>
              <p className="text-sm">{copy.endCapital}: {formatCurrency(Number(data.final_balance), locale, "EUR")}</p>
              {count < 5 && <p className="mt-2 text-xs text-amber-800 dark:text-amber-300">{copy.limitedData}</p>}
            </>}
          </article>;
        })}
      </div>}
    </section>
  );
}
