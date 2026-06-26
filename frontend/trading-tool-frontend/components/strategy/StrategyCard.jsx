import { useState } from "react";
import { useModal } from "@/components/modal/ModalProvider";
import { assistantChat } from "@/lib/api/ai";
import {
  analyzeStrategy,
  deleteStrategy,
  toggleFavoriteStrategy,
} from "@/lib/api/strategy";
import { useMarketData } from "@/hooks/useMarketData";
import { 
  ArrowRight, 
  ChevronRight, 
  Target, 
  ShieldAlert, 
  Activity, 
  TrendingUp, 
  TrendingDown,
  Bot as BotIcon,
  Search,
  Star,
  StarOff,
  Trash,
  Clock,
  Euro,
  Tags,
  Brain,
  Wand2
} from "lucide-react";

export default function StrategyCard({ strategy, onRefresh, onEdit, bots = [] }) {
  if (!strategy || typeof strategy !== "object") return null;

  const { openConfirm, showSnackbar } = useModal();
  const { btcLive } = useMarketData(strategy.symbol, { mode: "live" });

  const [loading, setLoading] = useState(false);
  const [justUpdated, setJustUpdated] = useState(false);
  const [finnLoading, setFinnLoading] = useState(false);
  const [finnReview, setFinnReview] = useState(null);
  const [finnAdherence, setFinnAdherence] = useState(null);
  const [finnOpen, setFinnOpen] = useState(false);

  /* ==========================================================
     DATA & LINEAGE
  ========================================================== */
  const {
    id,
    name,
    symbol,
    timeframe,
    strategy_type,
    entry,
    stop_loss,
    base_amount,
    ai_explanation,
    favorite,
    is_active,
  } = strategy;

  const linkedBot = bots.find(b => b.strategy_id === id);
  const isBotActive = linkedBot?.is_active;

  const strategyName = name || strategy.setup_name || "Strategie";
  const isDCA = strategy_type === "dca";

  const targets = Array.isArray(strategy.targets)
    ? strategy.targets.map(t => (typeof t === 'object' ? t.price : t))
    : [];

  const currentPrice = btcLive; // In a multi-asset system, we'd filter by symbol
  const distToEntry = currentPrice && entry ? ((currentPrice - entry) / entry) * 100 : null;

  /* ==========================================================
     RISK / REWARD CALCULATIONS
  ========================================================== */
  const calculateRR = () => {
    if (!entry || !stop_loss || targets.length === 0) return null;
    const risk = Math.abs(entry - stop_loss);
    const reward = Math.abs(targets[0] - entry);
    const riskPct = (risk / entry) * 100;
    const rewardPct = (reward / entry) * 100;
    const rr = reward / risk;
    return { riskPct, rewardPct, rr };
  };

  const rrStats = calculateRR();

  /* ==========================================================
     HANDLERS
  ========================================================== */
  async function handleAnalyze() {
    try {
      setLoading(true);
      await analyzeStrategy(id);
      showSnackbar("AI-uitleg bijgewerkt", "success");
      onRefresh?.();
    } catch (err) {
      showSnackbar("AI analyse mislukt", "danger");
    } finally {
      setLoading(false);
    }
  }

  async function handleFinnReview() {
    try {
      setFinnLoading(true);
      setFinnOpen(true);
      const context = {
        page: "/strategy",
        page_type: "Strategies",
        symbol,
        strategy_id: id,
        setup_id: strategy.setup_id || null,
      };
      const [review, adherence] = await Promise.all([
        assistantChat(`Beoordeel deze strategie voor ${symbol}.`, context, []),
        assistantChat(`Past dit nog bij mijn plan voor strategie ${id}?`, context, []),
      ]);
      setFinnReview(review?.analysis || review?.state?.analysis || null);
      setFinnAdherence(adherence?.analysis || adherence?.state?.analysis || null);
    } catch (err) {
      console.error("FINN strategy review failed:", err);
      showSnackbar("Finn-check mislukt", "danger");
    } finally {
      setFinnLoading(false);
    }
  }

  async function toggleFav() {
    try {
      await toggleFavoriteStrategy(id);
      onRefresh?.();
    } catch (err) {
      showSnackbar("Favoriet aanpassen mislukt", "danger");
    }
  }

  function openDel() {
    openConfirm({
      title: "Strategie verwijderen",
      statusLabel: "Gevoelige actie",
      context: <p>{strategyName} · {symbol} · {timeframe}</p>,
      impact: <p>Deze strategie verdwijnt uit je review-lane en gekoppelde workflows verliezen hun strategiecontext.</p>,
      safety: <p>Verwijderen is definitief. Controleer eerst of je bot of setup deze strategie nog gebruikt.</p>,
      consequence: <p>Na verwijderen verversen we de lijst en kun je Finn vragen om een nieuw concept of een veiliger alternatief.</p>,
      icon: <Trash />,
      tone: "danger",
      confirmText: "Verwijder strategie",
      onConfirm: async () => {
        await deleteStrategy(id);
        onRefresh?.();
        showSnackbar("Strategie verwijderd. Finn kan je helpen een nieuw concept op te zetten.", "success");
      },
    });
  }

  /* ==========================================================
     UI HELPERS
  ========================================================== */
  const formatCurrency = (v) => {
    if (v === null || v === undefined || isNaN(v)) return "---";
    return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(v);
  };

  return (
    <div className="bg-card border border-slate-200 rounded-2xl shadow-sm hover:shadow-md transition-all overflow-hidden">
      {/* ⛓️ LINEAGE HEADER */}
      <div className="bg-slate-50/80 px-5 py-3 border-b border-slate-100 flex items-center justify-between">
        <div className="flex items-center gap-2 text-[10px] font-black uppercase tracking-widest text-slate-400">
          <span className="text-muted hover:text-slate-700 cursor-default transition-colors">{strategy.setup_name || "Setup"}</span>
          <ChevronRight size={12} className="opacity-30" />
          <span className="text-[var(--primary)]">{strategyName}</span>
          <ChevronRight size={12} className="opacity-30" />
          <div className="flex items-center gap-1.5 ml-1">
             <div className={`w-2 h-2 rounded-full ${isBotActive ? "bg-green-500 shadow-[0_0_8px_rgba(34,197,94,0.4)] animate-pulse" : "bg-slate-300"}`} />
             <span className={`font-black ${isBotActive ? "text-green-600" : "text-secondary"}`}>
                {linkedBot ? (isBotActive ? "Bot actief" : "Bot gepauzeerd") : "Geen bot"}
             </span>
          </div>

          <div className="h-3 w-[1px] bg-slate-200 mx-1" />

          <div className={`px-2 py-0.5 rounded text-[8px] font-black uppercase tracking-tighter ${is_active ? "bg-blue-100 text-blue-600" : "bg-[var(--color-border-subtle)] text-slate-400"}`}>
             Status: {is_active ? "Live" : "Stand-by"}
          </div>
        </div>

        <button onClick={toggleFav} className="p-1 text-slate-300 hover:text-yellow-500 transition-all hover:scale-110">
          {favorite ? <Star size={16} className="fill-yellow-500 text-yellow-500" /> : <StarOff size={16} />}
        </button>
      </div>

      <div className="p-5 grid grid-cols-1 lg:grid-cols-12 gap-6">
        
        {/* LEFT: EXECUTION INFO */}
        <div className="lg:col-span-8 space-y-6 flex flex-col justify-between">
          <div className="flex items-start justify-between">
            <div>
              <h3 className="text-lg font-black uppercase tracking-tight text-slate-800">{strategyName}</h3>
              <div className="flex items-center gap-2 mt-1">
                <span className="bg-[var(--color-border-subtle)] text-muted px-2 py-0.5 rounded text-[10px] font-bold uppercase">{symbol}</span>
                <span className="bg-[var(--color-border-subtle)] text-muted px-2 py-0.5 rounded text-[10px] font-bold uppercase">{timeframe}</span>
                <span className="bg-[var(--primary-soft)] text-[var(--primary-dark)] px-2 py-0.5 rounded text-[10px] font-bold uppercase">{strategy_type}</span>
              </div>
            </div>

            <div className="text-right flex flex-col justify-center">
              <div className="text-[10px] font-black text-secondary uppercase tracking-widest leading-none mb-1">Koers</div>
              <div className="text-2xl font-black text-foreground tracking-tighter leading-none">
                {currentPrice ? formatCurrency(currentPrice) : <span className="text-slate-300 animate-pulse text-sm">Laden...</span>}
              </div>
              {distToEntry !== null && !isNaN(distToEntry) && (
                <div className={`text-[11px] font-bold mt-1.5 ${distToEntry >= 0 ? "text-green-500" : "text-red-500"}`}>
                  {distToEntry >= 0 ? "+" : ""}{distToEntry.toFixed(2)}% <span className="opacity-50 font-medium tracking-tight">vanaf instap</span>
                </div>
              )}
            </div>
          </div>

          {!isDCA && (
            <div className="grid grid-cols-3 gap-4 items-stretch">
              <div className="bg-[var(--color-border-subtle)] p-4 rounded-2xl border border-slate-100 flex flex-col justify-center">
                <div className="text-[10px] font-black text-secondary uppercase tracking-widest mb-1.5 flex items-center gap-1.5">
                  <ArrowRight size={12} className="text-blue-500" /> Instap
                </div>
                <div className="text-lg font-black text-foreground tracking-tight">{formatCurrency(entry)}</div>
              </div>
              <div className="bg-[var(--color-border-subtle)] p-4 rounded-2xl border border-slate-100 flex flex-col justify-center">
                <div className="text-[10px] font-black text-secondary uppercase tracking-widest mb-1.5 flex items-center gap-1.5">
                  <Target size={12} className="text-green-500" /> Doelen
                </div>
                <div className="text-lg font-black text-foreground tracking-tight">{targets.length > 0 ? formatCurrency(targets[0]) : "-"}</div>
              </div>
              <div className="bg-red-50/50 p-4 rounded-2xl border border-red-100 flex flex-col justify-center">
                <div className="text-[10px] font-black text-red-400 uppercase tracking-widest mb-1.5 flex items-center gap-1.5">
                  <ShieldAlert size={12} className="text-red-500" /> Stop-loss
                </div>
                <div className="text-lg font-black text-red-600 tracking-tight">{formatCurrency(stop_loss)}</div>
              </div>
            </div>
          )}

          {rrStats && (
            <div className="bg-slate-800 rounded-2xl p-4 text-white">
               <div className="flex justify-between items-end mb-4">
                  <div>
                     <div className="text-[9px] font-black text-secondary uppercase tracking-widest">Risico / Rendement</div>
                     <div className="text-xl font-black tracking-tighter">1 : {rrStats.rr.toFixed(2)}</div>
                  </div>
                  <div className="text-right">
                     <span className="text-[9px] font-black bg-red-500/20 text-red-400 px-2 py-1 rounded-lg mr-2">RISICO {rrStats.riskPct.toFixed(1)}%</span>
                     <span className="text-[9px] font-black bg-green-500/20 text-green-400 px-2 py-1 rounded-lg">RENDEMENT {rrStats.rewardPct.toFixed(1)}%</span>
                  </div>
               </div>
               
               {/* RR Bar visualization */}
               <div className="h-2 w-full bg-slate-700 rounded-full overflow-hidden flex">
                  <div style={{ width: `${(1 / (1 + rrStats.rr)) * 100}%` }} className="h-full bg-red-500" />
                  <div style={{ width: `${(rrStats.rr / (1 + rrStats.rr)) * 100}%` }} className="h-full bg-green-500" />
               </div>
            </div>
          )}

          {ai_explanation && (
            <div className="bg-purple-50/50 p-4 rounded-2xl border border-purple-100 italic">
               <div className="flex items-center gap-2 text-purple-600 mb-2">
                  <Brain size={16} />
                  <span className="text-[10px] font-black uppercase tracking-widest">Toelichting</span>
               </div>
               <p className="text-xs text-dim leading-relaxed truncate-3-lines">{ai_explanation}</p>
            </div>
          )}

          {(finnOpen || finnReview || finnAdherence) && (
            <div className="bg-slate-50/70 p-4 rounded-2xl border border-slate-200 space-y-3">
              <div className="flex items-center justify-between gap-3">
                <div className="flex items-center gap-2 text-slate-600">
                  <Brain size={15} className="text-violet-500" />
                  <span className="text-[10px] font-black uppercase tracking-widest">Finn-check</span>
                </div>
                {finnLoading && (
                  <span className="text-[9px] font-black uppercase tracking-widest text-slate-400">Laden…</span>
                )}
              </div>

              {finnReview && (
                <div className={`rounded-xl border p-3 ${
                  finnReview.decision_status === "block"
                    ? "border-rose-200 bg-rose-50 text-rose-700"
                    : finnReview.decision_status === "modify" || finnReview.decision_status === "insufficient_context"
                      ? "border-amber-200 bg-amber-50 text-amber-700"
                      : "border-emerald-200 bg-emerald-50 text-emerald-700"
                }`}>
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-[9px] font-black uppercase tracking-widest">Beslischeck</span>
                    <span className="text-[8px] font-black uppercase tracking-widest">{finnReview.decision_status}</span>
                  </div>
                  <p className="mt-2 text-xs font-semibold leading-relaxed">{finnReview.risk_summary}</p>
                  {finnReview.portfolio_impact?.message && (
                    <p className="mt-2 text-[11px] font-semibold leading-relaxed opacity-80">{finnReview.portfolio_impact.message}</p>
                  )}
                </div>
              )}

              {finnAdherence && (
                <div className={`rounded-xl border p-3 ${
                  finnAdherence.adherence_status === "in_plan"
                    ? "border-blue-200 bg-blue-50 text-blue-700"
                    : finnAdherence.adherence_status === "insufficiently_justified"
                      ? "border-amber-200 bg-amber-50 text-amber-700"
                      : "border-rose-200 bg-rose-50 text-rose-700"
                }`}>
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-[9px] font-black uppercase tracking-widest">Plantrouw</span>
                    <span className="text-[8px] font-black uppercase tracking-widest">{finnAdherence.adherence_status}</span>
                  </div>
                  <p className="mt-2 text-xs font-semibold leading-relaxed">{finnAdherence.adherence_reason}</p>
                  {finnAdherence.suggested_recovery_step && (
                    <p className="mt-2 text-[11px] font-semibold leading-relaxed opacity-80">{finnAdherence.suggested_recovery_step}</p>
                  )}
                </div>
              )}
            </div>
          )}
        </div>

        {/* RIGHT: PRICE LADDER */}
        {!isDCA && (
          <div className="lg:col-span-4 bg-slate-50/50 rounded-2xl border border-slate-100 p-4">
             <div className="text-[10px] font-black text-secondary uppercase tracking-widest mb-4 flex items-center gap-2">
                <Activity size={12} /> Uitvoering
             </div>
             
             <div className="space-y-3">
                {/* UPWARDS */}
                {targets.slice(0, 2).reverse().map((t, i) => (
                  <div key={i} className="flex items-center justify-between px-3 py-2 bg-green-50 border border-green-100 rounded-lg opacity-60">
                    <span className="text-[9px] font-black text-green-500">TP{targets.length - i}</span>
                    <span className="text-xs font-black text-green-700">{formatCurrency(t)}</span>
                  </div>
                ))}

                {/* CURRENT PRICE INDICATOR (Dynamic insertion) */}
                <div className="relative py-2">
                   <div className="absolute inset-x-0 top-1/2 -translate-y-1/2 h-[1px] bg-slate-300 border-dashed border-t" />
                   <div className="relative z-10 flex justify-center">
                      <div className="bg-card border border-slate-300 px-3 py-1 rounded-full shadow-sm flex items-center gap-2">
                         <div className="w-1.5 h-1.5 bg-[var(--primary)] rounded-full animate-ping" />
                         <span className="text-[10px] font-black text-[var(--primary)]">LIVE {formatCurrency(currentPrice)}</span>
                      </div>
                   </div>
                </div>

                <div className="flex items-center justify-between px-3 py-2 bg-blue-50 border border-blue-100 rounded-lg">
                   <span className="text-[9px] font-black text-blue-500 uppercase">Instap</span>
                   <span className="text-xs font-black text-blue-700">{formatCurrency(entry)}</span>
                </div>

                <div className="flex items-center justify-between px-3 py-2 bg-red-50 border border-red-100 rounded-lg">
                   <span className="text-[9px] font-black text-red-500 uppercase">Stop</span>
                   <span className="text-xs font-black text-red-700">{formatCurrency(stop_loss)}</span>
                </div>
             </div>
          </div>
        )}
      </div>

      {/* FOOTER ACTIONS */}
      <div className="px-5 py-3 border-t border-slate-100 bg-slate-50/30 flex justify-between items-center">
         <div className="flex items-center gap-3">
            <button onClick={handleAnalyze} disabled={loading} className="flex items-center gap-1.5 text-[10px] font-black uppercase tracking-widest text-secondary hover:text-purple-600 transition-colors disabled:opacity-50">
               <Wand2 size={12} />
               {loading ? "Analyseren..." : "Nieuwe analyse"}
            </button>
            <button onClick={handleFinnReview} disabled={finnLoading} className="flex items-center gap-1.5 text-[10px] font-black uppercase tracking-widest text-secondary hover:text-blue-600 transition-colors disabled:opacity-50">
               <Brain size={12} />
               {finnLoading ? "Finn-check…" : "Check met Finn"}
            </button>
         </div>
         
         <div className="flex items-center gap-3">
            <button onClick={openDel} className="p-2 text-slate-300 hover:text-red-500 transition-colors">
               <Trash size={14} />
            </button>
            <button onClick={() => onEdit?.(strategy)} className="bg-slate-800 text-white px-4 py-2 rounded-xl text-[10px] font-black uppercase tracking-widest hover:bg-black transition-all">
               Beheer
            </button>
         </div>
      </div>
    </div>
  );
}
