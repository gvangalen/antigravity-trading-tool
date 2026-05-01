"use client";

import { useEffect, useState } from "react";
import { 
  X, 
  Info, 
  AlertCircle, 
  RefreshCw,
  ArrowRight,
  ShieldCheck
} from "lucide-react";

const fmt = (v, digits = 2) => {
  const n = Number(v);
  if (!Number.isFinite(n)) return "—";
  return n.toLocaleString("nl-NL", {
    minimumFractionDigits: 0,
    maximumFractionDigits: digits,
  });
};

export default function OrderPreviewModal({
  preview,
  onConfirm,
  onCancel,
  onRefresh,
  loading = false
}) {
  const [seconds, setSeconds] = useState(10);

  useEffect(() => {
    if (loading) {
      setSeconds(10);
      return;
    }

    const timer = setInterval(() => {
      setSeconds((prev) => {
        if (prev <= 1) {
          onRefresh?.();
          return 10;
        }
        return prev - 1;
      });
    }, 1000);

    return () => clearInterval(timer);
  }, [onRefresh, loading]);

  if (!preview) return null;

  const isBuy = preview.side === "buy";

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center p-4 bg-slate-900/60 backdrop-blur-sm animate-in fade-in duration-200">
      <div className="bg-white w-full max-w-md rounded-[2.5rem] shadow-2xl overflow-hidden border border-slate-100 flex flex-col animate-in zoom-in-95 duration-200">
        
        {/* HEADER */}
        <div className="p-8 border-b border-slate-50 flex items-center justify-between">
          <div>
            <div className="text-[10px] font-black text-secondary uppercase tracking-widest mb-1">Bevestiging</div>
            <h3 className="text-2xl font-black text-foreground tracking-tighter uppercase leading-none">Order Preview</h3>
          </div>
          <button 
            onClick={onCancel}
            className="w-10 h-10 rounded-full bg-slate-50 flex items-center justify-center text-slate-400 hover:bg-slate-100 transition-colors"
          >
            <X size={20} />
          </button>
        </div>

        {/* BODY */}
        <div className="p-8 space-y-6">
          
          {/* PAIR SUMMARY */}
          <div className="flex items-center justify-between bg-slate-50 p-6 rounded-3xl">
             <div className="flex items-center gap-3">
                <div className={`w-12 h-12 rounded-2xl flex items-center justify-center shadow-sm ${isBuy ? 'bg-blue-600 text-white' : 'bg-rose-600 text-white'}`}>
                   {isBuy ? <RefreshCw className="animate-spin-slow" size={24}/> : <ArrowRight size={24}/>}
                </div>
                <div>
                   <div className={`text-xs font-black uppercase ${isBuy ? 'text-blue-600' : 'text-rose-600'}`}>
                      {isBuy ? 'Markt Koop' : 'Markt Verkoop'}
                   </div>
                   <div className="text-lg font-black text-slate-900 tracking-tighter">
                      {preview.symbol} / EUR
                   </div>
                </div>
             </div>
             <div className="text-right">
                <div className="text-[10px] font-bold text-slate-400 uppercase tracking-widest">Actuele Koers</div>
                <div className="text-lg font-black text-slate-900 tracking-tighter">
                   € {fmt(preview.price)}
                </div>
             </div>
          </div>

          {/* DETAILS LIST */}
          <div className="space-y-3">
             <div className="flex justify-between items-center px-2">
                <span className="text-xs font-bold text-slate-400 uppercase">Order Bedrag</span>
                <span className="text-sm font-black text-slate-900">€ {fmt(preview.gross_eur)}</span>
             </div>
             
             <div className="flex justify-between items-center px-2">
                <span className="text-xs font-bold text-slate-400 uppercase flex items-center gap-1.5">
                   Geschatte Fee 
                   <span className="px-1.5 py-0.5 bg-slate-100 text-[9px] rounded-md text-slate-500">{(preview.fee_rate * 100).toFixed(2)}%</span>
                </span>
                <span className="text-sm font-black text-rose-600">- € {fmt(preview.fee_eur)}</span>
             </div>

             <div className="h-px bg-slate-100 my-2" />

             <div className="flex justify-between items-center px-2 bg-blue-50/50 p-4 rounded-2xl border border-blue-100/50">
                <span className="text-xs font-black text-blue-600 uppercase">Je ontvangt</span>
                <div className="text-right">
                   <div className="text-lg font-black text-blue-600 tracking-tighter">
                      {fmt(preview.quantity, 8)} <span className="text-xs opacity-60">BTC</span>
                   </div>
                   {isBuy && (
                      <div className="text-[10px] font-bold text-blue-400 uppercase tracking-tighter">
                         € {fmt(preview.net_eur)} netto waarde
                      </div>
                   )}
                </div>
             </div>
          </div>

          {/* REFRESH TIMER */}
          <div className="flex items-center justify-center gap-3 py-2">
             <div className="relative w-8 h-8 flex items-center justify-center">
                <svg className="w-full h-full transform -rotate-90">
                   <circle
                     cx="16"
                     cy="16"
                     r="14"
                     stroke="currentColor"
                     strokeWidth="3"
                     fill="transparent"
                     className="text-slate-100"
                   />
                   <circle
                     cx="16"
                     cy="16"
                     r="14"
                     stroke="currentColor"
                     strokeWidth="3"
                     fill="transparent"
                     strokeDasharray={88}
                     strokeDashoffset={88 - (88 * seconds) / 10}
                     className="text-blue-600 transition-all duration-1000"
                   />
                </svg>
                <span className="absolute text-[10px] font-black text-slate-900">{seconds}</span>
             </div>
             <span className="text-[10px] font-black text-slate-400 uppercase tracking-widest">Prijs wordt ververst...</span>
          </div>

        </div>

        {/* FOOTER */}
        <div className="p-8 bg-slate-50 mt-auto flex flex-col gap-4">
           {preview.is_live && (
             <div className="flex items-center gap-2 text-blue-600 bg-blue-100/50 p-3 rounded-xl border border-blue-200/50">
                <ShieldCheck size={16} />
                <span className="text-[10px] font-black uppercase tracking-widest leading-none">Live Exchange Execution</span>
             </div>
           )}

           <div className="flex gap-4">
              <button
                onClick={onCancel}
                className="flex-1 py-4 rounded-2xl font-black text-slate-500 uppercase text-xs hover:bg-slate-100 transition-colors border border-slate-200"
              >
                Annuleer
              </button>
              <button
                onClick={onConfirm}
                disabled={loading}
                className={`flex-[2] py-4 rounded-2xl font-black text-white uppercase text-xs shadow-lg shadow-blue-200/50 transition-transform active:scale-95 ${loading ? 'bg-slate-300' : 'bg-blue-600 hover:bg-blue-700'}`}
              >
                {loading ? 'Plaatsen...' : 'Bevestig Order'}
              </button>
           </div>
        </div>

      </div>
    </div>
  );
}
