"use client";

import { Shield, AlertTriangle } from "lucide-react";
import { useEffect } from "react";

export default function GuardrailsPanel({
  decision = {},
  bot = {},
  onRefresh,
}) {

  const result = decision?.guardrails_result || {};
  const guardrails = result?.guardrails || {};

  /* ============================
     LISTEN FOR BUDGET CHANGES
  ============================ */


  /* ============================
     CORE VALUES
  ============================ */

  const allowed = result?.allowed === true;

  const adjustedAmount =
    Number(result?.adjusted_amount_eur ?? 0);

  const originalAmount =
    Number(result?.original_amount_eur ?? adjustedAmount);

  const warnings =
    result?.warnings ?? [];

  const blockedBy =
    result?.blocked_by ?? null;

  const guardrailReason =
    result?.reason ||
    decision?.guardrail_reason;
  
  const strategyReason =
    decision?.reasons?.[0];
  
  const reason =
    guardrailReason ||
    strategyReason ||
    warnings?.[0] ||
    blockedBy ||
    "within risk limits";

  /* ============================
     GUARDRAIL SETTINGS
  ============================ */

  const maxRisk =
    guardrails?.max_trade_risk_eur ??
    bot?.max_risk_per_trade ??
    0;

  const currentExposure =
    Number(guardrails?.current_asset_exposure_pct ?? 0);

  const maxExposure =
    Number(guardrails?.max_asset_exposure_pct ?? 100);

  const exposureUsedPct = currentExposure;

  /* ============================
     FORMAT
  ============================ */

  const eur = (v) => {
    const n = Number(v);
    if (!Number.isFinite(n)) return "€0";

    return n.toLocaleString("nl-NL", {
      style: "currency",
      currency: "EUR",
      maximumFractionDigits: 0,
    });
  };

  const pct = (v) => {
    const n = Number(v);
    if (!Number.isFinite(n)) return "0%";
    return `${n.toFixed(0)}%`;
  };

  const tradeAdjusted =
    originalAmount !== adjustedAmount;

  /* ============================
     UI
  ============================ */

  return (
    <div className="h-full flex flex-col space-y-4">
      {/* 🛡️ SAFETY CHECK HEADER */}
      <div className="flex items-center justify-between border-b border-slate-100 pb-3">
        <div className="flex items-center gap-2 text-[10px] font-black text-secondary uppercase tracking-widest">
          <Shield size={14} className="text-slate-300" />
          Safety Check
        </div>
        <div className={`px-2 py-0.5 rounded text-[10px] font-black uppercase tracking-tighter ${allowed ? "bg-green-100 text-green-600 border border-green-200" : "bg-red-100 text-red-600 border border-red-200"}`}>
          {allowed ? "GO / CLEAR" : "SYSTEM BLOCKED"}
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3">
        {/* SENSOR 1: TRADE LIMITS */}
        <div className="bg-[var(--color-border-subtle)] border border-slate-100 rounded-xl p-3 flex flex-col justify-between">
           <div className="text-[9px] font-black text-secondary uppercase tracking-tighter mb-2">Max Risk / Trade</div>
           <div className="text-sm font-black text-foreground font-mono tracking-tighter">{eur(maxRisk)}</div>
        </div>

        {/* SENSOR 2: ASSET EXPOSURE */}
        <div className="bg-[var(--color-border-subtle)] border border-slate-100 rounded-xl p-3 flex flex-col justify-between">
           <div className="text-[9px] font-black text-secondary uppercase tracking-tighter mb-1">Exposure Ratio</div>
           <div className="text-[11px] font-black text-foreground font-mono tracking-tighter opacity-80 mb-1">
             {currentExposure}% / {maxExposure}%
           </div>
           {/* Mini Gauge Bar */}
           <div className="w-full h-1 bg-slate-200 rounded-full overflow-hidden">
             <div 
               className={`h-full transition-all ${currentExposure > maxExposure * 0.8 ? 'bg-orange-500' : 'bg-[var(--primary)]'}`}
               style={{ width: `${Math.min(100, (currentExposure / maxExposure) * 100)}%` }}
             />
           </div>
        </div>
      </div>

      <div className="bg-[var(--color-border-subtle)] border border-slate-100 rounded-xl p-3 space-y-2">
         <div className="flex justify-between items-center">
            <div className="text-[9px] font-black text-secondary uppercase tracking-tighter">Adjusted Loadout</div>
            <div className={`text-[10px] font-black px-1.5 py-0.5 rounded ${tradeAdjusted ? 'bg-orange-100 text-orange-600' : 'bg-green-100 text-green-600'}`}>
              {tradeAdjusted ? "SCALED DOWN" : "OPTIMAL SIZE"}
            </div>
         </div>
         <div className="text-sm font-black text-foreground font-mono tracking-tighter">
            {eur(adjustedAmount)}
            {tradeAdjusted && (
               <span className="text-[10px] text-secondary font-normal ml-2 italic">
                 (Req: {eur(originalAmount)})
               </span>
            )}
         </div>
      </div>

      {/* SYSTEM FEEDBACK SECTION */}
      <div className="pt-2">
        <div className="text-[9px] font-black text-secondary uppercase tracking-widest mb-1 mx-1">Interlock Reason</div>
        <div className={`p-3 rounded-xl border italic text-xs font-bold tracking-tight min-h-[44px] flex items-center ${allowed ? "bg-blue-50/50 border-blue-100/50 text-blue-600" : "bg-orange-100/50 border-orange-200/50 text-orange-600"}`}>
           {reason === "within risk limits" ? "✓ All safety parameters nominal" : reason}
        </div>
      </div>

      {/* WARNINGS STACK */}
      {warnings.length > 1 && (
        <div className="pt-2 animate-pulse">
          {warnings.slice(1).map((w, i) => (
            <div key={i} className="flex items-center gap-2 p-2 rounded-lg bg-orange-50 border border-orange-100 text-[10px] font-black text-orange-600 uppercase tracking-tight">
              <AlertTriangle size={12} />
              {w}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
