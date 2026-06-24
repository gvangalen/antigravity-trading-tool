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

const BEHAVIOR_FLAG_LABELS = {
  fomo: "FOMO",
  overtrades: "Overtrading",
  leverage_seeking: "Leverage-neiging",
  holds_losers_too_long: "Verlies te lang laten lopen",
  takes_profit_too_early: "Winst te vroeg nemen",
};

const humanizeBehaviorLabel = (flag, fallbackLabel = "") =>
  fallbackLabel || BEHAVIOR_FLAG_LABELS[String(flag || "").trim()] || String(flag || "").replaceAll("_", " ");

const extractBehavioralFriction = (decision = {}) => {
  const direct =
    decision?.pending_behavioral_memory_friction ||
    decision?.memory_friction ||
    decision?.guardrails_result?.pending_behavioral_memory_friction ||
    decision?.guardrails_result?.memory_friction ||
    decision?.payload?.memory_friction ||
    null;
  if (direct && typeof direct === "object") return direct;
  const alignment = decision?.profile_habit_alignment?.primary_alignment || null;
  if (alignment) {
    return {
      source: "profile_habit_alignment",
      message: alignment.behavioral_cost || alignment.summary,
      safe_alternative: alignment.recommended_rule,
      label: humanizeBehaviorLabel(alignment.flag, alignment.label),
    };
  }
  return null;
};

export default function BotTodayProposal({
  bot = null,
  portfolio = null,
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

  const budgetTotal = Number(portfolio?.budget?.total_eur ?? 0);
  const positionValue = Number(portfolio?.stats?.position_value_eur ?? 0);
  const guardrails = decision?.guardrails_result || decision?.guardrails || {};
  const behavioralFriction = extractBehavioralFriction(decision);

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

  const governanceStatus = (() => {
    if (!hasTrade) return "watch";
    if (guardrails?.blocked || guardrails?.allow === false || status === "skipped") return "block";
    if (deviation > 0.2 || score < 55) return "modify";
    return "approve";
  })();

  const governanceTone =
    governanceStatus === "block"
      ? "border-rose-200 bg-rose-50 text-rose-700"
      : governanceStatus === "modify" || governanceStatus === "watch"
        ? "border-amber-200 bg-amber-50 text-amber-700"
        : "border-emerald-200 bg-emerald-50 text-emerald-700";

  const governanceHeadline =
    governanceStatus === "block"
      ? "Finn wil deze botactie nu blokkeren."
      : governanceStatus === "modify"
        ? "Finn wil deze botactie eerst bijschaven."
        : governanceStatus === "watch"
          ? "Finn ziet nog geen harde entry, alleen review-context."
          : "Finn ziet deze botactie als uitvoerbaar binnen de huidige context.";

  const setupFitText =
    score >= 75 ? "Sterke setup-fit" : score >= 55 ? "Redelijke setup-fit" : "Zwakke setup-fit";

  const portfolioMessage = (() => {
    if (budgetTotal > 0 && positionValue / budgetTotal >= 0.7) {
      return `${decision?.symbol || bot?.symbol || "Dit asset"} gebruikt al veel van dit botbudget. Voeg pas exposure toe als je bewust ruimte vrijhoudt.`;
    }
    if (deviation > 0.2) {
      return "De logic sizing ligt boven de markt sizing. Controleer eerst of je hier echt extra risico wilt stapelen.";
    }
    return "Portfolio-fit oogt werkbaar zolang je dit niet combineert met te veel andere live beslissingen op hetzelfde asset.";
  })();

  const nextStepMessage =
    governanceStatus === "block"
      ? "Open eerst de guardrails of verlaag het risico voordat je iets bevestigt."
      : governanceStatus === "modify"
        ? "Pas sizing of setup-condities aan en laat Finn daarna opnieuw meekijken."
        : governanceStatus === "watch"
          ? "Laat de bot wachten tot er een duidelijkere entry ontstaat of review de setup eerst."
          : "Je kunt nu door naar execution, zolang je plan en exposure bewust blijven.";

  /* =====================================================
     HEADER
  ===================================================== */

  /* =====================================================
     V2 PRO RENDER HELPERS
  ===================================================== */

  const systemHeader = (
    <div className="flex items-center gap-3 border-b border-[var(--color-border)] pb-4 mb-4">
      <div className="p-2 rounded-lg bg-indigo-50 dark:bg-indigo-600/10 text-indigo-600">
        <ShoppingCart size={18} />
      </div>
      <div>
        <div className="text-[10px] font-black text-muted uppercase tracking-widest">Bot Intelligence Pipeline</div>
        <div className="text-sm font-bold text-foreground tracking-tight">Daily Execution Proposal</div>
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
          className="bg-card border border-[var(--color-border)] text-foreground hover:bg-[var(--bg-soft)] px-5 py-2.5 rounded-xl font-bold text-sm flex items-center gap-2 transition-all"
        >
          <SkipForward size={16} />
          {hasTrade ? "SKIP TRADE" : "SKIP ANALYZE"}
        </button>
      )}

      {onGenerate && (
        <button
          onClick={onGenerate}
          disabled={isGenerating}
          className="ml-auto bg-slate-100/80 border border-slate-200 text-muted hover:bg-slate-200/50 px-5 py-2.5 rounded-xl font-bold text-[11px] uppercase tracking-wider flex items-center gap-2 transition-all disabled:opacity-50"
        >
          <RotateCcw size={14} />
          {isGenerating ? "RE-ANALYZING..." : "RE-SCAN MARKET"}
        </button>
      )}
    </div>
  );

  const governancePanel = (
    <div className={`mb-5 rounded-2xl border p-4 ${governanceTone}`}>
      <div className="flex items-center justify-between gap-3">
        <div>
          <div className="text-[10px] font-black uppercase tracking-[0.18em] opacity-75">
            Finn beslislaag
          </div>
          <p className="mt-2 text-sm font-black leading-snug text-slate-900">
            {governanceHeadline}
          </p>
        </div>
        <span className="rounded-full bg-white/80 px-3 py-1 text-[9px] font-black uppercase tracking-widest">
          {governanceStatus}
        </span>
      </div>
      <div className="mt-4 grid gap-2 md:grid-cols-3">
        <div className="rounded-xl border border-white/70 bg-white/75 p-3">
          <div className="text-[8px] font-black uppercase tracking-widest opacity-70">Beslischeck</div>
          <p className="mt-1 text-[11px] font-semibold leading-snug text-slate-700">{setupFitText}</p>
        </div>
        <div className="rounded-xl border border-white/70 bg-white/75 p-3">
          <div className="text-[8px] font-black uppercase tracking-widest opacity-70">Planfit</div>
          <p className="mt-1 text-[11px] font-semibold leading-snug text-slate-700">
            {score >= 60 ? "Deze actie volgt de huidige setup-logica redelijk goed." : "Deze actie vraagt eerst betere setupbevestiging."}
          </p>
        </div>
        <div className="rounded-xl border border-white/70 bg-white/75 p-3">
          <div className="text-[8px] font-black uppercase tracking-widest opacity-70">Portfoliofit</div>
          <p className="mt-1 text-[11px] font-semibold leading-snug text-slate-700">{portfolioMessage}</p>
        </div>
      </div>
      <div className="mt-3 rounded-xl border border-white/70 bg-white/75 p-3">
        <div className="text-[8px] font-black uppercase tracking-widest opacity-70">Veilige volgende stap</div>
        <p className="mt-1 text-[11px] font-semibold leading-snug text-slate-700">{nextStepMessage}</p>
      </div>
      {behavioralFriction && (
        <div className="mt-3 rounded-xl border border-amber-200 bg-white/85 p-3 text-amber-700">
          <div className="text-[8px] font-black uppercase tracking-widest">
            Gedragsrem{behavioralFriction?.label ? ` · ${behavioralFriction.label}` : ""}
          </div>
          {behavioralFriction?.message && (
            <p className="mt-1 text-[11px] font-semibold leading-snug text-slate-700">
              {behavioralFriction.message}
            </p>
          )}
          {behavioralFriction?.safe_alternative && (
            <p className="mt-2 text-[10px] font-black uppercase tracking-widest text-amber-700">
              {behavioralFriction.safe_alternative}
            </p>
          )}
        </div>
      )}
    </div>
  );

  const proposalGrid = (
    <div className="grid gap-4 lg:grid-cols-2">
      {/* STRATEGY MATCH INSTRUMENT */}
      <div className="bg-[var(--color-border-subtle)] border border-[var(--color-border)] rounded-2xl p-5 space-y-4 transition-colors">
        <div className="flex justify-between items-start">
          <div>
            <div className="text-[10px] font-black text-muted uppercase tracking-widest mb-1">Setupbasis</div>
            <div className="text-sm font-black text-foreground tracking-tight">{setupName}</div>
          </div>
          <div className="text-[10px] font-black text-blue-600 bg-blue-50 dark:bg-blue-900/40 px-2 py-1 rounded border border-blue-100 dark:border-blue-800 font-mono">
            SCORE {score}/100
          </div>
        </div>

        <ScoreBar score={score} />

        <div className="grid grid-cols-2 gap-3 pt-2">
          <div className="bg-white/80 p-2 rounded-lg border border-slate-200/50">
             <div className="text-[9px] font-black text-secondary uppercase tracking-tighter mb-0.5">Discipline</div>
             <div className="text-[11px] font-black text-slate-700 uppercase">{confidence}</div>
          </div>
          <div className="bg-white/80 p-2 rounded-lg border border-slate-200/50">
             <div className="text-[9px] font-black text-secondary uppercase tracking-tighter mb-0.5">Tijdstip</div>
             <div className="text-[11px] font-black text-muted font-mono">{formattedDecisionTime?.split(',')[1] || "KLAAR"}</div>
          </div>
        </div>

        <div className="p-3 rounded-xl bg-card/50 border border-[var(--color-border)] italic text-[11px] text-muted leading-relaxed font-medium">
          "{summary}"
        </div>
      </div>

      {/* POSITION SIZING INSTRUMENT */}
      <div className="bg-[var(--color-border-subtle)] border border-slate-100 rounded-2xl p-5 space-y-4 flex flex-col justify-between">
        <div>
           <div className="text-[10px] font-black text-secondary uppercase tracking-widest mb-1">Blootstelling</div>
           <div className="text-sm font-black text-foreground tracking-tight">{executionLabel}</div>
        </div>

        <div className="space-y-2.5">
           <div className="flex justify-between items-center bg-white/60 p-2 rounded-lg border border-slate-200/40">
              <span className="text-[10px] font-black text-secondary uppercase tracking-tighter">Marktweging</span>
              <span className="text-xs font-black text-slate-700 font-mono">{safeMarketMultiplier.toFixed(2)}x</span>
           </div>
           <div className="flex justify-between items-center bg-white/60 p-2 rounded-lg border border-slate-200/40">
              <span className="text-[10px] font-black text-secondary uppercase tracking-tighter">Setupweging</span>
              <span className="text-xs font-black text-[var(--primary)] font-mono">{safeStrategyMultiplier.toFixed(2)}x</span>
           </div>
           <div className="flex justify-between items-center bg-white/60 p-2 rounded-lg border border-slate-200/40">
              <span className="text-[10px] font-black text-secondary uppercase tracking-tighter">Afwijking</span>
              <span className={`text-[10px] font-black uppercase ${deviationColor}`}>{deviationLabel} ({deviation >= 0 ? "+" : ""}{deviation.toFixed(2)})</span>
           </div>
        </div>

        {allocationPreview && (
          <div className="bg-[var(--primary)] p-3 rounded-xl shadow-sm flex items-center justify-between">
             <div className="text-[9px] font-black text-white/70 uppercase tracking-widest">Netto inzet</div>
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
        <div className="rounded-[1.5rem] border border-[var(--color-border)] bg-card p-6 shadow-sm transition-colors duration-300">
           {governancePanel}
           <div className="flex items-center gap-2 text-muted mb-6">
              <div className="w-1.5 h-1.5 rounded-full bg-muted/30" />
              <div className="text-xs font-black uppercase tracking-widest">Geen actieve instapcondities gevonden</div>
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
      <div className="rounded-[1.5rem] border border-blue-600/20 dark:border-blue-600/40 bg-card p-6 shadow-sm ring-1 ring-blue-600/10 dark:ring-blue-600/20 transition-colors duration-300">
         {governancePanel}
         <div className="flex items-center justify-between mb-6">
            <div className="flex items-center gap-3">
               <div className="w-2 h-2 rounded-full bg-green-500 animate-pulse shadow-[0_0_8px_rgba(16,185,129,0.4)]" />
               <div className="text-2xl font-black text-foreground tracking-tighter uppercase">
                  {(order?.side ?? decision.action ?? "buy")} {order?.symbol ?? decision.symbol ?? "—"}
               </div>
            </div>
            <div className="px-3 py-1 rounded-lg bg-green-50 border border-green-100 text-green-600 text-[10px] font-black uppercase tracking-widest">
               Uitvoering nodig
            </div>
         </div>
         {proposalGrid}
         {tacticalCommandBar}
      </div>
    </div>
  );
}
