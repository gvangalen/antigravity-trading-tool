"use client";

import { useEffect, useMemo, useRef, useState } from "react";

import BotDecisionCard from "@/components/bot/BotDecisionCard";
import BotPortfolioCard from "@/components/bot/BotPortfolioCard";
import BotHistoryTable from "@/components/bot/BotHistoryTable";
import BotSettingsMenu from "@/components/bot/BotSettingsMenu";
import TradePlanCard from "@/components/bot/TradePlanCard";
import MarketDecisionCard from "@/components/bot/MarketDecisionCard";
import GuardrailsPanel from "@/components/bot/GuardrailsPanel";
import { useMarketIntelligence } from "@/hooks/useMarketIntelligence";

import {
  Bot,
  MoreVertical,
  Clock,
  Shield,
  Layers,
  Rocket,
  Activity,
  RotateCcw,
  Zap,
  ChevronDown,
  ChevronUp,
} from "lucide-react";

export default function BotAgentCard({
  bot,
  decision,
  order,
  portfolio,
  history = [],
  trades = [],
  loadingDecision = false,

  marketIntelligence,
  loadingMarketIntelligence = false,

  onGenerate,
  onExecute,
  onSkip,
  onOpenSettings,

  onSaveTradePlan,
  onBacktest,
}) {
  if (!bot) return null;

  const [backtestResult, setBacktestResult] = useState(null);
  const [backtestLoading, setBacktestLoading] = useState(false);
  const [scenarios, setScenarios] = useState({});
  const [scenariosLoading, setScenariosLoading] = useState(false);

  const [showHistory, setShowHistory] = useState(false);
  const [showSettings, setShowSettings] = useState(false);
  const settingsRef = useRef(null);

  const [savingPlan, setSavingPlan] = useState(false);
  const [saveError, setSaveError] = useState(null);

  const [isExpanded, setIsExpanded] = useState(false);

  const isAuto = bot?.mode === "auto";

  /* ================= SAFE BASE DATA ================= */

  const safeDecision = decision || {};
  const safeOrder = order || {};

  const symbol = (
    bot?.strategy?.setup?.symbol ||
    bot?.strategy?.symbol ||
    bot?.symbol ||
    safeDecision?.symbol ||
    "BTC"
  ).toUpperCase();

  const timeframe =
    bot?.strategy?.setup?.timeframe ||
    bot?.strategy?.timeframe ||
    bot?.timeframe ||
    "—";

  const statusLabel = (safeDecision?.action || "OBSERVE").toUpperCase();

  const confidence =
    safeDecision?.confidence_label ||
    safeDecision?.confidence ||
    "LOW";

  /* ================= DYNAMIC BOT BRAIN ================= */
  const {
    data: botMarketIntelligence,
    loading: loadingBotMarketIntelligence,
  } = useMarketIntelligence(symbol);

  /* ================= BOT STATE ================= */
  const normalizedAction = String(safeDecision?.action || "").toLowerCase();

  const botState = bot?.is_active
    ? normalizedAction === "hold" || normalizedAction === "observe" || !normalizedAction
      ? "waiting"
      : "live"
    : "paused";

  const lastRun =
    bot?.last_run
      ? new Date(bot.last_run).toLocaleTimeString("nl-NL", {
          hour: "2-digit",
          minute: "2-digit",
        })
      : null;

  /* ================= DEBUG ================= */
  useEffect(() => {
    console.log("🤖 BOT", bot);
    console.log("📊 DECISION RAW", decision);
    console.log("📦 SCORES_JSON", decision?.scores_json);
    console.log("🛡 GUARDRAILS RAW", decision?.guardrails_result);
    console.log("🧭 TRADE PLAN RAW", decision?.trade_plan);
  }, [bot, decision]);


  /* ================= NORMALIZE DECISION ================= */
  const normalizedDecision = useMemo(() => {
  const scores = safeDecision?.scores_json || {};
  const guardrails =
    safeDecision?.guardrails_result ||
    safeDecision?.guardrails ||
    {};
  const tradePlan = safeDecision?.trade_plan || {};

  const rawPositionSize =
    safeDecision?.position_size ??
    scores?.position_size ??
    0.5;

  const parsedPositionSize = Number(rawPositionSize);

  const normalizedPositionSize = Math.max(
    0,
    Math.min(
      Number.isFinite(parsedPositionSize) ? parsedPositionSize : 0.5,
      1
    )
  );

  const normalized = {
    ...safeDecision,

    scores_json: scores,
    metrics: safeDecision?.metrics || {},

    guardrails_result: guardrails,
    guardrails: guardrails,

    trade_plan: tradePlan,

    transition_risk:
      scores?.transition_risk ??
      safeDecision?.transition_risk ??
      null,

    market_pressure:
      scores?.market_pressure ??
      safeDecision?.market_pressure ??
      null,

    warnings:
      scores?.warnings ??
      safeDecision?.warnings ??
      [],

    requested_amount_eur:
      safeDecision?.requested_amount_eur ??
      scores?.requested_amount_eur ??
      0,

    amount_eur:
      safeDecision?.amount_eur ??
      scores?.amount_eur ??
      0,

    base_amount:
      safeDecision?.base_amount ??
      scores?.base_amount ??
      safeDecision?.requested_amount_eur ??
      0,

    execution_mode:
      safeDecision?.execution_mode ??
      scores?.execution_mode ??
      "fixed",

    decision_curve_name:
      safeDecision?.decision_curve_name ??
      scores?.decision_curve_name ??
      null,

    setup_match:
      safeDecision?.setup_match ??
      scores?.setup_match ??
      null,

    // ✅ MARKET SUGGESTION / POSITION SIZE
    position_size: normalizedPositionSize,

    // ✅ STRATEGY EXPOSURE BLIJFT APART
    exposure_multiplier:
      safeDecision?.exposure_multiplier ??
      scores?.exposure_multiplier ??
      1,
  };

  return normalized;
}, [safeDecision]);

  /* ================= HISTORY ================= */
  const combinedHistory = useMemo(() => {
    const botHistory = (history || []).filter((h) => h.bot_id === bot.id);

    const tradeAsHistory = (trades || []).map((t) => ({
      id: t.id,
      bot_id: bot.id,
      created_at: t.executed_at,
      date: t.executed_at,
      side: t.side,
      qty: t.qty,
      price: t.price,
      amount_eur: t.amount_eur,
      confidence: t.confidence || null,
      status: "executed",
      symbol: t.symbol,
      mode: t.mode,
      action: t.side,
    }));

    const merged = [...tradeAsHistory, ...botHistory].sort((a, b) => {
      const d1 = new Date(a.created_at || a.date || 0);
      const d2 = new Date(b.created_at || b.date || 0);
      return d2 - d1;
    });

    return merged;
  }, [history, trades, bot.id]);

  /* ================= CLOSE SETTINGS ================= */

  useEffect(() => {
    if (!showSettings) return;

    const handler = (e) => {
      if (!settingsRef.current) return;
      if (settingsRef.current.contains(e.target)) return;
      setShowSettings(false);
    };

    document.addEventListener("mousedown", handler);
    document.addEventListener("touchstart", handler);

    return () => {
      document.removeEventListener("mousedown", handler);
      document.removeEventListener("touchstart", handler);
    };
  }, [showSettings]);

  /* ================= RISK BADGE ================= */

  const riskConfig = {
    conservative: {
      label: "Risk: Conservative",
      className: "bg-green-100 text-green-700 border-green-200",
      icon: <Shield size={12} />,
    },
    balanced: {
      label: "Risk: Balanced",
      className: "bg-yellow-100 text-yellow-700 border-yellow-200",
      icon: <Layers size={12} />,
    },
    aggressive: {
      label: "Risk: Aggressive",
      className: "bg-red-100 text-red-700 border-red-200",
      icon: <Rocket size={12} />,
    },
  };

  const risk =
    riskConfig[String(bot?.risk_profile || "balanced").toLowerCase()] ||
    riskConfig.balanced;

  /* ================= SAVE TRADE PLAN ================= */

  const decisionId =
    normalizedDecision?.id ??
    normalizedDecision?.decision_id ??
    null;

  const botId =
    normalizedDecision?.bot_id ??
    bot?.id ??
    null;

  const canSavePlan =
    !isAuto &&
    !!onSaveTradePlan &&
    !!decisionId &&
    !!botId;

  const handleSaveTradePlan = async (planDraft) => {
    if (!canSavePlan) return;

    setSaveError(null);
    setSavingPlan(true);

    try {
      await onSaveTradePlan({
        bot_id: botId,
        decision_id: decisionId,
        draft: planDraft,
      });
    } catch (e) {
      console.error("❌ Save plan error", e);
      setSaveError(e?.message || "Opslaan mislukt");
      throw e;
    } finally {
      setSavingPlan(false);
    }
  };

  /* =====================================================
     🔁 HANDLE BACKTEST
  ===================================================== */
  const handleBacktest = async (scenario = "default") => {
    if (!onBacktest) return;
    setBacktestLoading(true);
    setBacktestResult(null);

    try {
      const res = await onBacktest(bot.id, scenario);
      setBacktestResult(res);
    } catch (e) {
      console.error("Backtest failed", e);
    } finally {
      setBacktestLoading(false);
    }
  };

  /* =====================================================
     🚀 HANDLE RUN SCENARIOS (PARALLEL)
  ===================================================== */
  const handleRunScenarios = async () => {
    if (!onBacktest) return;
    
    setScenariosLoading(true);
    setScenarios({});

    try {
      const types = ["default", "aggressive", "conservative"];
      const results = await Promise.all(
        types.map(t => onBacktest(bot.id, t))
      );
      
      const scenarioMap = {};
      results.forEach((res, i) => {
        if (res?.ok) {
          scenarioMap[types[i]] = res;
        }
      });
      
      setScenarios(scenarioMap);
    } catch (e) {
      console.error("Scenario run failed", e);
    } finally {
      setScenariosLoading(false);
    }
  };

  /* ================= PLAN SOURCE ================= */
  const planSource = useMemo(() => {
    return normalizedDecision?.trade_plan || null;
  }, [normalizedDecision?.trade_plan]);

  
  /* ================= ORDER STATE ================= */
  const hasExecutableTrade = useMemo(() => {
    if (order) return true;

    const action = String(normalizedDecision?.action || "").toLowerCase();
    const amount = Number(normalizedDecision?.amount_eur ?? 0);

    return (action === "buy" || action === "sell" || action === "short") && amount > 0;
  }, [order, normalizedDecision]);

  /* ================= RENDER ================= */

  return (
    <div className="w-full rounded-[2.5rem] border border-slate-200 bg-card shadow-xl overflow-hidden flex flex-col transition-all hover:shadow-2xl">
      
      {/* 🕋 MODULAR HEADER HUD */}
      <div className="p-8 pb-4 space-y-6">
        <div className="flex items-start justify-between gap-6">
          <div className="flex items-start gap-5">
            <div className="w-14 h-14 rounded-2xl bg-[var(--color-border-subtle)] border border-slate-100 text-[var(--primary)] flex items-center justify-center shadow-inner group-hover:scale-105 transition-transform mt-1">
               <Bot size={28} className="opacity-80" />
            </div>

            <div className="space-y-2.5">
              <div className="flex items-center gap-3">
                <h2 className="text-2xl font-black text-foreground tracking-tight">{bot?.name}</h2>
                <div className={`w-2.5 h-2.5 rounded-full ${botState === 'live' ? 'bg-green-500 shadow-[0_0_12px_rgba(34,197,94,0.6)] animate-pulse' : botState === 'waiting' ? 'bg-yellow-400' : 'bg-slate-300'}`} />
              </div>
              
              <div className="flex items-center gap-3 text-[10px] font-black uppercase tracking-[0.15em] text-slate-400">
                <span className="text-dim bg-[var(--color-border-subtle)] px-2 py-0.5 rounded-md">{symbol}</span>
                <div className="w-1 h-1 rounded-full bg-slate-300" />
                <span>{timeframe}</span>
                {bot?.strategy && (
                  <>
                    <div className="w-1 h-1 rounded-full bg-slate-300" />
                    <span className="text-[var(--primary)] font-bold">{bot.strategy.name}</span>
                  </>
                )}
              </div>

              {/* HORIZONTAL PILLS CONTAINER */}
              <div className="flex flex-wrap items-center gap-2 pt-1.5">
                <div className={`px-3 py-1.5 rounded-xl border text-[9px] font-black uppercase tracking-widest shadow-sm flex items-center gap-1.5 ${risk.className}`}>
                   {risk.icon}
                   {risk.label.replace('Risk: ', '')}
                </div>
                
                <div className="px-3 py-1.5 rounded-xl border border-slate-200 bg-[var(--color-border-subtle)] text-[9px] font-black text-muted uppercase tracking-widest shadow-sm flex items-center gap-1.5">
                   <Activity size={10} />
                   {isAuto ? "AUTO-PILOT" : "MANUAL-LINK"}
                </div>

                <div className={`px-3 py-1.5 rounded-xl border text-[9px] font-black uppercase tracking-widest shadow-sm flex items-center gap-1.5 ${bot?.is_live ? 'bg-emerald-100 text-emerald-700 border-emerald-200' : 'bg-blue-100 text-blue-700 border-blue-200'}`}>
                   {bot?.is_live ? <Zap size={10} /> : <Clock size={10} />}
                   {bot?.is_live ? "LIVE" : "PAPER"}
                </div>

                <button
                  onClick={() => handleBacktest()}
                  disabled={backtestLoading || scenariosLoading}
                  className="h-8 px-3 rounded-xl border border-slate-200 bg-card text-muted hover:text-[var(--primary)] hover:border-[var(--primary)] transition-all shadow-sm active:scale-95 flex items-center gap-1.5 text-[9px] font-black uppercase tracking-wider disabled:opacity-50"
                >
                  {backtestLoading ? (
                    <div className="w-2.5 h-2.5 border-2 border-slate-300 border-t-[var(--primary)] animate-spin rounded-full" />
                  ) : (
                    <RotateCcw size={11} className="opacity-70" />
                  )}
                  {backtestLoading ? "ANALYZING..." : "RUN BACKTEST"}
                </button>

                <button
                  onClick={handleRunScenarios}
                  disabled={backtestLoading || scenariosLoading}
                  className="h-8 px-3 rounded-xl border border-indigo-200 bg-indigo-50 text-indigo-600 hover:bg-indigo-100 transition-all shadow-sm active:scale-95 flex items-center gap-1.5 text-[9px] font-black uppercase tracking-wider disabled:opacity-50"
                >
                  {scenariosLoading ? (
                    <div className="w-2.5 h-2.5 border-2 border-indigo-300 border-t-indigo-600 animate-spin rounded-full" />
                  ) : (
                    <Activity size={11} className="opacity-70" />
                  )}
                  SCENARIOS
                </button>
              </div>
            </div>
          </div>

          <div className="relative" ref={settingsRef}>
            <button
              className="w-10 h-10 flex items-center justify-center rounded-xl border border-slate-200 bg-card text-secondary hover:text-slate-800 hover:border-slate-400 transition-all shadow-sm active:scale-95"
              onClick={(e) => {
                e.stopPropagation();
                setShowSettings((v) => !v);
              }}
            >
              <MoreVertical size={20} />
            </button>

            {showSettings && (
              <div className="absolute right-0 mt-3 z-[100] min-w-[220px]">
                <BotSettingsMenu
                  onOpen={(type) => {
                    setShowSettings(false);
                    onOpenSettings?.(type, bot);
                  }}
                />
              </div>
            )}
          </div>
        </div>

        {/* 📊 SYSTEM STATUS BAR (UPGRADED PADDING) */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 p-2 bg-[var(--color-border-subtle)] border border-slate-100 rounded-[1.5rem]">
          <div className="bg-card rounded-xl p-4 border border-slate-100 shadow-sm">
             <div className="text-[9px] font-black text-secondary uppercase tracking-widest mb-1.5 opacity-60">Status Response</div>
             <div className={`text-xs font-black uppercase tracking-tight flex items-center gap-2 ${bot?.is_live ? 'text-emerald-600' : 'text-blue-600'}`}>
                <div className={`w-2 h-2 rounded-full ${botState === 'live' ? (bot?.is_live ? 'bg-emerald-500' : 'bg-green-500') : 'bg-slate-400'}`} />
                {bot?.is_live ? 'LIVE' : 'PAPER'} {botState}
             </div>
          </div>

          <div className="bg-card rounded-xl p-4 border border-slate-100 shadow-sm">
             <div className="text-[9px] font-black text-secondary uppercase tracking-widest mb-1.5 opacity-60">Market Action</div>
             <div className="text-xs font-black text-[var(--primary)] uppercase tracking-tight flex items-center gap-2">
                <Rocket size={12} strokeWidth={3} />
                {statusLabel}
             </div>
          </div>

          <div className="bg-card rounded-xl p-4 border border-slate-100 shadow-sm">
             <div className="text-[9px] font-black text-secondary uppercase tracking-widest mb-1.5 opacity-60">Logic Confidence</div>
             <div className="text-xs font-black text-foreground uppercase tracking-tight flex items-center gap-2">
                <Layers size={12} strokeWidth={3} />
                {confidence}
             </div>
          </div>

          <div className="bg-card rounded-xl p-4 border border-slate-100 shadow-sm">
             <div className="text-[9px] font-black text-secondary uppercase tracking-widest mb-1.5 opacity-60">Telemetry Sync</div>
             <div className="text-xs font-black text-muted tracking-tight font-mono">{lastRun || "SYNCING..."}</div>
          </div>
        </div>

        {/* 🔽 EXPAND TOGGLE 🔽 */}
        <button
          onClick={(e) => { e.stopPropagation(); setIsExpanded(v => !v); }}
          className="w-full mt-4 py-3 border border-slate-200 dark:border-slate-800 border-dashed rounded-xl text-[10px] font-black text-slate-400 dark:text-slate-500 hover:text-slate-600 dark:hover:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-800/50 transition-colors flex items-center justify-center gap-2 uppercase tracking-[0.2em] shadow-sm active:scale-[0.99]"
        >
          {isExpanded ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
          {isExpanded ? "Collapse Diagnostics" : "View Full Diagnostics"}
        </button>

        {/* 📊 BACKTEST RESULTS SECTION */}
        {/* ⏳ LOADING STATE */}
        {(backtestLoading || scenariosLoading) && (
          <div className="mt-4 p-6 bg-[var(--color-border-subtle)] border border-slate-100 rounded-2xl flex items-center justify-center gap-4 animate-pulse">
            <div className="w-5 h-5 border-2 border-slate-300 border-t-[var(--primary)] animate-spin rounded-full" />
            <div className="text-xs font-black text-secondary uppercase tracking-[0.2em]">
              {scenariosLoading ? "Crunching parallel scenarios..." : "Analyzing last 30 days..."}
            </div>
          </div>
        )}

        {/* 📊 BACKTEST RESULTS SECTION (LIGHT MODE) */}
        {backtestResult && !backtestLoading && (
          <div className="mt-4 space-y-4 animate-fade-in">
            <div className="bg-card rounded-[2rem] border border-slate-200 shadow-xl overflow-hidden relative group">
              <div className="absolute top-0 right-0 w-32 h-32 bg-indigo-50/50 blur-3xl rounded-full translate-x-1/2 -translate-y-1/2 opacity-50" />
              
              <div className="p-8 pb-4 flex items-center justify-between border-b border-slate-100">
                <div className="flex items-center gap-3">
                  <div className="w-8 h-8 rounded-lg bg-emerald-50 text-emerald-600 flex items-center justify-center border border-emerald-100">
                    <Activity size={16} strokeWidth={3} />
                  </div>
                  <h3 className="text-[10px] font-black text-secondary uppercase tracking-[0.2em]">{symbol} Performance Scan (V2)</h3>
                </div>
                <button 
                  onClick={() => setBacktestResult(null)}
                  className="w-8 h-8 rounded-lg bg-[var(--color-border-subtle)] text-secondary hover:text-slate-600 transition-colors flex items-center justify-center border border-slate-200"
                >
                  <RotateCcw size={14} />
                </button>
              </div>

              <div className="grid grid-cols-2 md:grid-cols-4 divide-x divide-y md:divide-y-0 divide-slate-100">
                <div className="p-8 hover:bg-slate-50/50 transition-colors">
                  <div className="text-[9px] font-black text-secondary uppercase tracking-widest mb-2">Profit (€)</div>
                  <div className={`text-2xl font-black tracking-tighter ${backtestResult.return_pct >= 0 ? 'text-emerald-500' : 'text-red-500'}`}>
                    {backtestResult.return_pct >= 0 ? '+' : ''}
                    €{Math.round((backtestResult.return_pct / 100) * 10000).toLocaleString()}
                  </div>
                  <div className="text-[8px] font-bold text-secondary mt-1 italic">€10,000 model</div>
                </div>

                <div className="p-8 hover:bg-slate-50/50 transition-colors">
                  <div className="text-[9px] font-black text-secondary uppercase tracking-widest mb-2">ROI (%)</div>
                  <div className={`text-2xl font-black tracking-tighter ${backtestResult.return_pct >= 0 ? 'text-emerald-500' : 'text-red-500'}`}>
                    {backtestResult.return_pct >= 0 ? '+' : ''}{backtestResult.return_pct}%
                  </div>
                </div>

                <div className="p-8 hover:bg-slate-50/50 transition-colors">
                  <div className="text-[9px] font-black text-secondary uppercase tracking-widest mb-2">Win%</div>
                  <div className="text-2xl font-black text-foreground tracking-tighter">
                    {backtestResult.performance?.winrate}%
                  </div>
                  <div className="text-[8px] font-bold text-secondary mt-1 uppercase tracking-widest">
                    {backtestResult.performance?.wins}W / {backtestResult.performance?.losses}L
                  </div>
                </div>

                <div className="p-8 hover:bg-slate-50/50 transition-colors">
                  <div className="text-[9px] font-black text-secondary uppercase tracking-widest mb-2">Total Capital</div>
                  <div className="text-2xl font-black text-foreground tracking-tighter">
                    €{Math.round(10000 + ((backtestResult.return_pct / 100) * 10000)).toLocaleString()}
                  </div>
                  <div className="text-[8px] font-bold text-indigo-400 mt-1 uppercase tracking-widest">€10K START</div>
                </div>
              </div>

              <div className="p-6 bg-slate-50/80 border-t border-slate-100 flex flex-wrap items-center justify-between gap-4">
                <div className="flex flex-col">
                  <span className="text-[8px] font-bold text-secondary uppercase tracking-widest">Avg Trade</span>
                  <span className={`text-xs font-black ${backtestResult.performance?.expectancy >= 0 ? 'text-emerald-600' : 'text-red-500'}`}>
                    {backtestResult.performance?.expectancy >= 0 ? '+' : ''}{backtestResult.performance?.expectancy}%
                  </span>
                </div>
                <div className="flex flex-col">
                  <span className="text-[8px] font-bold text-secondary uppercase tracking-widest">Best Trade</span>
                  <span className="text-xs font-black text-emerald-600">+{backtestResult.performance?.best_trade_pct}%</span>
                </div>
                <div className="flex flex-col">
                  <span className="text-[8px] font-bold text-secondary uppercase tracking-widest">Worst Trade</span>
                  <span className="text-xs font-black text-red-400">{backtestResult.performance?.worst_trade_pct}%</span>
                </div>
                <div className="flex flex-col">
                  <span className="text-[8px] font-bold text-secondary uppercase tracking-widest">Executions</span>
                  <span className="text-xs font-black text-slate-600">
                    {backtestResult.total_trades} trades
                  </span>
                </div>
                <div className="flex flex-col text-right">
                  <span 
                    className="text-[8px] font-bold text-secondary uppercase tracking-widest cursor-help underline decoration-slate-200 decoration-dotted"
                    title="Expected average profit per trade based on historical performance"
                   >
                     Expectancy ?
                   </span>
                  <span className={`text-xs font-black ${backtestResult.performance?.expectancy >= 0 ? 'text-indigo-600' : 'text-red-500'}`}>
                    {backtestResult.performance?.expectancy >= 0 ? '+' : ''}{backtestResult.performance?.expectancy}%
                  </span>
                </div>
              </div>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
              <div className="p-5 bg-card border border-slate-100 rounded-2xl shadow-sm">
                <div className="text-[10px] font-black text-secondary uppercase tracking-widest mb-3">AI_SUMMARY</div>
                <div className="text-sm font-bold text-slate-700 leading-relaxed italic border-l-4 border-indigo-400 pl-4 py-1">
                  "{backtestResult.summary?.message || 'Geen details beschikbaar.'}"
                </div>
              </div>

              <div className="p-5 bg-slate-50/50 border border-slate-100 rounded-2xl shadow-sm">
                <div className="text-[10px] font-black text-secondary uppercase tracking-widest mb-3">RECENT_TRADES</div>
                <div className="space-y-2">
                  {backtestResult.trades?.length > 0 ? (
                    backtestResult.trades.map((t, i) => (
                      <div key={i} className="flex items-center justify-between bg-card px-3 py-2 rounded-xl border border-slate-100 shadow-xs">
                        <div className="flex items-center gap-3">
                           {t.type === 'buy' ? (
                             <div className="text-[10px] font-black text-indigo-500 bg-indigo-50 px-1.5 py-0.5 rounded border border-indigo-100">BUY</div>
                           ) : (
                             <div className="text-[10px] font-black text-orange-500 bg-orange-50 px-1.5 py-0.5 rounded border border-orange-100">SELL</div>
                           )}
                           <span className="text-xs font-bold text-muted tracking-tighter">€{t.price.toLocaleString()}</span>
                        </div>
                        <div className="flex items-center gap-2">
                           {t.pnl_pct !== null && (
                             <span className={`text-[10px] font-black ${t.pnl_pct >= 0 ? 'text-emerald-500' : 'text-red-400'}`}>
                               {t.pnl_pct >= 0 ? '+' : ''}{t.pnl_pct}%
                             </span>
                           )}
                           {t.status === 'open' ? (
                             <div className="w-2 h-2 rounded-full bg-yellow-400" />
                           ) : t.pnl_pct >= 0 ? (
                             <span className="text-emerald-500 font-bold">✔</span>
                           ) : (
                             <span className="text-red-400 font-bold font-mono">❌</span>
                           )}
                        </div>
                      </div>
                    ))
                  ) : (
                    <div className="text-[10px] font-bold text-secondary italic">No trades executed in last 30 days.</div>
                  )}
                </div>
              </div>
            </div>
          </div>
        )}

        {/* 🚀 SCENARIO COMPARISON TABLE (LIGHT MODE) */}
        {Object.keys(scenarios).length > 0 && !scenariosLoading && (
          <div className="mt-4 p-6 bg-[var(--color-border-subtle)] rounded-3xl border border-slate-200 shadow-sm animate-fade-in relative overflow-hidden">
             <div className="flex items-center justify-between mb-6">
                <div className="flex items-center gap-3">
                   <div className="w-8 h-8 rounded-lg bg-indigo-100 text-indigo-600 flex items-center justify-center border border-indigo-200">
                      <Zap size={18} strokeWidth={3} />
                   </div>
                   <h3 className="text-sm font-black text-foreground uppercase tracking-widest">Scenario Comparison</h3>
                </div>
                <button onClick={() => setScenarios({})} className="text-secondary hover:text-slate-600 transition-colors">
                   <RotateCcw size={14} />
                </button>
             </div>

             <div className="grid grid-cols-3 gap-4">
                {['default', 'aggressive', 'conservative'].map(type => {
                   const res = scenarios[type];
                   if (!res) return null;
                   
                   const allRes = Object.values(scenarios);
                   const maxReturn = Math.max(...allRes.map(r => r.return_pct));
                   const isBest = res.return_pct === maxReturn && allRes.length > 1;

                   return (
                      <div 
                        key={type} 
                        className={`p-5 rounded-2xl flex flex-col items-center text-center transition-all ${isBest ? 'bg-white border-2 border-indigo-500 shadow-lg shadow-indigo-100' : 'bg-white/50 border border-slate-200'}`}
                      >
                         <div className="flex items-center gap-2 mb-3">
                           <div className="text-[10px] font-black text-secondary uppercase tracking-[0.2em]">{type}</div>
                           {isBest && <span className="text-[10px]">🏆</span>}
                         </div>

                         <div className={`text-xl font-black tracking-tighter mb-1 ${res.return_pct >= 0 ? 'text-emerald-500' : 'text-red-500'}`}>
                            {res.return_pct >= 0 ? '+' : ''}{res.return_pct}%
                         </div>
                         
                         <div className="space-y-1">
                           <div className={`text-[12px] font-black ${isBest ? 'text-slate-900' : 'text-slate-600'}`}>
                             €{Math.round(10000 + ((res.return_pct / 100) * 10000)).toLocaleString()}
                           </div>
                           <div className="text-[9px] font-bold text-secondary uppercase tracking-widest">
                             {res.total_trades} trades
                           </div>
                         </div>
                      </div>
                   )
                })}
             </div>
          </div>
        )}
      </div>

      {/* 🚀 MAIN COCKPIT MODULES */}
      {isExpanded && (
        <>
          <div className="p-8 pt-4 space-y-10 border-t border-slate-100 dark:border-slate-800/50 mt-4 animate-fade-in">
            
            {/* Module 1: Portfolio & Safety Check */}
            <div className="bg-slate-50/50 rounded-[2rem] border border-slate-100 overflow-hidden shadow-sm">
              <div className="flex flex-col">
                <div className="flex-1 p-6 lg:p-8">
                  <BotPortfolioCard bot={portfolio} />
                </div>

                <div className="p-6 lg:p-8 bg-white/50 border-t border-slate-100">
                  <GuardrailsPanel
                    decision={normalizedDecision}
                    bot={bot}
                  />
                </div>
              </div>
            </div>

            {/* Module 2: Market Intelligence (THE BRAIN) */}
            <div className="bg-card rounded-[2rem] border border-slate-200 p-6 lg:p-8 shadow-sm">
              {loadingBotMarketIntelligence ? (
                <div className="flex items-center gap-3 text-xs font-black text-secondary uppercase tracking-widest p-10 justify-center">
                  <div className="w-4 h-4 rounded-full border-2 border-slate-200 border-t-[var(--primary)] animate-spin" />
                  Syncing Brain...
                </div>
              ) : (
                <MarketDecisionCard data={botMarketIntelligence} />
              )}
            </div>

            {/* Module 3: Execution Engine & Price Ladder */}
            <div className="bg-card rounded-[2rem] border border-slate-200 overflow-hidden shadow-md">
              <div className="flex flex-col">
                <div className="flex-1 p-6 lg:p-8">
                  <BotDecisionCard
                    bot={bot}
                    decision={normalizedDecision}
                    order={safeOrder}
                    loading={loadingDecision}
                    isAuto={isAuto}
                    onGenerate={onGenerate}
                    onExecute={!isAuto ? onExecute : undefined}
                    onSkip={!isAuto ? onSkip : undefined}
                  />
                </div>

                <div className="p-6 lg:p-8 bg-slate-50/30 border-t border-slate-100">
                  <TradePlanCard
                    decision={normalizedDecision}
                    tradePlan={planSource}
                    loading={loadingDecision}
                    allowManual={!isAuto}
                    onSave={canSavePlan ? handleSaveTradePlan : undefined}
                    saving={savingPlan}
                    error={saveError}
                  />
                </div>
              </div>
            </div>
          </div>

          {/* 📜 TERMINAL LOGS / HISTORY (BOTTOM BAR) */}
          <div className="mt-auto border-t border-slate-100 bg-[var(--color-border-subtle)] text-muted overflow-hidden">
            <button
              onClick={(e) => { e.stopPropagation(); setShowHistory((v) => !v); }}
              className="w-full p-5 lg:p-6 text-xs font-black uppercase tracking-[0.2em] hover:bg-slate-100/80 hover:text-slate-800 transition-all flex items-center justify-between group"
            >
              <div className="flex items-center gap-3">
                <Clock size={14} className="group-hover:rotate-[360deg] transition-transform duration-700" />
                {showHistory ? "SYSTEM_LOGS_MINIMIZE" : "SYSTEM_LOGS_OPEN"}
              </div>
              <div className="text-[10px] opacity-40">[{combinedHistory.length} ENTRIES]</div>
            </button>

            {showHistory && (
              <div className="p-6 bg-card border-t border-slate-100 max-h-[400px] overflow-y-auto animate-fade-slide">
                <BotHistoryTable history={combinedHistory} />
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
}
