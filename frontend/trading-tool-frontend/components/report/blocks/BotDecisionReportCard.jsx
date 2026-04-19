import ReportCard from "../ReportCard";
import {
  Bot,
  ArrowUpRight,
  ArrowDownRight,
  PauseCircle,
  AlertCircle
} from "lucide-react";

/* =======================================================
   Bot Decision — REPORT (V2 PRO REFINED)
======================================================= */
export default function BotDecisionReportCard({ snapshot }) {
  // 1) Normaliseer snapshot
  let safeSnapshot = snapshot ?? {};

  if (typeof safeSnapshot === "string") {
    try {
      safeSnapshot = JSON.parse(safeSnapshot);
    } catch (e) {
      safeSnapshot = {};
    }
  }

  if (Array.isArray(safeSnapshot)) {
    safeSnapshot = safeSnapshot[0] ?? {};
  }

  // 2) Defaults
  const {
    bot_name = "Handelsbot",
    action = "hold",
    confidence = null,
    amount_eur = null,
    setup_match = null,
    reason = "Geen actie: criteria niet bereikt.",
  } = safeSnapshot || {};

  const normalizedAction =
    typeof action === "string" ? action.toLowerCase() : "hold";

  const isBuy = normalizedAction === "buy";
  const isSell = normalizedAction === "sell";
  const isHold = !isBuy && !isSell;

  return (
    <ReportCard title="Handelsactie" icon={<Bot size={16} />}>
      
      {/* BOT IDENTITY */}
      <div className="mb-6">
        <div className="text-[11px] font-bold text-secondary tracking-tight mb-1">Bot</div>
        <div className="text-xl font-bold text-foreground tracking-tight">{bot_name}</div>
      </div>

      <div className="space-y-6">
        
        {/* ACTION NODE */}
        <div className={`p-5 rounded-2xl border flex items-center justify-between transition-all duration-500 ${
          isBuy ? "bg-green-500/5 border-green-500/10 text-green-700" :
          isSell ? "bg-red-500/5 border-red-500/10 text-red-700" :
          "bg-[var(--color-border-subtle)] border-slate-100 text-slate-600"
        }`}>
            <div className="flex items-center gap-3">
               <div className={`w-10 h-10 rounded-xl flex items-center justify-center shadow-sm ${
                 isBuy ? "bg-green-600 text-white" :
                 isSell ? "bg-red-600 text-white" :
                 "bg-card border border-slate-200 text-slate-400"
               }`}>
                  {isBuy && <ArrowUpRight size={20} />}
                  {isSell && <ArrowDownRight size={20} />}
                  {isHold && <PauseCircle size={20} />}
               </div>
               <div>
                  <div className="text-[11px] font-bold tracking-tight opacity-60">Actie</div>
                  <div className="text-xl font-bold uppercase tracking-tight leading-none">
                    {normalizedAction}
                  </div>
               </div>
            </div>

            {confidence !== null && (
              <div className="flex flex-col items-end">
                 <span className="text-[10px] font-bold tracking-tight opacity-60">Vertrouwen</span>
                 <span className="text-lg font-bold font-mono tracking-tight">{confidence}%</span>
              </div>
            )}
        </div>

        {/* DETAILS */}
        <div className="grid grid-cols-2 gap-4">
           {amount_eur !== null && (
             <div className="p-4 rounded-xl border border-slate-50 bg-white/50 shadow-sm">
                <span className="text-[10px] font-bold text-secondary tracking-tight mb-2 block">Ordergrootte</span>
                <span className="text-sm font-bold text-foreground font-mono tracking-tight">€{amount_eur.toLocaleString()}</span>
             </div>
           )}

           {setup_match !== null && (
             <div className="p-4 rounded-xl border border-slate-50 bg-white/50 shadow-sm">
                <span className="text-[10px] font-bold text-secondary tracking-tight mb-2 block">Setup Match</span>
                <span className="text-sm font-bold text-foreground font-mono tracking-tight">{setup_match}%</span>
             </div>
           )}
        </div>

        {/* TOELICHTING */}
        <div className="pt-6 border-t border-slate-50">
           <div className="flex items-center gap-2 mb-3">
              <AlertCircle size={14} className="text-secondary" />
              <span className="text-[11px] font-bold text-secondary tracking-tight">Toelichting</span>
           </div>
           <div className="text-[14px] text-dim leading-relaxed italic bg-card p-4 rounded-xl border border-slate-50 shadow-inner-light">
             {reason}
           </div>
        </div>

      </div>
    </ReportCard>
  );
}
