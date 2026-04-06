"use client";

import CardLoader from "@/components/ui/CardLoader";
import ScoreBar from "@/components/ui/ScoreBar";

import {
  Play,
  SkipForward,
  RotateCcw,
  ShoppingCart,
  Layers,
  TrendingUp,
} from "lucide-react";

export default function BotTodayProposal({
  decision = null,
  order = null,
  loading = false,
  isGenerating = false,
  onGenerate,
  onExecute,
  onSkip,
  isAuto = false,
}) {

  /* =====================================================
     LOADING / EMPTY
  ===================================================== */

  if (loading) {
    return (
      <div className="py-6">
        <CardLoader text="Bot analyseert markt…" />
      </div>
    );
  }

  if (!decision) return null;

  const botId = decision.bot_id;
  const decisionId = decision.decision_id;

  const status = decision.status ?? "planned";
  const isFinal = status === "executed" || status === "skipped";

  const confidence = decision.confidence ?? "low";

  /* =====================================================
     EXPOSURE FRAMEWORK
  ===================================================== */

  const strategyMultiplier = Number(decision.exposure_multiplier ?? 1);
  const safeStrategyMultiplier = Number.isFinite(strategyMultiplier) ? strategyMultiplier : 1;
  
  const safeMarketMultiplier = Number(
    decision?.metrics?.position_size ?? 1
  );

  // ✅ FIX
  const deviation = safeStrategyMultiplier - safeMarketMultiplier;
    const deviationLabel =
      deviation > 0 ? "Higher risk"
      : deviation < 0 ? "Safer than market"
      : "Aligned";

  const deviationColor =
    deviation > 0 ? "text-red-600"
    : deviation < 0 ? "text-emerald-600"
    : "text-[var(--text-muted)]";

  /* =====================================================
     EXECUTION CONTEXT (🔥 FIXED)
  ===================================================== */

  const executionMode = decision.execution_mode || "fixed";
  const curveName = decision.decision_curve_name || null;

  // 🔥 FIX: juiste fallback chain
  const baseAmount = Number(
    decision.base_amount ??
    decision.requested_amount_eur ??
    decision.amount_eur ??
    0
  );

  const executionLabel =
    executionMode === "custom"
      ? "Curve sizing actief"
      : "Vast bedrag";

  const allocationPreview =
    baseAmount > 0
      ? `€${Math.round(baseAmount * safeStrategyMultiplier)}`
      : null;

  /* =====================================================
     TIMESTAMP
  ===================================================== */

  const decisionTime =
    decision.updated_at ||
    decision.decision_ts ||
    decision.created_at ||
    null;

  const formattedDecisionTime = decisionTime
    ? new Date(decisionTime).toLocaleString("nl-NL", {
        day: "2-digit",
        month: "short",
        hour: "2-digit",
        minute: "2-digit",
      })
    : null;

  /* =====================================================
     SETUP MATCH (🔥 FIXED)
  ===================================================== */

  const setupMatch = decision.setup_match || null;

  // 🔥 FIX: correcte score fallback
  const score = (() => {
    if (typeof setupMatch?.score === "number") {
      return Math.min(setupMatch.score, 100);
    }
    if (typeof decision?.scores?.total === "number") {
      return Math.min(decision.scores.total, 100);
    }
    return 10;
  })();

  const setupName = setupMatch?.name ?? "Geen strategy match";
  const setupSymbol = setupMatch?.symbol ?? "—";
  const setupTf = setupMatch?.timeframe ?? "—";

  const summary =
    setupMatch?.summary ??
    "De bot ziet momenteel geen setup die aan de voorwaarden voldoet.";

  const detail =
    setupMatch?.detail ??
    "De bot wacht op betere marktomstandigheden.";

  /* =====================================================
     TRADE DETECTIE (🔥 BELANGRIJK FIX)
  ===================================================== */

  const hasTrade =
    !!order ||
    (
      decision.action !== "hold" &&
      Number(decision.amount_eur ?? 0) > 0
    );

  const canExecute =
    !isAuto &&
    !isFinal &&
    hasTrade &&
    !!onExecute &&
    !!decisionId;

  /* =====================================================
     HEADER
  ===================================================== */

  /* =====================================================
     V2 PRO RENDER HELPERS
  ===================================================== */

  const systemHeader = (
    <div className="flex items-center gap-3 border-b border-slate-100 pb-4 mb-4">
      <div className="p-2 rounded-lg bg-indigo-50 text-indigo-600">
        <ShoppingCart size={18} />
      </div>
      <div>
        <div className="text-[10px] font-black text-slate-400 uppercase tracking-widest">Bot Intelligence Pipeline</div>
        <div className="text-sm font-bold text-slate-800 tracking-tight">Daily Execution Proposal</div>
      </div>
    </div>
  );

  const tacticalCommandBar = (
    <div className="flex flex-wrap gap-3 pt-6 border-t border-slate-100 mt-6">
      {canExecute && (
        <button
          onClick={() =>
            onExecute({
              bot_id: botId,
              decision_id: decisionId,
            })
          }
          className="bg-[var(--primary)] hover:bg-[var(--primary-dark)] text-white px-5 py-2.5 rounded-xl font-bold text-sm flex items-center gap-2 shadow-sm transition-all hover:scale-[1.02] active:scale-[0.98]"
        >
          <Play size={16} fill="currentColor" />
          EXECUTE PROPOSAL
        </button>
      )}

      {!isAuto && !isFinal && onSkip && (
        <button
          onClick={() => onSkip({ bot_id: botId })}
          className="bg-white border border-slate-200 text-slate-600 hover:bg-slate-50 px-5 py-2.5 rounded-xl font-bold text-sm flex items-center gap-2 transition-all"
        >
          <SkipForward size={16} />
          {hasTrade ? "SKIP TRADE" : "SKIP ANALYZE"}
        </button>
      )}

      {onGenerate && (
        <button
          onClick={onGenerate}
          disabled={isGenerating}
          className="ml-auto bg-slate-100/80 border border-slate-200 text-slate-500 hover:bg-slate-200/50 px-5 py-2.5 rounded-xl font-bold text-[11px] uppercase tracking-wider flex items-center gap-2 transition-all disabled:opacity-50"
        >
          <RotateCcw size={14} />
          {isGenerating ? "RE-ANALYZING..." : "RE-SCAN MARKET"}
        </button>
      )}
    </div>
  );

  const proposalGrid = (
    <div className="grid gap-4 lg:grid-cols-2">
      {/* STRATEGY MATCH INSTRUMENT */}
      <div className="bg-slate-50 border border-slate-100 rounded-2xl p-5 space-y-4">
        <div className="flex justify-between items-start">
          <div>
            <div className="text-[10px] font-black text-slate-400 uppercase tracking-widest mb-1">Logic Payload</div>
            <div className="text-sm font-black text-slate-800 tracking-tight">{setupName}</div>
          </div>
          <div className="text-[10px] font-black text-[var(--primary)] bg-blue-50 px-2 py-1 rounded border border-blue-100 font-mono">
            SCORE {score}/100
          </div>
        </div>

        <ScoreBar score={score} />

        <div className="grid grid-cols-2 gap-3 pt-2">
          <div className="bg-white/80 p-2 rounded-lg border border-slate-200/50">
             <div className="text-[9px] font-black text-slate-400 uppercase tracking-tighter mb-0.5">Discipline</div>
             <div className="text-[11px] font-black text-slate-700 uppercase">{confidence}</div>
          </div>
          <div className="bg-white/80 p-2 rounded-lg border border-slate-200/50">
             <div className="text-[9px] font-black text-slate-400 uppercase tracking-tighter mb-0.5">Telemetry</div>
             <div className="text-[11px] font-black text-slate-500 font-mono">{formattedDecisionTime?.split(',')[1] || "READY"}</div>
          </div>
        </div>

        <div className="p-3 rounded-xl bg-white/50 border border-slate-200/50 italic text-[11px] text-slate-500 leading-relaxed font-medium">
          "{summary}"
        </div>
      </div>

      {/* POSITION SIZING INSTRUMENT */}
      <div className="bg-slate-50 border border-slate-100 rounded-2xl p-5 space-y-4 flex flex-col justify-between">
        <div>
           <div className="text-[10px] font-black text-slate-400 uppercase tracking-widest mb-1">Exposure Module</div>
           <div className="text-sm font-black text-slate-800 tracking-tight">{executionLabel}</div>
        </div>

        <div className="space-y-2.5">
           <div className="flex justify-between items-center bg-white/60 p-2 rounded-lg border border-slate-200/40">
              <span className="text-[10px] font-black text-slate-400 uppercase tracking-tighter">Market Sizing</span>
              <span className="text-xs font-black text-slate-700 font-mono">{safeMarketMultiplier.toFixed(2)}x</span>
           </div>
           <div className="flex justify-between items-center bg-white/60 p-2 rounded-lg border border-slate-200/40">
              <span className="text-[10px] font-black text-slate-400 uppercase tracking-tighter">Logic Sizing</span>
              <span className="text-xs font-black text-[var(--primary)] font-mono">{safeStrategyMultiplier.toFixed(2)}x</span>
           </div>
           <div className="flex justify-between items-center bg-white/60 p-2 rounded-lg border border-slate-200/40">
              <span className="text-[10px] font-black text-slate-400 uppercase tracking-tighter">Variance Status</span>
              <span className={`text-[10px] font-black uppercase ${deviationColor}`}>{deviationLabel} ({deviation >= 0 ? "+" : ""}{deviation.toFixed(2)})</span>
           </div>
        </div>

        {allocationPreview && (
          <div className="bg-[var(--primary)] p-3 rounded-xl shadow-sm flex items-center justify-between">
             <div className="text-[9px] font-black text-white/70 uppercase tracking-widest">Net Cash Outlay</div>
             <div className="text-sm font-black text-white font-mono">{allocationPreview}</div>
          </div>
        )}
      </div>
    </div>
  );

  /* =====================================================
     MAIN LAYOUTS
  ===================================================== */

  if (!hasTrade) {
    return (
      <div className="py-4">
        {systemHeader}
        <div className="rounded-[1.5rem] border border-slate-100 bg-white p-6 shadow-sm">
           <div className="flex items-center gap-2 text-slate-400 mb-6">
              <div className="w-1.5 h-1.5 rounded-full bg-slate-300" />
              <div className="text-xs font-black uppercase tracking-widest">No Active Entry Conditions Found</div>
           </div>
           {proposalGrid}
           {tacticalCommandBar}
        </div>
      </div>
    );
  }

  return (
    <div className="py-4">
      {systemHeader}
      <div className="rounded-[1.5rem] border border-[var(--primary-soft)] bg-white p-6 shadow-sm ring-1 ring-[var(--primary-soft)]">
         <div className="flex items-center justify-between mb-6">
            <div className="flex items-center gap-3">
               <div className="w-2 h-2 rounded-full bg-green-500 animate-pulse shadow-[0_0_8px_var(--primary-soft)]" />
               <div className="text-2xl font-black text-slate-800 tracking-tighter uppercase">
                  {(order?.side ?? decision.action ?? "buy")} {order?.symbol ?? decision.symbol ?? "—"}
               </div>
            </div>
            <div className="px-3 py-1 rounded-lg bg-green-50 border border-green-100 text-green-600 text-[10px] font-black uppercase tracking-widest">
               Execution Required
            </div>
         </div>
         {proposalGrid}
         {tacticalCommandBar}
      </div>
    </div>
  );
}
