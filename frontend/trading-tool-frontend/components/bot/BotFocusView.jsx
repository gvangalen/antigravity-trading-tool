"use client";

import { useEffect, useMemo, useState } from "react";
import { AlertTriangle, ChevronRight, ShieldCheck } from "lucide-react";
import { useTranslation } from "@/app/providers/I18nProvider";
import { formatCurrency, formatDateTime } from "@/lib/i18n";
import SystemConnectivity from "@/components/dashboard/SystemConnectivity";
import StrategyTestPanel from "@/components/bot/StrategyTestPanel";
import BotHistoryTable from "@/components/bot/BotHistoryTable";
import { openFinnContext } from "@/lib/finnCommandSearch";
import { getBotApiErrorMessage } from "@/lib/bot/botApiErrorMessage.mjs";
import { selectLastBotDecision } from "@/lib/bot/lastDecision.mjs";
import { paperPriceMessageKey } from "@/lib/bot/paperPriceMessage.mjs";
import { marketPairLabel } from "@/lib/marketPairLabel.mjs";

export default function BotFocusView({
  bots, activeBot, onSelectBot, decision, pendingOrder, portfolio, trades, allTrades,
  loading, onLoadBotTrades, onLoadAllTrades, onCreateBot, onOpenSettings,
  onUpdateBot, onGenerate, onTrade, tradeActive, onBacktest,
  history,
}) {
  const { t, locale } = useTranslation();
  const copy = t?.botPage?.focus || {};
  const [view, setView] = useState("bots");
  const [activityView, setActivityView] = useState("decisions");
  const [showStrategyTest, setShowStrategyTest] = useState(false);
  const [cashInput, setCashInput] = useState("");
  const [cashAcknowledged, setCashAcknowledged] = useState(false);
  const [editingCash, setEditingCash] = useState(false);
  const [savingCash, setSavingCash] = useState(false);
  const [cashError, setCashError] = useState("");
  const [changingActivity, setChangingActivity] = useState(false);
  const [activityError, setActivityError] = useState("");

  useEffect(() => {
    if (activeBot?.id) void onLoadBotTrades(activeBot.id, 5);
  }, [activeBot?.id, onLoadBotTrades]);

  useEffect(() => {
    if (view === "trades") void onLoadAllTrades(0);
  }, [view, onLoadAllTrades]);

  useEffect(() => {
    setCashInput("");
    setCashAcknowledged(false);
    setEditingCash(false);
    setCashError("");
    setActivityError("");
    setActivityView("decisions");
    setShowStrategyTest(false);
  }, [activeBot?.id]);

  const risk = decision?.safety_check || { state: "missing", allowed_amount_eur: 0 };
  const orderState = ["unknown_exchange_state", "sending"].includes(pendingOrder?.status) ? "unknown_exchange_state"
    : ["ready", "pending"].includes(pendingOrder?.status) ? "execution_pending"
      : pendingOrder ? "awaiting_exchange" : null;
  const state = orderState || (activeBot?.is_active === false ? "paused" : risk.state || "missing");
  const riskTitle = copy.states?.[state] || state;
  const explanations = Array.isArray(risk.explanations) ? risk.explanations : [];
  const paperPriceKey = !orderState && paperPriceMessageKey({
    isLive: activeBot?.is_live, symbol: activeBot?.symbol,
    reasonCode: risk.reason_code, at: new Date(),
  });
  const riskReason = paperPriceKey ? copy[paperPriceKey]
    : orderState ? copy.reasons?.[orderState]
    : risk.execution_failure || (state === "no_proposal" ? copy.reasons?.no_proposal : null)
      || copy.riskCodes?.[risk.reason_code] || copy.riskCodes?.[explanations[0]?.code]
      || ((state === "allowed" || state === "executed") && explanations.length === 0 ? copy.states?.allowed : null)
      || risk.reason || copy.reasons?.[state] || copy.reasonUnavailable;
  const nextStepText = paperPriceKey ? copy[`${paperPriceKey}NextStep`]
    : orderState ? copy.nextSteps?.[orderState] : copy.nextSteps?.[risk.reason_code] || copy.nextSteps?.[state] || risk.next_step || copy.nextStepFallback;
  const pausedPaperWithoutCash = state === "paused" && !activeBot?.is_live
    && (!portfolio?.stats?.paper_cash_configured || Number(portfolio.stats.paper_cash_eur || 0) <= 0);
  const riskTone = state === "blocked" || state === "error" || state === "unknown_exchange_state"
    ? "border-red-200 bg-red-50 text-red-900 dark:border-red-900 dark:bg-red-950/30 dark:text-red-200"
    : state === "reduced" || state === "stale" || state === "missing" || state === "awaiting_exchange" || state === "execution_pending"
      ? "border-amber-200 bg-amber-50 text-amber-900 dark:border-amber-900 dark:bg-amber-950/30 dark:text-amber-200"
      : "border-blue-200 bg-blue-50 text-blue-900 dark:border-blue-900 dark:bg-blue-950/30 dark:text-blue-200";
  const money = (amount) => formatCurrency(Number(amount || 0), locale, "EUR", { maximumFractionDigits: 2 });
  const statusTime = orderState ? pendingOrder?.created_at : risk.checked_at;
  const checkedAt = statusTime
    ? formatDateTime(statusTime, locale, { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" })
    : copy.notChecked;
  const availableCash = portfolio?.stats?.paper_cash_configured
    ? money(portfolio.stats.paper_cash_eur)
    : copy.notConfigured;
  const symbol = marketPairLabel(activeBot);
  const timeframe = activeBot?.strategy?.setup?.timeframe || activeBot?.strategy?.timeframe || "—";
  const modeLabel = copy.modes?.[activeBot?.mode] || activeBot?.mode || "—";
  const recentActivity = useMemo(() => {
    const decisions = (history || [])
      .filter((item) => item.bot_id === activeBot?.id)
      .map((item) => ({ ...item, id: `decision-${item.decision_id}`, created_at: item.decision_ts || item.created_at || item.date }));
    const executions = (trades || []).map((trade) => ({
      id: `trade-${trade.id}`,
      bot_id: activeBot?.id,
      created_at: trade.executed_at,
      action: trade.side,
      qty: trade.qty,
      price: trade.price,
      amount_eur: trade.amount_eur,
      status: trade.status || "executed",
      symbol: trade.symbol,
      is_trade: true,
    }));
    return [...executions, ...decisions].sort((a, b) =>
      new Date(b.created_at || b.date || 0) - new Date(a.created_at || a.date || 0));
  }, [activeBot?.id, history, trades]);
  // The current-status endpoint may omit a paused bot. Its persisted decision
  // history still describes the last assessment, without making it executable.
  const lastRecordedDecision = selectLastBotDecision(decision, history, activeBot?.id);
  const historyOnlyDecision = !decision?.action && Boolean(lastRecordedDecision);
  const historicalDecisionAt = historyOnlyDecision
    ? lastRecordedDecision?.decision_ts || lastRecordedDecision?.created_at || lastRecordedDecision?.date
    : null;
  const recordedSafety = lastRecordedDecision?.safety_check || {};
  const recordedReason = lastRecordedDecision?.strategy_reason
    || lastRecordedDecision?.reasons?.find((item) => typeof item === "string" && item.trim())
    || recordedSafety.reason;
  const strategyReason = recordedReason === "Scheduled DCA amount selected from the confirmed plan"
    ? copy.scheduledDcaReason : recordedReason;
  const dcaSchedule = activeBot?.dca_schedule_status;
  const nextDcaDate = dcaSchedule?.next_due_date
    ? new Intl.DateTimeFormat(locale, { day: "numeric", month: "long", year: "numeric" })
      .format(new Date(`${dcaSchedule.next_due_date}T12:00:00`))
    : null;

  async function saveCash(event) {
    event.preventDefault();
    const amount = Number(cashInput.replace(",", "."));
    if (!Number.isFinite(amount) || amount <= 0 || amount > 100000000) {
      setCashError(copy.invalidCash);
      return;
    }
    if (!cashAcknowledged) {
      setCashError(copy.cashAcknowledgementRequired);
      return;
    }
    setSavingCash(true);
    setCashError("");
    try {
      await onUpdateBot(activeBot.id, { paper_initial_cash_eur: amount, risk_acknowledged: true });
      setEditingCash(false);
    } catch (error) {
      setCashError(error?.message || copy.cashSaveFailed);
    } finally {
      setSavingCash(false);
    }
  }

  async function toggleActivity() {
    if (!activeBot || changingActivity) return;
    setChangingActivity(true);
    setActivityError("");
    try {
      await onUpdateBot(activeBot.id, { is_active: !activeBot.is_active });
    } catch (error) {
      setActivityError(getBotApiErrorMessage(error, copy.activityFailed));
    } finally {
      setChangingActivity(false);
    }
  }

  return (
    <section className="space-y-5 pb-24">
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="text-[10px] font-black uppercase tracking-[0.2em] text-blue-700">{copy.eyebrow}</div>
          <h1 className="mt-1 text-3xl font-black tracking-tight text-slate-950 dark:text-white">{copy.title}</h1>
          <p className="mt-1 text-sm text-slate-500">{copy.subtitle}</p>
        </div>
        <button type="button" onClick={onCreateBot} className="rounded-xl bg-blue-600 px-4 py-2.5 text-sm font-bold text-white hover:bg-blue-700">
          {copy.createBot}
        </button>
      </header>

      <nav className="flex gap-5 border-b border-slate-200" aria-label={copy.viewLabel}>
        <button type="button" onClick={() => setView("bots")} aria-current={view === "bots" ? "page" : undefined}
          className={`border-b-2 pb-3 text-sm font-bold ${view === "bots" ? "border-blue-600 text-blue-700" : "border-transparent text-slate-500"}`}>{copy.bots}</button>
        <button type="button" onClick={() => setView("trades")} aria-current={view === "trades" ? "page" : undefined}
          className={`border-b-2 pb-3 text-sm font-bold ${view === "trades" ? "border-blue-600 text-blue-700" : "border-transparent text-slate-500"}`}>{copy.allTrades}</button>
      </nav>

      {view === "trades" ? (
        <section className="rounded-2xl border border-slate-200 bg-white p-5 dark:border-slate-800 dark:bg-slate-950">
          <h2 className="text-xl font-black text-slate-950 dark:text-white">{copy.allTrades}</h2>
          <p className="mb-4 mt-1 text-sm text-slate-500">{copy.allTradesDescription}</p>
          {allTrades.items.some((trade) => trade.environment === "unknown") && (
            <p className="mb-4 text-sm text-amber-800 dark:text-amber-300">{copy.legacyEnvironmentHint}</p>
          )}
          <div className="overflow-x-auto">
            <table className="w-full min-w-[610px] text-left text-sm">
              <thead className="border-b border-slate-200 text-xs uppercase text-slate-500"><tr>
                <th className="p-3">{copy.date}</th><th className="p-3">{copy.bot}</th><th className="p-3">{copy.trade}</th><th className="p-3">{copy.amount}</th><th className="p-3">{copy.environment}</th><th className="p-3">{copy.execution}</th><th className="p-3">{copy.status}</th>
              </tr></thead>
              <tbody>{allTrades.items.map((trade) => (
                <tr key={trade.id} className="border-b border-slate-100 dark:border-slate-800">
                  <td className="p-3">{trade.executed_at ? formatDateTime(trade.executed_at, locale) : "—"}</td>
                  <td className="p-3">{trade.bot_name}</td>
                  <td className="p-3">{trade.side === "buy" ? copy.buy : copy.sell} {trade.symbol}</td>
                  <td className="p-3">{money(trade.amount_eur)}</td>
                  <td className="p-3">{trade.environment === "unknown" ? copy.legacyEnvironment : copy.environments?.[trade.environment] || copy.unknown}</td>
                  <td className="p-3">{copy.executionModes?.[trade.execution_mode] || copy.unknown}</td>
                  <td className="p-3">{copy.tradeStatuses?.[trade.status] || copy.unknown}</td>
                </tr>
              ))}</tbody>
            </table>
          </div>
          {!loading.trades && !allTrades.items.length && <p className="py-6 text-sm text-slate-500">{copy.noTrades}</p>}
          {allTrades.has_more && <button type="button" disabled={loading.trades} onClick={() => onLoadAllTrades(allTrades.next_offset)} className="mt-4 rounded-lg border border-slate-200 px-4 py-2 text-sm font-bold text-blue-700">{copy.loadMore}</button>}
        </section>
      ) : (
        <>
          <div className="overflow-hidden rounded-xl border border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-950" aria-label={copy.botListLabel}>
            {bots.map((bot) => {
              const selected = bot.id === activeBot?.id;
              const botRisk = ["unknown_exchange_state", "sending"].includes(bot.pendingOrder?.status)
                ? "unknown_exchange_state" : ["ready", "pending"].includes(bot.pendingOrder?.status)
                  ? "execution_pending" : bot.pendingOrder ? "awaiting_exchange"
                    : !bot.is_active ? "paused" : (bot.decision?.safety_check?.state || "missing");
              return <button key={bot.id} type="button" aria-pressed={selected} onClick={() => onSelectBot(bot)}
                className={`flex w-full items-center gap-3 border-b border-slate-100 px-4 py-3 text-left last:border-b-0 dark:border-slate-800 ${selected ? "bg-blue-50 shadow-[inset_3px_0_0_#2563eb] dark:bg-blue-950/30" : "hover:bg-slate-50 dark:hover:bg-slate-900"}`}>
                <span className="flex-1 min-w-0"><strong className="block truncate text-sm text-slate-950 dark:text-white">{bot.name}</strong>
                  <small className="text-slate-500">{marketPairLabel(bot)} · {bot.strategy?.setup?.timeframe || "—"} · {bot.is_live ? copy.live : copy.paper}</small></span>
                <span className="rounded-full bg-slate-100 px-2.5 py-1 text-xs font-bold text-slate-700 dark:bg-slate-800 dark:text-slate-200">{copy.states?.[botRisk] || botRisk}</span>
                <ChevronRight size={16} className="text-slate-400" />
              </button>;
            })}
            {!bots.length && <p className="p-5 text-sm text-slate-500">{copy.noBots}</p>}
          </div>

          {activeBot && <article className="space-y-5 rounded-2xl border border-slate-200 bg-white p-5 dark:border-slate-800 dark:bg-slate-950 sm:p-6">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div><div className="text-[10px] font-black uppercase tracking-widest text-blue-700">{copy.botOverview}</div>
                <h2 className="mt-1 text-2xl font-black text-slate-950 dark:text-white">{activeBot.name}</h2>
                <p className="mt-1 text-sm text-slate-500">{activeBot.strategy?.name || "—"} · {symbol} · {timeframe}</p></div>
              <div className="flex flex-wrap gap-2 text-xs font-bold">
                <span className="rounded-full bg-blue-50 px-3 py-1 text-blue-700">{activeBot.is_live ? copy.live : copy.paper}</span>
                <span className="rounded-full bg-emerald-50 px-3 py-1 text-emerald-700">{activeBot.is_active ? copy.active : copy.paused}</span>
                <span className="rounded-full bg-slate-100 px-3 py-1 text-slate-700">{modeLabel}</span>
              </div>
            </div>

            {activeBot.is_live && !activeBot.is_active ? (
              <section className="rounded-xl border border-amber-200 bg-amber-50 p-4 text-amber-900" role="status">
                <h3 className="font-black">{copy.deferredLiveTitle}</h3>
                <p className="mt-1 text-sm">{copy.deferredLiveBody}</p>
                <button type="button" onClick={() => onOpenSettings("portfolio", activeBot)}
                  className="mt-2 text-sm font-bold text-blue-700 underline">{copy.deferredLiveLimits}</button>
              </section>
            ) : null}

            {!activeBot.is_live && activeBot.is_active && dcaSchedule?.due_today === false && (
              <section className="rounded-xl border border-blue-200 bg-blue-50 p-4 text-blue-950" role="status">
                <h3 className="font-bold">{copy.dcaNotDueTitle}</h3>
                <p className="mt-1 text-sm">{copy.dcaNotDueBody?.replace("{date}", nextDcaDate || dcaSchedule.next_due_date)}</p>
              </section>
            )}

            <section className={`rounded-xl border p-4 ${riskTone}`} aria-live="polite">
              <div className="flex items-center gap-2 text-xs font-black uppercase tracking-wider"><AlertTriangle size={16} />{copy.now}</div>
              <h3 className="mt-2 text-lg font-black">{riskTitle}</h3>
              <p className="mt-1 text-sm">{state === "paused" ? copy.pausedReason : riskReason}</p>
              <p className="mt-3 text-sm"><strong>{copy.nextStep}:</strong> {state === "paused" ? (pausedPaperWithoutCash ? copy.fundAndResumeStep : copy.resumeStep) : nextStepText}</p>
            </section>

            <div className="flex flex-wrap gap-2">
              {!activeBot.is_live && Number(activeBot.paper_initial_cash_eur || 0) === 0 && !portfolio?.stats?.paper_cash_configured && <button type="button" onClick={() => setEditingCash((value) => !value)} className="rounded-lg bg-blue-600 px-3 py-2 text-sm font-bold text-white">{copy.setPaperCash}</button>}
              <button type="button" disabled={changingActivity} onClick={toggleActivity} className="rounded-lg border border-slate-200 px-3 py-2 text-sm font-bold text-slate-700 dark:text-slate-200">{activeBot.is_active ? copy.pauseBot : copy.resumeBot}</button>
              <button type="button" onClick={() => onOpenSettings("general", activeBot)} className="rounded-lg border border-slate-200 px-3 py-2 text-sm font-bold text-slate-700 dark:text-slate-200">{copy.settings}</button>
              {!activeBot.is_live && <button type="button" disabled={!activeBot.is_active || Boolean(orderState) || ["executed", "skipped"].includes(decision?.status)} onClick={() => onGenerate(activeBot)} className="rounded-lg border border-slate-200 px-3 py-2 text-sm font-bold text-slate-700 disabled:opacity-50 dark:text-slate-200">{copy.checkAgain}</button>}
              {activeBot.is_live && decision?.id && <button type="button"
                disabled={!activeBot.is_active || Boolean(orderState) || ["executed", "skipped"].includes(decision?.status)}
                onClick={() => openFinnContext({
                  query: (copy.livePreflightPrompt || "Doe live preflight voor bot-decision {decision_id}")
                    .replace("{decision_id}", String(decision.id)),
                  context: { bot_id: activeBot.id, decision_id: decision.id, symbol },
                  autoSubmit: true,
                })}
                className="rounded-lg border border-blue-200 bg-blue-50 px-3 py-2 text-sm font-bold text-blue-700 disabled:opacity-50">
                {copy.livePreflight || "Live preflight"}
              </button>}
              <button type="button" disabled={Boolean(orderState) && !tradeActive} onClick={onTrade} className="rounded-lg border border-slate-200 px-3 py-2 text-sm font-bold text-slate-700 disabled:opacity-50 dark:text-slate-200">{tradeActive ? copy.closeTrade : copy.trade}</button>
            </div>
            {activityError && <p role="alert" className="text-sm text-red-700">{activityError}</p>}

            {editingCash && !activeBot.is_live && Number(activeBot.paper_initial_cash_eur || 0) === 0 && !portfolio?.stats?.paper_cash_configured && <form onSubmit={saveCash} className="rounded-xl border border-blue-200 bg-blue-50 p-4">
              <label className="block text-sm font-bold text-slate-800" htmlFor="paper-cash-input">{copy.paperCashInput}</label>
              <p className="mt-1 text-xs text-slate-600">{copy.paperCashExplanation}</p>
              <div className="mt-3 flex flex-wrap gap-2"><input id="paper-cash-input" type="number" min="0.01" max="100000000" step="0.01" required value={cashInput} onChange={(event) => setCashInput(event.target.value)} className="min-h-10 rounded-lg border border-slate-300 bg-white px-3 text-sm" />
                <button type="submit" disabled={savingCash || !cashAcknowledged} className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-bold text-white disabled:opacity-50">{copy.saveCash}</button></div>
              <label className="mt-3 flex items-start gap-2 text-sm text-slate-700"><input type="checkbox" checked={cashAcknowledged} onChange={(event) => setCashAcknowledged(event.target.checked)} className="mt-1" />{copy.paperCashAcknowledgement}</label>
              {cashError && <p role="alert" className="mt-2 text-sm text-red-700">{cashError}</p>}
            </form>}

            <section className="rounded-xl border border-slate-200 p-4 dark:border-slate-800" aria-label={copy.safetyTitle}>
              <div className="flex items-center justify-between gap-3"><h3 className="flex items-center gap-2 text-base font-black text-slate-950 dark:text-white"><ShieldCheck size={18} className="text-blue-700" />{copy.safetyTitle}</h3><span className="text-xs font-bold text-slate-600 dark:text-slate-300">{riskTitle}</span></div>
              <p className="mt-2 text-sm font-bold text-slate-800 dark:text-slate-200">{state === "paused" ? copy.pausedReason : riskReason}</p>
              <div className="mt-3 grid gap-2 text-sm sm:grid-cols-3">
                <div className="rounded-lg bg-slate-50 p-3 dark:bg-slate-900"><small className="block text-slate-500">{orderState ? copy.orderSubmittedAt : state === "paused" ? copy.lastKnownCheck : copy.lastCheck}</small><strong>{checkedAt}</strong></div>
                <div className="rounded-lg bg-slate-50 p-3 dark:bg-slate-900"><small className="block text-slate-500">{copy.allowedOrder}</small><strong>{orderState || !Number(risk.proposed_amount_eur) || ["paused", "stale", "missing", "error"].includes(state) ? "—" : money(risk.checked_amount_eur ?? risk.allowed_amount_eur)}</strong></div>
                <div className="rounded-lg bg-slate-50 p-3 dark:bg-slate-900"><small className="block text-slate-500">{activeBot.is_live ? copy.exchangeCash : copy.paperCash}</small><strong>{activeBot.is_live ? copy.seeExchange : availableCash}</strong></div>
              </div>
              {Number(risk.proposed_amount_eur || 0) > 0 && state !== "paused" && (
                <p className="mt-3 text-sm font-semibold text-slate-700 dark:text-slate-200">
                  {copy.proposedAmount || "Voorgesteld"}: {money(risk.proposed_amount_eur)} → {copy.checkedAmount || "Na limieten"}: {money(risk.checked_amount_eur ?? risk.allowed_amount_eur)}
                </p>
              )}
              {explanations.length > 0 && (
                <ul className="mt-2 space-y-1 text-sm text-slate-700 dark:text-slate-200" aria-label={copy.adjustmentReasons || "Redenen voor aanpassing of blokkade"}>
                  {explanations.map((item, index) => (
                    <li key={`${item.code || "reason"}-${index}`}>
                      • {paperPriceKey && item.code === "market_price_stale"
                        ? riskReason : copy.riskCodes?.[item.code] || item.message || copy.reasonUnavailable}
                      {Number.isFinite(Number(item.from_amount_eur)) && Number.isFinite(Number(item.to_amount_eur))
                        ? `: ${money(item.from_amount_eur)} → ${money(item.to_amount_eur)}` : ""}
                    </li>
                  ))}
                </ul>
              )}
              <details className="mt-3 border-t border-slate-200 pt-3"><summary className="cursor-pointer text-sm font-bold text-blue-700">{copy.allLimits}</summary>
                <dl className="mt-3 grid gap-2 text-sm sm:grid-cols-2"><div><dt>{copy.budgetLimit}</dt><dd>{money(activeBot.budget?.total_eur)}</dd></div><div><dt>{copy.dailyLimit}</dt><dd>{money(activeBot.budget?.daily_limit_eur)}</dd></div><div><dt>{copy.minOrder}</dt><dd>{activeBot.budget?.min_order_eur == null ? "—" : money(activeBot.budget.min_order_eur)}</dd></div><div><dt>{copy.maxOrder}</dt><dd>{money(activeBot.budget?.max_order_eur)}</dd></div><div><dt>{copy.assetExposure}</dt><dd>{activeBot.budget?.max_asset_exposure_pct ?? 100}%</dd></div></dl>
                <p className="mt-3 text-xs text-slate-500">{copy.zeroLimitMeaning}</p>
              </details>
            </section>

            <SystemConnectivity variant="bot" />

            <div className="grid gap-4 lg:grid-cols-2">
              <section className="rounded-xl border border-slate-200 p-4 dark:border-slate-800"><div className="flex flex-wrap items-center justify-between gap-2"><h3 className="font-black text-slate-950 dark:text-white">{copy.planExecution}</h3><button type="button" onClick={() => setShowStrategyTest((value) => !value)} aria-expanded={showStrategyTest} className="text-sm font-bold text-blue-700">{copy.strategyTest?.title}</button></div>
                <dl className="mt-3 space-y-2 text-sm"><div className="flex justify-between gap-3"><dt>{copy.strategy}</dt><dd className="font-bold">{activeBot.strategy?.name || "—"}</dd></div><div className="flex justify-between gap-3"><dt>{copy.execution}</dt><dd className="font-bold">{modeLabel}</dd></div><div className="flex justify-between gap-3"><dt>{copy.environment}</dt><dd className="font-bold">{activeBot.is_live ? copy.live : copy.paper}</dd></div></dl>
              </section>
              <section className="rounded-xl border border-slate-200 p-4 dark:border-slate-800"><div className="flex justify-between gap-3"><h3 className="font-black text-slate-950 dark:text-white">{copy.budgetLimits}</h3><button type="button" onClick={() => onOpenSettings("portfolio", activeBot)} className="text-sm font-bold text-blue-700">{copy.adjust}</button></div>
                <p className="mt-3 text-sm">{money(portfolio?.stats?.invested_eur)} {copy.usedOf} {money(activeBot.budget?.total_eur)} {copy.limit}</p>
                <p className="mt-2 text-xs text-slate-500">{copy.budgetNotCash}</p>
              </section>
              <section className="rounded-xl border border-slate-200 p-4 dark:border-slate-800 lg:col-span-2"><h3 className="font-black text-slate-950 dark:text-white">{historyOnlyDecision ? copy.previousRecordedDecision : copy.lastDecision}</h3>
                <p className="mt-2 text-sm font-bold">{lastRecordedDecision?.action ? (copy.actions?.[String(lastRecordedDecision.action).toLowerCase()] || lastRecordedDecision.action) : copy.noDecision}</p>
                {historyOnlyDecision && <p className="mt-1 text-xs text-slate-500">{historicalDecisionAt ? `${formatDateTime(historicalDecisionAt, locale)} · ` : ""}{copy.historicalDecisionHint}</p>}
                <p className="mt-1 text-sm text-slate-500">{lastRecordedDecision
                  ? (decision && (["blocked", "reduced", "error"].includes(risk.state) || explanations.length > 0)
                    ? riskReason : strategyReason || copy.riskCodes?.[recordedSafety.reason_code] || copy.reasonUnavailable)
                  : copy.noDecision}</p>
              </section>
            </div>

            {showStrategyTest && <StrategyTestPanel key={activeBot.id} bot={activeBot} onBacktest={onBacktest} />}

            <section className="rounded-xl border border-slate-200 p-4 dark:border-slate-800" aria-label={copy.recentTrades}>
              <div className="flex flex-wrap items-center justify-between gap-3">
                <h3 className="font-black text-slate-950 dark:text-white">{copy.recentTrades}</h3>
                <button type="button" onClick={() => setView("trades")} className="text-sm font-bold text-blue-700">{copy.allTrades}</button>
              </div>
              <div className="mt-3 flex gap-3 border-b border-slate-200" role="tablist" aria-label={copy.recentTrades}>
                <button type="button" role="tab" aria-selected={activityView === "trades"} onClick={() => setActivityView("trades")} className={`pb-2 text-sm font-bold ${activityView === "trades" ? "border-b-2 border-blue-600 text-blue-700" : "text-slate-500"}`}>{copy.activityTrades}</button>
                <button type="button" role="tab" aria-selected={activityView === "decisions"} onClick={() => setActivityView("decisions")} className={`pb-2 text-sm font-bold ${activityView === "decisions" ? "border-b-2 border-blue-600 text-blue-700" : "text-slate-500"}`}>{copy.activityDecisions}</button>
              </div>
              <div className="mt-3 max-h-80 overflow-auto">
                <BotHistoryTable history={recentActivity.filter((item) => activityView === "trades" ? item.is_trade : !item.is_trade)} emptyMessage={activityView === "trades" ? copy.noTrades : copy.noDecisions} botIsLive={activeBot.is_live} botSymbol={activeBot.symbol} />
              </div>
            </section>
          </article>}
        </>
      )}
    </section>
  );
}
