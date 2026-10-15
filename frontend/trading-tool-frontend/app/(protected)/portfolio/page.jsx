"use client";

import { Suspense, useCallback, useEffect, useRef, useState } from "react";
import { ArrowRight, RefreshCw, Wallet } from "lucide-react";

import { fetchBotTrades, fetchPortfolioSummary } from "@/lib/api/botApi";
import { openFinnContext } from "@/lib/finnCommandSearch";
import { formatCurrency, formatDateTime, formatNumber } from "@/lib/i18n";
import { useTranslation } from "@/app/providers/I18nProvider";

const known = (value) => value !== null && value !== undefined && Number.isFinite(Number(value));

function PortfolioPageInner() {
  const { t, locale } = useTranslation();
  const copy = t?.portfolioPage || {};
  const [environment, setEnvironment] = useState("paper");
  const [loadedOverview, setLoadedOverview] = useState(null);
  const requestSequence = useRef(0);
  const [selectedId, setSelectedId] = useState(null);
  const [detailTab, setDetailTab] = useState("positions");
  const [trades, setTrades] = useState([]);
  const [tradesLoading, setTradesLoading] = useState(false);
  const [tradesError, setTradesError] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const money = useCallback((value) => known(value)
    ? formatCurrency(Number(value), locale, "EUR", { maximumFractionDigits: 2 })
    : "—", [locale]);
  const time = useCallback((value) => value
    ? formatDateTime(new Date(value), locale, { dateStyle: "medium", timeStyle: "short" })
    : null, [locale]);

  const load = useCallback(async () => {
    const sequence = ++requestSequence.current;
    setLoading(true);
    setError(null);
    try {
      const response = await fetchPortfolioSummary(environment);
      if (sequence === requestSequence.current) {
        setLoadedOverview({ environment, data: response?.data || null });
      }
    } catch (cause) {
      if (sequence === requestSequence.current) {
        setError(cause?.message || copy.loadError);
        setLoadedOverview({ environment, data: null });
      }
    } finally {
      if (sequence === requestSequence.current) setLoading(false);
    }
  }, [environment, copy.loadError]);

  useEffect(() => {
    load();
    window.addEventListener("portfolio:updated", load);
    return () => window.removeEventListener("portfolio:updated", load);
  }, [load]);
  useEffect(() => { setSelectedId(null); setTrades([]); }, [environment]);

  // A render after switching tabs must never relabel the previous environment's
  // money as the newly selected one, even before the next effect starts.
  const overview = loadedOverview?.environment === environment ? loadedOverview.data : null;
  const bots = overview?.bots || [];
  const selected = bots.find((bot) => bot.bot_id === selectedId) || null;
  useEffect(() => {
    if (!selectedId || detailTab !== "transactions") return;
    let active = true;
    setTradesLoading(true);
    setTradesError(false);
    fetchBotTrades(selectedId, 30)
      .then((items) => { if (active) setTrades(Array.isArray(items) ? items : []); })
      .catch(() => { if (active) { setTrades([]); setTradesError(true); } })
      .finally(() => { if (active) setTradesLoading(false); });
    return () => { active = false; };
  }, [selectedId, detailTab]);

  const global = overview?.global || {};
  const valuationAvailable = Boolean(overview?.valuation_available);
  const result = valuationAvailable && known(global.realized_pnl) && known(global.unrealized_pnl)
    ? Number(global.realized_pnl) + Number(global.unrealized_pnl) : null;
  const statusMessage = overview?.valuation_status === "unreconciled_live"
    ? copy.unreconciledLive
    : overview?.valuation_status === "unfunded"
      ? copy.unfunded
      : overview?.valuation_status === "missing_price"
        ? copy.missingPrice
        : overview?.valuation_status === "empty" ? copy.empty : null;

  const discuss = (bot) => openFinnContext({
    query: `Bespreek de opgeslagen portefeuille van bot ${bot.name}. Leg de bekende waarde, positie, het resultaat en ontbrekende gegevens uit.`,
    context: { page: "/portfolio", bot_id: bot.bot_id, bot_name: bot.name,
      symbol: bot.symbol, finn_subject_type: "bot", locale },
  });

  const selectEnvironment = (nextEnvironment) => {
    if (nextEnvironment === environment) return;
    requestSequence.current += 1;
    setLoading(true);
    setError(null);
    setSelectedId(null);
    setEnvironment(nextEnvironment);
  };

  return (
    <main className="mx-auto w-full max-w-7xl space-y-8 px-4 py-8 pb-28 text-slate-900 dark:text-slate-100 sm:px-6 lg:px-8">
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Portfolio</h1>
          <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">{copy.subtitle}</p>
        </div>
        <div className="flex items-center gap-2">
          <div className="flex rounded-xl border border-slate-200 p-1 dark:border-slate-700" role="group" aria-label={copy.environment}>
            {(["paper", "live"]).map((item) => (
              <button key={item} type="button" onClick={() => selectEnvironment(item)}
                aria-pressed={environment === item}
                className={`rounded-lg px-4 py-2 text-sm font-semibold ${environment === item ? "bg-blue-600 text-white" : "text-slate-600 dark:text-slate-300"}`}>
                {copy[item]}
              </button>
            ))}
          </div>
          <button type="button" onClick={load} aria-label={copy.refresh}
            className="rounded-xl border border-slate-200 p-2.5 dark:border-slate-700"><RefreshCw size={18} /></button>
        </div>
      </header>

      {error && <div role="alert" className="rounded-xl bg-red-50 p-4 text-sm text-red-700 dark:bg-red-950/30 dark:text-red-200">{copy.loadError} {error}</div>}
      {statusMessage && !loading && <p className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900 dark:border-amber-900 dark:bg-amber-950/30 dark:text-amber-200">{statusMessage}</p>}
      {environment === "paper" && <p className="text-xs text-slate-500 dark:text-slate-400">{copy.paperMoney}</p>}
      {environment === "live" && <p className="text-xs text-slate-500 dark:text-slate-400">{copy.liveAttribution}</p>}

      <section className="grid grid-cols-2 gap-4 rounded-2xl border border-slate-200 p-5 dark:border-slate-800 md:grid-cols-4" aria-label={copy.totalValue}>
        {[
          [copy.totalValue, valuationAvailable ? global.total_equity : null],
          [copy.cash, global.cash_balance],
          [copy.positions, global.current_position_value],
          [copy.result, result],
        ].map(([label, value]) => (
          <div key={label} className="min-w-0">
            <div className="text-xs text-slate-500 dark:text-slate-400">{label}</div>
            <div className="mt-1 text-xl font-bold tabular-nums sm:text-2xl">{money(value)}</div>
          </div>
        ))}
      </section>
      {overview && <p className="text-xs text-slate-500 dark:text-slate-400">
        {overview.valuation_as_of ? `${copy.asOf}: ${time(overview.valuation_as_of)} · ` : ""}
        {copy.readAt}: {time(overview.read_at) || copy.unknown}
      </p>}

      <section className="rounded-2xl border border-slate-200 p-5 dark:border-slate-800">
        <h2 className="text-lg font-semibold">{copy.history}</h2>
        <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">{copy.historyHint}</p>
        <p className="mt-6 text-sm text-slate-500">{copy.noHistory}</p>
      </section>

      <section className="rounded-2xl border border-slate-200 p-5 dark:border-slate-800">
        <h2 className="text-lg font-semibold">{copy.bots}</h2>
        {!loading && bots.length === 0 && <p className="mt-4 text-sm text-slate-500">{copy.noBots}</p>}
        {bots.length > 0 && <div className="mt-4 overflow-x-auto">
          <table className="w-full min-w-[650px] text-left text-sm">
            <thead className="border-b border-slate-200 text-xs text-slate-500 dark:border-slate-800">
              <tr>{[copy.bot, copy.value, copy.cash, copy.positions, copy.result].map((label) => <th key={label} scope="col" className="px-3 py-3 font-medium">{label}</th>)}<th scope="col"><span className="sr-only">{copy.details}</span></th></tr>
            </thead>
            <tbody>{bots.map((bot) => <tr key={bot.bot_id} className="border-b border-slate-100 dark:border-slate-800">
              <th scope="row" className="px-3 py-4 font-semibold">{bot.name}<span className="block text-xs font-normal text-slate-500">{bot.symbol} · {environment === "paper" ? copy.paper : copy.live}</span></th>
              <td className="px-3 py-4 tabular-nums">{money(bot.equity)}</td>
              <td className="px-3 py-4 tabular-nums">{money(bot.cash_eur)}</td>
              <td className="px-3 py-4 tabular-nums">{money(bot.position_value_eur)}</td>
              <td className="px-3 py-4 tabular-nums">{money(bot.result_eur)}</td>
              <td className="px-3 py-4"><button type="button" onClick={() => { setSelectedId(bot.bot_id); setDetailTab("positions"); }}
                aria-label={`${copy.details}: ${bot.name}`} className="text-blue-600 hover:underline dark:text-blue-400">{copy.details} <ArrowRight className="inline" size={14} /></button></td>
            </tr>)}</tbody>
            <tfoot><tr className="border-t border-slate-300 font-semibold dark:border-slate-700">
              <th scope="row" className="px-3 py-4">{copy.total}</th>
              <td className="px-3 py-4 tabular-nums">{money(global.total_equity)}</td>
              <td className="px-3 py-4 tabular-nums">{money(global.cash_balance)}</td>
              <td className="px-3 py-4 tabular-nums">{money(global.current_position_value)}</td>
              <td className="px-3 py-4 tabular-nums">{money(result)}</td><td />
            </tr></tfoot>
          </table>
        </div>}
      </section>

      {selected && <section className="rounded-2xl border border-blue-200 bg-blue-50/30 p-5 dark:border-blue-900 dark:bg-blue-950/20" aria-label={selected.name}>
        <div className="flex justify-between gap-3"><div><h2 className="text-lg font-semibold">{selected.name}</h2><p className="text-xs text-slate-500">{selected.symbol} · {environment === "paper" ? copy.paper : copy.live}</p></div>
          <button type="button" onClick={() => setSelectedId(null)} className="text-sm text-slate-600 dark:text-slate-300">{copy.close}</button></div>
        <div className="mt-5 flex flex-wrap gap-2">{[["positions", copy.positions], ["transactions", copy.transactions], ["limits", copy.limits]].map(([key, label]) =>
          <button type="button" key={key} onClick={() => setDetailTab(key)} aria-pressed={detailTab === key}
            className={`rounded-lg px-3 py-2 text-sm ${detailTab === key ? "bg-blue-600 text-white" : "border border-slate-200 dark:border-slate-700"}`}>{label}</button>)}</div>
        {detailTab === "positions" && <div className="mt-5 grid gap-3 text-sm sm:grid-cols-3">
          <div>{copy.asset}: <strong>{selected.symbol}</strong></div>
          <div>{copy.quantity}: <strong>{known(selected.position_qty) ? formatNumber(selected.position_qty, locale, { maximumFractionDigits: 8 }) : "—"}</strong></div>
          <div>{copy.value}: <strong>{money(selected.position_value_eur)}</strong></div>
          {selected.position_qty === 0 && <p className="text-slate-500">{copy.noPosition}</p>}
          {Number(selected.position_qty) > 0 && selected.price_quote_currency && selected.price_quote_currency !== "EUR" &&
            <p className="text-slate-500 sm:col-span-3">{copy.foreignQuote}: {selected.price_quote_currency}. {copy.conversionNeeded}</p>}
        </div>}
        {detailTab === "transactions" && <div className="mt-5 space-y-2 text-sm">
          {tradesLoading ? <p>{copy.loadingTransactions}</p> : tradesError ? <p role="alert">{copy.transactionsError}</p> : trades.length ? trades.map((trade) => <div key={trade.id} className="flex justify-between gap-3 border-b border-slate-200 py-2 dark:border-slate-800"><span>{copy[trade.side] || trade.side} · {trade.qty} {trade.symbol}</span><span>{money(trade.amount_eur)} · {time(trade.executed_at)}</span></div>) : <p>{copy.noTransactions}</p>}
        </div>}
        {detailTab === "limits" && <div className="mt-5 text-sm"><span>{copy.budget}: <strong>{money(selected.budget_total_eur)}</strong></span><p className="mt-2 text-xs text-slate-500">{copy.budgetHint}</p></div>}
        <button type="button" onClick={() => discuss(selected)} className="mt-6 inline-flex items-center gap-2 text-sm font-semibold text-blue-600 dark:text-blue-400"><Wallet size={16} />{copy.discuss}</button>
      </section>}
    </main>
  );
}

export default function PortfolioPage() {
  return <Suspense fallback={null}><PortfolioPageInner /></Suspense>;
}
