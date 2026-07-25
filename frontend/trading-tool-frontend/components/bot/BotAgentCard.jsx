"use client";

import { useEffect, useMemo, useRef, useState } from "react";

import BotPortfolioCard from "@/components/bot/BotPortfolioCard";
import BotHistoryTable from "@/components/bot/BotHistoryTable";
import BotSettingsMenu from "@/components/bot/BotSettingsMenu";
import GuardrailsPanel from "@/components/bot/GuardrailsPanel";

import {
  Bot,
  MoreVertical,
  Clock,
  Shield,
  Layers,
  Rocket,
  Activity,
  RotateCcw,
  Sparkles,
  Wallet,
  Zap,
  ChevronDown,
  ChevronUp,
} from "lucide-react";
import { useTranslation } from "@/app/providers/I18nProvider";
import { formatCurrency, formatDateTime } from "@/lib/i18n";

export default function BotAgentCard({
  bot,
  decision,
  order,
  portfolio,
  history = [],
  trades = [],
  loadingDecision = false,
  loadingMarketIntelligence = false,
  onOpenSettings,
  onBacktest,
  onAskFinn,
  finnActionLabel = "Ask FINN",
  onTrade,
  tradeActionLabel = "Trade",
  tradeActive = false,
  compact = false,
}) {
  const { t, locale } = useTranslation();
  const copy = t?.botPage?.agentCard || {};
  if (!bot) return null;

  const [backtestResult, setBacktestResult] = useState(null);
  const [backtestLoading, setBacktestLoading] = useState(false);
  const [scenarios, setScenarios] = useState({});
  const [scenariosLoading, setScenariosLoading] = useState(false);

  const [showHistory, setShowHistory] = useState(false);
  const [showSettings, setShowSettings] = useState(false);
  const settingsRef = useRef(null);

  const [isExpanded, setIsExpanded] = useState(false);

  const isAuto = bot?.mode === "auto";

  /* ================= SAFE BASE DATA ================= */

  const safeDecision = decision || {};

  const symbol = (
    bot?.strategy?.setup?.symbol ||
    bot?.strategy?.symbol ||
    bot?.symbol ||
    safeDecision?.symbol ||
    "—"
  ).toUpperCase();

  const timeframe =
    bot?.strategy?.setup?.timeframe ||
    bot?.strategy?.timeframe ||
    bot?.timeframe ||
    "—";

  const normalizedActionLabel = String(safeDecision?.action || "").toLowerCase();

  const normalizedConfidence = String(
    safeDecision?.confidence_label ||
    safeDecision?.confidence ||
    ""
  ).toLowerCase();
  const hasLinkedStrategy = Boolean(bot?.strategy?.id || bot?.strategy_id || bot?.strategy);

  const deriveDecisionReason = (decisionState) => {
    const directReason =
      decisionState?.reason ||
      decisionState?.guardrail_reason ||
      decisionState?.guardrails_result?.reason ||
      decisionState?.guardrails?.reason ||
      decisionState?.reasons?.[0] ||
      decisionState?.guardrails_result?.warnings?.[0] ||
      decisionState?.guardrails?.warnings?.[0] ||
      decisionState?.setup_match?.summary ||
      decisionState?.setup_match?.detail ||
      decisionState?.trade_plan?.summary ||
      decisionState?.profile_habit_alignment?.primary_alignment?.summary ||
      "";

    if (directReason) return directReason;
    if (!hasLinkedStrategy) return copy.noStrategy;
    if (!bot?.is_active) return copy.blockerPausedTitle || "Bot is gepauzeerd";
    if (normalizedAction === "hold" || normalizedAction === "observe") {
      return copy.blockerWaitingBody || "De bot wacht op bevestiging vanuit setup, strategie en marktcontext.";
    }
    if (normalizedAction) {
      return copy.executionReasonFallback || "De bot heeft een beslissing, maar nog geen extra toelichting uit de engine ontvangen.";
    }
    return copy.dataUpdating;
  };

  /* ================= BOT STATE ================= */
  const normalizedAction = String(safeDecision?.action || "").toLowerCase();

  const botState = bot?.is_active
    ? normalizedAction === "hold" || normalizedAction === "observe" || !normalizedAction
      ? "waiting"
      : "live"
    : "paused";

  const lastRun =
    bot?.last_run
      ? formatDateTime(bot.last_run, locale, {
          day: "2-digit",
          month: "short",
          hour: "2-digit",
          minute: "2-digit",
        })
      : null;

  /* ================= NORMALIZE DECISION + SUMMARY ================= */
  const decisionView = useMemo(() => {
    const scores = safeDecision?.scores_json || {};
    const guardrails =
      safeDecision?.guardrails_result ||
      safeDecision?.guardrails ||
      {};
    const tradePlan = safeDecision?.trade_plan || {};

    const rawPositionSize =
      safeDecision?.position_size ??
      scores?.position_size ??
      null;

    const parsedPositionSize = Number(rawPositionSize);

    const normalizedPositionSize = rawPositionSize !== null && Number.isFinite(parsedPositionSize)
      ? Math.max(0, Math.min(parsedPositionSize, 1))
      : null;

    const normalizedDecision = {
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

      position_size: normalizedPositionSize,

      exposure_multiplier:
        safeDecision?.exposure_multiplier ??
        scores?.exposure_multiplier ??
        1,
    };

    const hasDecision = Boolean(
      normalizedActionLabel ||
      normalizedDecision?.action ||
      normalizedDecision?.decision_id ||
      normalizedDecision?.id
    );

    const decisionReason = deriveDecisionReason(normalizedDecision);

    const summaryReason = !hasLinkedStrategy
      ? copy.noStrategy
      : decisionReason || copy.dataUpdating;

    const blocker = !hasLinkedStrategy
      ? {
          tone: "amber",
          title: copy.noStrategy,
          body:
            copy.blockerNoStrategyBody ||
            "Deze bot kan nog niet handelen, omdat er nog geen strategie is gekoppeld aan het plan.",
          nextStep:
            copy.blockerNoStrategyStep ||
            "Volgende stap: koppel eerst een strategie voordat Automation een beslissing kan nemen.",
        }
      : !bot?.is_active
        ? {
            tone: "slate",
            title: copy.blockerPausedTitle || "Bot is gepauzeerd",
            body:
              copy.blockerPausedBody ||
              "De keten blijft zichtbaar, maar deze bot voert niets uit totdat je hem opnieuw activeert.",
            nextStep:
              copy.blockerPausedStep ||
              "Volgende stap: hervat de bot als dit nog steeds je goedgekeurde plan is.",
          }
        : !hasDecision || normalizedAction === "hold" || normalizedAction === "observe"
          ? {
              tone: "blue",
              title: copy.blockerWaitingTitle || "Wachten op geldige uitvoering",
              body:
                decisionReason ||
                copy.blockerWaitingBody ||
                "Er is nog geen directe tradebeslissing. De bot wacht op bevestiging vanuit setup, strategie en marktcontext.",
              nextStep:
                copy.blockerWaitingStep ||
                "Volgende stap: controleer de gekoppelde keten en wacht op betere marktcondities.",
            }
          : {
              tone: "emerald",
              title: copy.blockerReadyTitle || "Bot is klaar voor uitvoering",
              body:
                decisionReason ||
                copy.blockerReadyBody ||
                "De gekoppelde keten is compleet en de huidige beslissing kan worden uitgevoerd binnen de ingestelde limieten.",
              nextStep:
                copy.blockerReadyStep ||
                "Volgende stap: beoordeel de trade of laat de bot zijn goedgekeurde plan volgen.",
            };

    const blockerToneClasses = blocker.tone === "amber"
      ? "border-amber-200 bg-amber-50 text-amber-800"
      : blocker.tone === "emerald"
        ? "border-emerald-200 bg-emerald-50 text-emerald-800"
        : blocker.tone === "slate"
          ? "border-slate-200 bg-slate-50 text-slate-700"
          : "border-blue-200 bg-blue-50 text-blue-800";

    return {
      normalizedDecision,
      hasDecision,
      decisionReason,
      summaryReason,
      blocker,
      blockerToneClasses,
    };
  }, [bot?.is_active, copy, hasLinkedStrategy, normalizedAction, normalizedActionLabel, safeDecision]);

  const {
    normalizedDecision,
    summaryReason,
    blocker,
    blockerToneClasses,
  } = decisionView;

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
      label: copy.riskConservative,
      className: "bg-green-100 text-green-700 border-green-200",
      icon: <Shield size={12} />,
    },
    balanced: {
      label: copy.riskBalanced,
      className: "bg-yellow-100 text-yellow-700 border-yellow-200",
      icon: <Layers size={12} />,
    },
    aggressive: {
      label: copy.riskAggressive,
      className: "bg-red-100 text-red-700 border-red-200",
      icon: <Rocket size={12} />,
    },
  };

  const risk =
    riskConfig[String(bot?.risk_profile || "balanced").toLowerCase()] ||
    riskConfig.balanced;

  const scenarioLabels = {
    default: copy.scenarioDefault,
    aggressive: copy.scenarioAggressive,
    conservative: copy.scenarioConservative,
  };
  const stateLabels = copy.stateLabels || {};
  const actionLabels = copy.actionLabels || {};
  const confidenceLabels = copy.confidenceLabels || {};

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

  const executionSummary = useMemo(() => {
    const action = String(normalizedDecision?.action || "").toLowerCase();
    const amount = Number(normalizedDecision?.amount_eur ?? normalizedDecision?.requested_amount_eur ?? 0);
    const confidence = String(
      normalizedDecision?.confidence_label ||
      normalizedDecision?.confidence ||
      ""
    ).toLowerCase();
    const setupName =
      normalizedDecision?.setup_match?.name ||
      bot?.strategy?.setup?.name ||
      copy.noStrategy;
    const setupScore = Number(normalizedDecision?.setup_match?.score ?? NaN);
    const stopLoss = planSource?.stop_loss?.price ?? planSource?.stop_loss ?? null;
    const targets = Array.isArray(planSource?.targets) ? planSource.targets : [];

    return {
      actionLabel:
        actionLabels[action] ||
        action.toUpperCase() ||
        copy.insufficientData,
      confidenceLabel:
        confidenceLabels[confidence] ||
        confidence.toUpperCase() ||
        copy.insufficientData,
      amountLabel:
        amount > 0
          ? formatCurrency(amount, locale, "EUR", { maximumFractionDigits: 0 })
          : copy.insufficientData,
      setupName,
      setupScoreLabel: Number.isFinite(setupScore) ? `${Math.round(setupScore)}/100` : copy.insufficientData,
      stopLossLabel:
        stopLoss != null
          ? formatCurrency(Number(stopLoss), locale, "EUR", { maximumFractionDigits: 0 })
          : copy.notAvailable || "n.v.t.",
      targetCount: targets.length,
      hasPlanLevels: stopLoss != null || targets.length > 0,
      reason: deriveDecisionReason(normalizedDecision),
    };
  }, [
    actionLabels,
    bot?.strategy?.setup?.name,
    confidenceLabels,
    copy.dataUpdating,
    copy.insufficientData,
    copy.noStrategy,
    copy.notAvailable,
    copy.executionReasonFallback,
    locale,
    normalizedDecision,
    planSource,
  ]);

  
  /* ================= ORDER STATE ================= */
  const hasExecutableTrade = useMemo(() => {
    if (order) return true;

    const action = String(normalizedDecision?.action || "").toLowerCase();
    const amount = Number(normalizedDecision?.amount_eur ?? 0);

    return (action === "buy" || action === "sell" || action === "short") && amount > 0;
  }, [order, normalizedDecision]);

  /* ================= RENDER ================= */

  return (
    <div className={`w-full overflow-hidden border border-slate-200 bg-card flex flex-col transition-all ${compact ? "rounded-3xl shadow-sm" : "rounded-[2.5rem] shadow-xl hover:shadow-2xl"}`}>
      
      {/* 🕋 MODULAR HEADER HUD */}
      <div className={`${compact ? "p-5 pb-3 space-y-4" : "p-8 pb-4 space-y-6"}`}>
        <div className="flex items-start justify-between gap-6">
          <div className="flex items-start gap-5">
            <div className={`${compact ? "w-10 h-10 rounded-xl" : "w-14 h-14 rounded-2xl"} bg-[var(--color-border-subtle)] border border-slate-100 text-[var(--primary)] flex items-center justify-center shadow-inner transition-transform mt-1`}>
               <Bot size={compact ? 19 : 28} className="opacity-80" />
            </div>

            <div className={compact ? "space-y-1.5" : "space-y-2.5"}>
              {compact ? (
                <div>
                  <p className="text-[9px] font-black uppercase tracking-[0.2em] text-slate-400">{copy.selectedBotDetails}</p>
                  <p className="mt-1 text-sm font-black text-foreground">{bot?.strategy?.name || copy.noStrategy}</p>
                </div>
              ) : (
                <div className="flex items-center gap-3">
                  <h2 className="text-2xl font-black text-foreground tracking-tight">{bot?.name}</h2>
                  <div className={`w-2.5 h-2.5 rounded-full ${botState === 'live' ? 'bg-green-500 shadow-[0_0_12px_rgba(34,197,94,0.6)] animate-pulse' : botState === 'waiting' ? 'bg-yellow-400' : 'bg-slate-300'}`} />
                </div>
              )}
              
              {!compact ? <div className="flex items-center gap-3 text-[10px] font-black uppercase tracking-[0.15em] text-slate-400">
                <span className="text-dim bg-[var(--color-border-subtle)] px-2 py-0.5 rounded-md">{symbol}</span>
                <div className="w-1 h-1 rounded-full bg-slate-300" />
                <span>{timeframe}</span>
                {bot?.strategy && (
                  <>
                    <div className="w-1 h-1 rounded-full bg-slate-300" />
                    <span className="text-[var(--primary)] font-bold">{bot.strategy.name}</span>
                  </>
                )}
              </div> : null}

              {/* HORIZONTAL PILLS CONTAINER */}
              <div className="flex flex-wrap items-center gap-2 pt-1.5">
                <div className={`px-3 py-1.5 rounded-xl border text-[9px] font-black uppercase tracking-widest shadow-sm flex items-center gap-1.5 ${risk.className}`}>
                   {risk.icon}
                   {risk.label.replace(copy.riskPrefix, "")}
                </div>
                
                <div className="px-3 py-1.5 rounded-xl border border-slate-200 bg-[var(--color-border-subtle)] text-[9px] font-black text-muted uppercase tracking-widest shadow-sm flex items-center gap-1.5">
                   <Activity size={10} />
                   {isAuto ? copy.autoPilot : copy.manualLink}
                </div>

                <div className={`px-3 py-1.5 rounded-xl border text-[9px] font-black uppercase tracking-widest shadow-sm flex items-center gap-1.5 ${bot?.is_live ? 'bg-emerald-100 text-emerald-700 border-emerald-200' : 'bg-blue-100 text-blue-700 border-blue-200'}`}>
                   {bot?.is_live ? <Zap size={10} /> : <Clock size={10} />}
                   {bot?.is_live ? copy.liveMode : copy.paperMode}
                </div>
              </div>
            </div>
          </div>

          <div className="relative flex items-center gap-2" ref={settingsRef}>
            {onTrade ? (
              <button
                type="button"
                onClick={(event) => {
                  event.stopPropagation();
                  onTrade();
                }}
                aria-label={tradeActionLabel}
                aria-pressed={tradeActive}
                title={tradeActionLabel}
                className={`inline-flex min-h-10 items-center gap-2 rounded-xl border px-3 text-[10px] font-black uppercase tracking-[0.14em] transition ${
                  tradeActive
                    ? "border-blue-600 bg-blue-600 text-white shadow-sm hover:bg-blue-700"
                    : "border-slate-200 bg-white text-slate-600 hover:border-blue-200 hover:bg-blue-50 hover:text-blue-700 dark:border-slate-800 dark:bg-slate-950 dark:text-slate-300 dark:hover:border-blue-900 dark:hover:bg-blue-950/30 dark:hover:text-blue-300"
                }`}
              >
                <Wallet size={14} />
                <span className="hidden sm:inline">{tradeActionLabel}</span>
              </button>
            ) : null}
            {onAskFinn ? (
              <button
                type="button"
                onClick={(event) => {
                  event.stopPropagation();
                  onAskFinn();
                }}
                aria-label={finnActionLabel}
                title={finnActionLabel}
                className="inline-flex min-h-10 items-center gap-2 rounded-xl border border-blue-100 bg-blue-50 px-3 text-[10px] font-black uppercase tracking-[0.14em] text-blue-700 transition hover:border-blue-200 hover:bg-blue-100 dark:border-blue-950 dark:bg-blue-950/30 dark:text-blue-300"
              >
                <Sparkles size={14} />
                <span className="hidden sm:inline">{finnActionLabel}</span>
              </button>
            ) : null}
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

        <div className={`rounded-[1.5rem] border px-5 py-4 ${blockerToneClasses}`}>
          <div className="text-[10px] font-black uppercase tracking-[0.22em] opacity-70">
            {copy.primaryStateLabel || "Direct zichtbaar"}
          </div>
          <div className="mt-2 text-lg font-black tracking-tight">
            {blocker.title}
          </div>
          <p className="mt-2 text-sm font-semibold leading-relaxed">
            {blocker.body}
          </p>
          <p className="mt-2 text-xs font-bold opacity-80">
            {blocker.nextStep}
          </p>
        </div>

        {/* 📊 SYSTEM STATUS BAR */}
        <div className={`grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 ${compact ? "gap-2 p-1.5 rounded-2xl" : "gap-4 p-2 rounded-[1.5rem]"} bg-[var(--color-border-subtle)] border border-slate-100`}>
          <div className="bg-card rounded-xl p-4 border border-slate-100 shadow-sm">
             <div className="text-[9px] font-black text-secondary uppercase tracking-widest mb-1.5 opacity-60">{copy.statusReaction}</div>
             <div className={`text-xs font-black uppercase tracking-tight flex items-center gap-2 ${bot?.is_live ? 'text-emerald-600' : 'text-blue-600'}`}>
                <div className={`w-2 h-2 rounded-full ${botState === 'live' ? (bot?.is_live ? 'bg-emerald-500' : 'bg-green-500') : botState === 'waiting' ? 'bg-amber-400' : 'bg-slate-400'}`} />
                {stateLabels[botState] || botState}
             </div>
          </div>

          <div className="bg-card rounded-xl p-4 border border-slate-100 shadow-sm">
             <div className="text-[9px] font-black text-secondary uppercase tracking-widest mb-1.5 opacity-60">{copy.marketAction}</div>
             <div className="text-xs font-black text-[var(--primary)] uppercase tracking-tight flex items-center gap-2">
                <Rocket size={12} strokeWidth={3} />
                {actionLabels[normalizedActionLabel] || normalizedActionLabel.toUpperCase() || copy.insufficientData}
             </div>
          </div>

          <div className="bg-card rounded-xl p-4 border border-slate-100 shadow-sm">
             <div className="text-[9px] font-black text-secondary uppercase tracking-widest mb-1.5 opacity-60">{copy.summaryReasonLabel || "Waarom"}</div>
             <div className="text-xs font-black text-foreground tracking-tight">{summaryReason}</div>
          </div>

          <div className="bg-card rounded-xl p-4 border border-slate-100 shadow-sm">
             <div className="text-[9px] font-black text-secondary uppercase tracking-widest mb-1.5 opacity-60">{copy.lastChecked}</div>
             <div className="text-xs font-black text-muted tracking-tight">{lastRun || copy.dataUpdating}</div>
          </div>
         </div>

        {/* 🔽 EXPAND TOGGLE 🔽 */}
        <button
          onClick={(e) => { e.stopPropagation(); setIsExpanded(v => !v); }}
          className="w-full mt-4 py-3 border border-slate-200 dark:border-slate-800 border-dashed rounded-xl text-[10px] font-black text-slate-400 dark:text-slate-500 hover:text-slate-600 dark:hover:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-800/50 transition-colors flex items-center justify-center gap-2 uppercase tracking-[0.2em] shadow-sm active:scale-[0.99]"
        >
          {isExpanded ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
          {isExpanded ? copy.collapseDiagnostics : copy.viewFullDiagnostics}
        </button>

        {isExpanded && (
          <div className="rounded-[1.5rem] border border-slate-200 bg-slate-50/70 p-4">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <div className="text-[10px] font-black uppercase tracking-[0.18em] text-slate-500">
                  {copy.diagnosticsToolsLabel || "Diagnostiektools"}
                </div>
                <p className="mt-1 text-sm font-semibold text-slate-600">
                  {copy.diagnosticsToolsBody || "Gebruik backtests en scenario's alleen wanneer je dieper wilt controleren waarom de bot wel of niet uitvoerbaar is."}
                </p>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <button
                  onClick={() => handleBacktest()}
                  disabled={backtestLoading || scenariosLoading}
                  className="h-9 px-3 rounded-xl border border-slate-200 bg-card text-muted hover:text-[var(--primary)] hover:border-[var(--primary)] transition-all shadow-sm active:scale-95 flex items-center gap-1.5 text-[9px] font-black uppercase tracking-wider disabled:opacity-50"
                >
                  {backtestLoading ? (
                    <div className="w-2.5 h-2.5 border-2 border-slate-300 border-t-[var(--primary)] animate-spin rounded-full" />
                  ) : (
                    <RotateCcw size={11} className="opacity-70" />
                  )}
                  {backtestLoading ? copy.analyzing : copy.startBacktest}
                </button>

                <button
                  onClick={handleRunScenarios}
                  disabled={backtestLoading || scenariosLoading}
                  className="h-9 px-3 rounded-xl border border-indigo-200 bg-indigo-50 text-indigo-600 hover:bg-indigo-100 transition-all shadow-sm active:scale-95 flex items-center gap-1.5 text-[9px] font-black uppercase tracking-wider disabled:opacity-50"
                >
                  {scenariosLoading ? (
                    <div className="w-2.5 h-2.5 border-2 border-indigo-300 border-t-indigo-600 animate-spin rounded-full" />
                  ) : (
                    <Activity size={11} className="opacity-70" />
                  )}
                  {copy.scenarios}
                </button>
              </div>
            </div>
          </div>
        )}

        {/* 📊 BACKTEST RESULTS SECTION */}
        {/* ⏳ LOADING STATE */}
        {isExpanded && (backtestLoading || scenariosLoading) && (
          <div className="mt-4 p-6 bg-[var(--color-border-subtle)] border border-slate-100 rounded-2xl flex items-center justify-center gap-4 animate-pulse">
            <div className="w-5 h-5 border-2 border-slate-300 border-t-[var(--primary)] animate-spin rounded-full" />
            <div className="text-xs font-black text-secondary uppercase tracking-[0.2em]">
              {scenariosLoading ? copy.scenarioLoading : copy.backtestLoading}
            </div>
          </div>
        )}

        {/* 📊 BACKTEST RESULTS SECTION (LIGHT MODE) */}
        {isExpanded && backtestResult && !backtestLoading && (
          <div className="mt-4 space-y-4 animate-fade-in">
            <div className="bg-card rounded-[2rem] border border-slate-200 shadow-xl overflow-hidden relative group">
              <div className="absolute top-0 right-0 w-32 h-32 bg-indigo-50/50 blur-3xl rounded-full translate-x-1/2 -translate-y-1/2 opacity-50" />
              
              <div className="p-8 pb-4 flex items-center justify-between border-b border-slate-100">
                <div className="flex items-center gap-3">
                  <div className="w-8 h-8 rounded-lg bg-emerald-50 text-emerald-600 flex items-center justify-center border border-emerald-100">
                    <Activity size={16} strokeWidth={3} />
                  </div>
                  <h3 className="text-[10px] font-black text-secondary uppercase tracking-[0.2em]">{symbol} {copy.performanceScan}</h3>
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
                  <div className="text-[9px] font-black text-secondary uppercase tracking-widest mb-2">{copy.profit}</div>
                  <div className={`text-2xl font-black tracking-tighter ${backtestResult.return_pct >= 0 ? 'text-emerald-500' : 'text-red-500'}`}>
                    {backtestResult.return_pct >= 0 ? '+' : ''}
                    {formatCurrency(Math.round((backtestResult.return_pct / 100) * 10000), locale, "EUR", {
                      maximumFractionDigits: 0,
                    })}
                  </div>
                  <div className="text-[8px] font-bold text-secondary mt-1 italic">{copy.modelTenK}</div>
                </div>

                <div className="p-8 hover:bg-slate-50/50 transition-colors">
                  <div className="text-[9px] font-black text-secondary uppercase tracking-widest mb-2">{copy.roi}</div>
                  <div className={`text-2xl font-black tracking-tighter ${backtestResult.return_pct >= 0 ? 'text-emerald-500' : 'text-red-500'}`}>
                    {backtestResult.return_pct >= 0 ? '+' : ''}{backtestResult.return_pct}%
                  </div>
                </div>

                <div className="p-8 hover:bg-slate-50/50 transition-colors">
                  <div className="text-[9px] font-black text-secondary uppercase tracking-widest mb-2">{copy.winRate}</div>
                  <div className="text-2xl font-black text-foreground tracking-tighter">
                    {backtestResult.performance?.winrate}%
                  </div>
                  <div className="text-[8px] font-bold text-secondary mt-1 uppercase tracking-widest">
                    {backtestResult.performance?.wins}W / {backtestResult.performance?.losses}L
                  </div>
                </div>

                <div className="p-8 hover:bg-slate-50/50 transition-colors">
                  <div className="text-[9px] font-black text-secondary uppercase tracking-widest mb-2">{copy.totalCapital}</div>
                  <div className="text-2xl font-black text-foreground tracking-tighter">
                    {formatCurrency(Math.round(10000 + ((backtestResult.return_pct / 100) * 10000)), locale, "EUR", {
                      maximumFractionDigits: 0,
                    })}
                  </div>
                  <div className="text-[8px] font-bold text-indigo-400 mt-1 uppercase tracking-widest">{copy.tenKStart}</div>
                </div>
              </div>

              <div className="p-6 bg-slate-50/80 border-t border-slate-100 flex flex-wrap items-center justify-between gap-4">
                <div className="flex flex-col">
                  <span className="text-[8px] font-bold text-secondary uppercase tracking-widest">{copy.avgTrade}</span>
                  <span className={`text-xs font-black ${backtestResult.performance?.expectancy >= 0 ? 'text-emerald-600' : 'text-red-500'}`}>
                    {backtestResult.performance?.expectancy >= 0 ? '+' : ''}{backtestResult.performance?.expectancy}%
                  </span>
                </div>
                <div className="flex flex-col">
                  <span className="text-[8px] font-bold text-secondary uppercase tracking-widest">{copy.bestTrade}</span>
                  <span className="text-xs font-black text-emerald-600">+{backtestResult.performance?.best_trade_pct}%</span>
                </div>
                <div className="flex flex-col">
                  <span className="text-[8px] font-bold text-secondary uppercase tracking-widest">{copy.worstTrade}</span>
                  <span className="text-xs font-black text-red-400">{backtestResult.performance?.worst_trade_pct}%</span>
                </div>
                <div className="flex flex-col">
                  <span className="text-[8px] font-bold text-secondary uppercase tracking-widest">{copy.executions}</span>
                  <span className="text-xs font-black text-slate-600">
                    {backtestResult.total_trades} {copy.trades}
                  </span>
                </div>
                <div className="flex flex-col text-right">
                  <span 
                    className="text-[8px] font-bold text-secondary uppercase tracking-widest cursor-help underline decoration-slate-200 decoration-dotted"
                    title={copy.expectancyTooltip}
                   >
                     {copy.expectancy}
                   </span>
                  <span className={`text-xs font-black ${backtestResult.performance?.expectancy >= 0 ? 'text-indigo-600' : 'text-red-500'}`}>
                    {backtestResult.performance?.expectancy >= 0 ? '+' : ''}{backtestResult.performance?.expectancy}%
                  </span>
                </div>
              </div>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
              <div className="p-5 bg-card border border-slate-100 rounded-2xl shadow-sm">
                <div className="text-[10px] font-black text-secondary uppercase tracking-widest mb-3">{copy.aiSummary}</div>
                <div className="text-sm font-bold text-slate-700 leading-relaxed italic border-l-4 border-indigo-400 pl-4 py-1">
                  "{backtestResult.summary?.message || copy.noDetails}"
                </div>
              </div>

              <div className="p-5 bg-slate-50/50 border border-slate-100 rounded-2xl shadow-sm">
                <div className="text-[10px] font-black text-secondary uppercase tracking-widest mb-3">{copy.recentTrades}</div>
                <div className="space-y-2">
                  {backtestResult.trades?.length > 0 ? (
                    backtestResult.trades.map((t, i) => (
                      <div key={i} className="flex items-center justify-between bg-card px-3 py-2 rounded-xl border border-slate-100 shadow-xs">
                        <div className="flex items-center gap-3">
                           {t.type === 'buy' ? (
                             <div className="text-[10px] font-black text-indigo-500 bg-indigo-50 px-1.5 py-0.5 rounded border border-indigo-100">{copy.buy}</div>
                           ) : (
                             <div className="text-[10px] font-black text-orange-500 bg-orange-50 px-1.5 py-0.5 rounded border border-orange-100">{copy.sell}</div>
                           )}
                           <span className="text-xs font-bold text-muted tracking-tighter">
                             {formatCurrency(Number(t.price ?? 0), locale, "EUR", {
                               maximumFractionDigits: 0,
                             })}
                           </span>
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
                    <div className="text-[10px] font-bold text-secondary italic">{copy.noRecentTrades}</div>
                  )}
                </div>
              </div>
            </div>
          </div>
        )}

        {/* 🚀 SCENARIO COMPARISON TABLE (LIGHT MODE) */}
        {isExpanded && Object.keys(scenarios).length > 0 && !scenariosLoading && (
          <div className="mt-4 p-6 bg-[var(--color-border-subtle)] rounded-3xl border border-slate-200 shadow-sm animate-fade-in relative overflow-hidden">
             <div className="flex items-center justify-between mb-6">
                <div className="flex items-center gap-3">
                   <div className="w-8 h-8 rounded-lg bg-indigo-100 text-indigo-600 flex items-center justify-center border border-indigo-200">
                      <Zap size={18} strokeWidth={3} />
                   </div>
                   <h3 className="text-sm font-black text-foreground uppercase tracking-widest">{copy.scenarioComparison}</h3>
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
                           <div className="text-[10px] font-black text-secondary uppercase tracking-[0.2em]">{scenarioLabels[type] || type}</div>
                           {isBest && <span className="text-[10px]">🏆</span>}
                         </div>

                         <div className={`text-xl font-black tracking-tighter mb-1 ${res.return_pct >= 0 ? 'text-emerald-500' : 'text-red-500'}`}>
                            {res.return_pct >= 0 ? '+' : ''}{res.return_pct}%
                         </div>
                         
                         <div className="space-y-1">
                           <div className={`text-[12px] font-black ${isBest ? 'text-slate-900' : 'text-slate-600'}`}>
                             {formatCurrency(Math.round(10000 + ((res.return_pct / 100) * 10000)), locale, "EUR", {
                               maximumFractionDigits: 0,
                             })}
                           </div>
                           <div className="text-[9px] font-bold text-secondary uppercase tracking-widest">
                             {res.total_trades} {copy.trades}
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
            <div className="grid grid-cols-1 gap-5 xl:grid-cols-2">
              <div className="bg-slate-50/50 rounded-[2rem] border border-slate-100 overflow-hidden shadow-sm">
                <div className="p-6 lg:p-8">
                  <BotPortfolioCard bot={portfolio} />
                </div>
              </div>

              <div className="bg-white/60 rounded-[2rem] border border-slate-100 overflow-hidden shadow-sm">
                <div className="p-6 lg:p-8">
                  <GuardrailsPanel
                    decision={normalizedDecision}
                    bot={bot}
                  />
                </div>
              </div>
            </div>

            {/* Module 2: Execution Summary */}
            {hasLinkedStrategy ? (
              <div className="bg-card rounded-[2rem] border border-slate-200 p-6 lg:p-8 shadow-sm">
                <div className="flex flex-wrap items-start justify-between gap-4">
                  <div>
                    <div className="text-[10px] font-black uppercase tracking-[0.18em] text-slate-400">
                      {copy.executionSummaryLabel || "Execution summary"}
                    </div>
                    <h3 className="mt-2 text-xl font-black text-slate-900">
                      {bot?.strategy?.name || copy.noStrategy}
                    </h3>
                    <p className="mt-2 max-w-3xl text-sm font-semibold leading-relaxed text-slate-600">
                      {executionSummary.reason}
                    </p>
                  </div>
                  <div className="rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-[10px] font-black uppercase tracking-[0.14em] text-slate-500">
                    {loadingMarketIntelligence ? (copy.dataUpdating || "Data wordt bijgewerkt") : (copy.diagnosticsReady || "Diagnostiek")}
                  </div>
                </div>

                <div className="mt-6 grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
                  <div className="rounded-2xl border border-slate-100 bg-slate-50/80 p-4">
                    <div className="text-[9px] font-black uppercase tracking-widest text-slate-400">{copy.marketAction}</div>
                    <div className="mt-2 text-sm font-black text-slate-900">{executionSummary.actionLabel}</div>
                  </div>
                  <div className="rounded-2xl border border-slate-100 bg-slate-50/80 p-4">
                    <div className="text-[9px] font-black uppercase tracking-widest text-slate-400">{copy.logicalConfidence}</div>
                    <div className="mt-2 text-sm font-black text-slate-900">{executionSummary.confidenceLabel}</div>
                  </div>
                  <div className="rounded-2xl border border-slate-100 bg-slate-50/80 p-4">
                    <div className="text-[9px] font-black uppercase tracking-widest text-slate-400">{copy.amountLabel || "Bedrag"}</div>
                    <div className="mt-2 text-sm font-black text-slate-900">{executionSummary.amountLabel}</div>
                  </div>
                  <div className="rounded-2xl border border-slate-100 bg-slate-50/80 p-4">
                    <div className="text-[9px] font-black uppercase tracking-widest text-slate-400">{copy.setupLabel || "Setup"}</div>
                    <div className="mt-2 text-sm font-black text-slate-900">{executionSummary.setupName}</div>
                    <div className="mt-1 text-[11px] font-bold text-slate-500">{copy.setupScoreLabel || "Setup score"}: {executionSummary.setupScoreLabel}</div>
                  </div>
                </div>

                {executionSummary.hasPlanLevels ? (
                  <div className="mt-4 grid grid-cols-1 gap-4 md:grid-cols-2">
                    <div className="rounded-2xl border border-slate-100 bg-white p-4">
                      <div className="text-[9px] font-black uppercase tracking-widest text-slate-400">{copy.stopLossLabel || "Stop loss"}</div>
                      <div className="mt-2 text-sm font-black text-slate-900">{executionSummary.stopLossLabel}</div>
                    </div>
                    <div className="rounded-2xl border border-slate-100 bg-white p-4">
                      <div className="text-[9px] font-black uppercase tracking-widest text-slate-400">{copy.targetCountLabel || "Targets"}</div>
                      <div className="mt-2 text-sm font-black text-slate-900">{executionSummary.targetCount}</div>
                    </div>
                  </div>
                ) : null}
              </div>
            ) : null}
          </div>

          {/* 📜 TERMINAL LOGS / HISTORY (BOTTOM BAR) */}
          <div className="mt-auto border-t border-slate-100 bg-[var(--color-border-subtle)] text-muted overflow-hidden">
            <button
              onClick={(e) => { e.stopPropagation(); setShowHistory((v) => !v); }}
              className="w-full p-5 lg:p-6 text-xs font-black uppercase tracking-[0.2em] hover:bg-slate-100/80 hover:text-slate-800 transition-all flex items-center justify-between group"
            >
              <div className="flex items-center gap-3">
                <Clock size={14} className="group-hover:rotate-[360deg] transition-transform duration-700" />
                {showHistory ? copy.systemLogsMinimize : copy.systemLogsOpen}
              </div>
              <div className="text-[10px] opacity-40">[{combinedHistory.length} {copy.entries.toUpperCase()}]</div>
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
