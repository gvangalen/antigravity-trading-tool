import { useState } from "react";
import { useModal } from "@/components/modal/ModalProvider";
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
  const { btcLive } = useMarketData();

  const [loading, setLoading] = useState(false);
  const [justUpdated, setJustUpdated] = useState(false);

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
      description: "Weet je zeker dat je deze strategie wilt verwijderen?",
      icon: <Trash />,
      tone: "danger",
      onConfirm: async () => {
        await deleteStrategy(id);
        onRefresh?.();
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
    <div className="bg-white border border-slate-200 rounded-2xl shadow-sm hover:shadow-md transition-all overflow-hidden">
      {/* ⛓️ LINEAGE HEADER */}
      <div className="bg-slate-50/80 px-5 py-3 border-b border-slate-100 flex items-center justify-between">
        <div className="flex items-center gap-2 text-[10px] font-black uppercase tracking-widest text-slate-400">
          <span className="text-slate-500 hover:text-slate-700 cursor-default transition-colors">{strategy.setup_name || "Setup"}</span>
          <ChevronRight size={12} className="opacity-30" />
          <span className="text-[var(--primary)]">{strategyName}</span>
          <ChevronRight size={12} className="opacity-30" />
          <div className="flex items-center gap-1.5 ml-1">
             <div className={`w-2 h-2 rounded-full ${isBotActive ? "bg-green-500 shadow-[0_0_8px_rgba(34,197,94,0.4)] animate-pulse" : "bg-slate-300"}`} />
             <span className={`font-black ${isBotActive ? "text-green-600" : "text-slate-400"}`}>
                {linkedBot ? (isBotActive ? "Bot Actief" : "Bot Gepauzeerd") : "Geen Bot"}
             </span>
          </div>

          <div className="h-3 w-[1px] bg-slate-200 mx-1" />

          <div className={`px-2 py-0.5 rounded text-[8px] font-black uppercase tracking-tighter ${is_active ? "bg-blue-100 text-blue-600" : "bg-slate-100 text-slate-400"}`}>
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
                <span className="bg-slate-100 text-slate-500 px-2 py-0.5 rounded text-[10px] font-bold uppercase">{symbol}</span>
                <span className="bg-slate-100 text-slate-500 px-2 py-0.5 rounded text-[10px] font-bold uppercase">{timeframe}</span>
                <span className="bg-[var(--primary-soft)] text-[var(--primary-dark)] px-2 py-0.5 rounded text-[10px] font-bold uppercase">{strategy_type}</span>
              </div>
            </div>

            <div className="text-right flex flex-col justify-center">
              <div className="text-[10px] font-black text-slate-400 uppercase tracking-widest leading-none mb-1">Koers</div>
              <div className="text-2xl font-black text-slate-800 tracking-tighter leading-none">
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
              <div className="bg-slate-50 p-4 rounded-2xl border border-slate-100 flex flex-col justify-center">
                <div className="text-[10px] font-black text-slate-400 uppercase tracking-widest mb-1.5 flex items-center gap-1.5">
                  <ArrowRight size={12} className="text-blue-500" /> Instap
                </div>
                <div className="text-lg font-black text-slate-800 tracking-tight">{formatCurrency(entry)}</div>
              </div>
              <div className="bg-slate-50 p-4 rounded-2xl border border-slate-100 flex flex-col justify-center">
                <div className="text-[10px] font-black text-slate-400 uppercase tracking-widest mb-1.5 flex items-center gap-1.5">
                  <Target size={12} className="text-green-500" /> Doelen
                </div>
                <div className="text-lg font-black text-slate-800 tracking-tight">{targets.length > 0 ? formatCurrency(targets[0]) : "-"}</div>
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
                     <div className="text-[9px] font-black text-slate-400 uppercase tracking-widest">Risico / Rendement</div>
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
               <p className="text-xs text-slate-600 leading-relaxed truncate-3-lines">{ai_explanation}</p>
            </div>
          )}
        </div>

        {/* RIGHT: PRICE LADDER */}
        {!isDCA && (
          <div className="lg:col-span-4 bg-slate-50/50 rounded-2xl border border-slate-100 p-4">
             <div className="text-[10px] font-black text-slate-400 uppercase tracking-widest mb-4 flex items-center gap-2">
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
                      <div className="bg-white border border-slate-300 px-3 py-1 rounded-full shadow-sm flex items-center gap-2">
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
         <button onClick={handleAnalyze} disabled={loading} className="flex items-center gap-1.5 text-[10px] font-black uppercase tracking-widest text-slate-400 hover:text-purple-600 transition-colors disabled:opacity-50">
            <Wand2 size={12} />
            {loading ? "Analyseren..." : "Nieuwe Analyse"}
         </button>
         
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

