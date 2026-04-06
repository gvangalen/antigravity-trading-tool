"use client";

import { useEffect, useMemo, useRef, useState } from "react";

import BotDecisionCard from "@/components/bot/BotDecisionCard";
import BotPortfolioCard from "@/components/bot/BotPortfolioCard";
import BotHistoryTable from "@/components/bot/BotHistoryTable";
import BotSettingsMenu from "@/components/bot/BotSettingsMenu";
import TradePlanCard from "@/components/bot/TradePlanCard";
import MarketDecisionCard from "@/components/bot/MarketDecisionCard";
import GuardrailsPanel from "@/components/bot/GuardrailsPanel";

import {
  Bot,
  MoreVertical,
  Clock,
  Shield,
  Layers,
  Rocket,
  Activity,
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
}) {
  if (!bot) return null;

  const [showHistory, setShowHistory] = useState(false);
  const [showSettings, setShowSettings] = useState(false);
  const settingsRef = useRef(null);

  const [savingPlan, setSavingPlan] = useState(false);
  const [saveError, setSaveError] = useState(null);

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

  /* ================= REFRESH ON BUDGET UPDATE ================= */
  useEffect(() => {
    const handleBudgetUpdate = () => {
      console.log("🔄 Budget updated → refreshing bot decision");
      onGenerate?.(bot);
    };

    window.addEventListener("bot:budget-updated", handleBudgetUpdate);

    return () => {
      window.removeEventListener("bot:budget-updated", handleBudgetUpdate);
    };
  }, [bot, onGenerate]);

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
    <div className="w-full rounded-[2.5rem] border border-slate-200 bg-white shadow-xl overflow-hidden flex flex-col transition-all hover:shadow-2xl">
      
      {/* 🕋 MODULAR HEADER HUD */}
      <div className="p-8 pb-4 space-y-6">
        <div className="flex items-start justify-between gap-6">
          <div className="flex items-center gap-5">
            <div className="w-14 h-14 rounded-2xl bg-slate-50 border border-slate-100 text-[var(--primary)] flex items-center justify-center shadow-inner group-hover:scale-105 transition-transform">
               <Bot size={28} className="opacity-80" />
            </div>

            <div className="space-y-1">
              <div className="flex items-center gap-3">
                <h2 className="text-2xl font-black text-slate-800 tracking-tight">{bot?.name}</h2>
                <div className={`w-2.5 h-2.5 rounded-full ${botState === 'live' ? 'bg-green-500 shadow-[0_0_12px_rgba(34,197,94,0.6)] animate-pulse' : botState === 'waiting' ? 'bg-yellow-400' : 'bg-slate-300'}`} />
              </div>
              
              <div className="flex items-center gap-3 text-[10px] font-black uppercase tracking-[0.15em] text-slate-400">
                <span className="text-slate-600 bg-slate-100 px-2 py-0.5 rounded-md">{symbol}</span>
                <div className="w-1 h-1 rounded-full bg-slate-300" />
                <span>{timeframe}</span>
                {bot?.strategy && (
                  <>
                    <div className="w-1 h-1 rounded-full bg-slate-300" />
                    <span className="text-[var(--primary)] font-bold">{bot.strategy.name}</span>
                  </>
                )}
              </div>
            </div>
          </div>

          <div className="flex items-center gap-4">
            {/* TACTICAL BADGES */}
            <div className="hidden sm:flex items-center gap-3">
              <div className={`px-4 py-2 rounded-xl border text-[10px] font-black uppercase tracking-widest shadow-sm flex items-center gap-2 ${risk.className}`}>
                 {risk.icon}
                 {risk.label.replace('Risk: ', '')}
              </div>
              
              <div className="px-4 py-2 rounded-xl border border-slate-200 bg-slate-50 text-[10px] font-black text-slate-500 uppercase tracking-widest shadow-sm flex items-center gap-2">
                 <Activity size={12} />
                 {isAuto ? "AUTO-PILOT" : "MANUAL-LINK"}
              </div>
            </div>

            <div className="relative" ref={settingsRef}>
              <button
                className="w-10 h-10 flex items-center justify-center rounded-xl border border-slate-200 bg-white text-slate-400 hover:text-slate-800 hover:border-slate-400 transition-all shadow-sm active:scale-95"
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
        </div>

        {/* 📊 SYSTEM STATUS BAR (UPGRADED PADDING) */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 p-2 bg-slate-50 border border-slate-100 rounded-[1.5rem]">
          <div className="bg-white rounded-xl p-4 border border-slate-100 shadow-sm">
             <div className="text-[9px] font-black text-slate-400 uppercase tracking-widest mb-1.5 opacity-60">Status Response</div>
             <div className="text-xs font-black text-slate-800 uppercase tracking-tight flex items-center gap-2">
                <div className={`w-2 h-2 rounded-full ${botState === 'live' ? 'bg-green-500' : 'bg-slate-400'}`} />
                {botState} session
             </div>
          </div>

          <div className="bg-white rounded-xl p-4 border border-slate-100 shadow-sm">
             <div className="text-[9px] font-black text-slate-400 uppercase tracking-widest mb-1.5 opacity-60">Market Action</div>
             <div className="text-xs font-black text-[var(--primary)] uppercase tracking-tight flex items-center gap-2">
                <Rocket size={12} strokeWidth={3} />
                {statusLabel}
             </div>
          </div>

          <div className="bg-white rounded-xl p-4 border border-slate-100 shadow-sm">
             <div className="text-[9px] font-black text-slate-400 uppercase tracking-widest mb-1.5 opacity-60">Logic Confidence</div>
             <div className="text-xs font-black text-slate-800 uppercase tracking-tight flex items-center gap-2">
                <Layers size={12} strokeWidth={3} />
                {confidence}
             </div>
          </div>

          <div className="bg-white rounded-xl p-4 border border-slate-100 shadow-sm">
             <div className="text-[9px] font-black text-slate-400 uppercase tracking-widest mb-1.5 opacity-60">Telemetry Sync</div>
             <div className="text-xs font-black text-slate-500 tracking-tight font-mono">{lastRun || "SYNCING..."}</div>
          </div>
        </div>
      </div>

      {/* 🚀 MAIN COCKPIT MODULES */}
      <div className="p-8 pt-4 space-y-10">
        
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
        <div className="bg-white rounded-[2rem] border border-slate-200 p-6 lg:p-8 shadow-sm">
          {loadingMarketIntelligence ? (
            <div className="flex items-center gap-3 text-xs font-black text-slate-400 uppercase tracking-widest p-10 justify-center">
              <div className="w-4 h-4 rounded-full border-2 border-slate-200 border-t-[var(--primary)] animate-spin" />
              Syncing Brain...
            </div>
          ) : (
            <MarketDecisionCard data={marketIntelligence} />
          )}
        </div>

        {/* Module 3: Execution Engine & Price Ladder */}
        <div className="bg-white rounded-[2rem] border border-slate-200 overflow-hidden shadow-md">
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
      <div className="mt-auto border-t border-slate-100 bg-slate-50 text-slate-500 overflow-hidden">
        <button
          onClick={() => setShowHistory((v) => !v)}
          className="w-full p-5 lg:p-6 text-xs font-black uppercase tracking-[0.2em] hover:bg-slate-100/80 hover:text-slate-800 transition-all flex items-center justify-between group"
        >
          <div className="flex items-center gap-3">
            <Clock size={14} className="group-hover:rotate-[360deg] transition-transform duration-700" />
            {showHistory ? "SYSTEM_LOGS_MINIMIZE" : "SYSTEM_LOGS_OPEN"}
          </div>
          <div className="text-[10px] opacity-40">[{combinedHistory.length} ENTRIES]</div>
        </button>

        {showHistory && (
          <div className="p-8 pt-0 border-t border-slate-200/50 animate-fade-in">
            <BotHistoryTable history={combinedHistory} />
          </div>
        )}
      </div>
    </div>
  );
}
