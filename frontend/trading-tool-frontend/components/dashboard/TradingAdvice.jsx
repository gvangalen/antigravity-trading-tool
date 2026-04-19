'use client';

import { useEffect, useState } from 'react';
import { Rocket, Target, ShieldAlert, Zap } from 'lucide-react';

export default function TradingAdvice() {
  const [advice, setAdvice] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadDummyAdvice();
  }, []);

  function loadDummyAdvice() {
    setLoading(true);

    // 🔵 Mock AI advice
    setAdvice({
      setup: 'BTC Swing Buy',
      trend: 'Bullish',
      entry: 97000,
      targets: [
        { type: 'TP1', price: 104000 },
        { type: 'TP2', price: 112000 }
      ],
      stop_loss: '$94,500',
      risk: 'Medium',
      reason: 'Mock advice: this is a temporary placeholder for system validation.',
    });

    setLoading(false);
  }

  const getTrendClasses = () => {
    if (advice?.trend === 'Bullish') return 'border-emerald-100 dark:border-emerald-900/30 bg-emerald-50 dark:bg-emerald-950/20 text-emerald-800 dark:text-emerald-400';
    if (advice?.trend === 'Bearish') return 'border-rose-100 dark:border-rose-900/30 bg-rose-50 dark:bg-rose-950/20 text-rose-800 dark:text-rose-400';
    return 'border-slate-100 dark:border-slate-800 bg-[var(--color-border-subtle)] dark:bg-slate-900 text-foreground dark:text-slate-300';
  };

  return (
    <div className={`rounded-2xl border-2 p-6 shadow-sm transition-all overflow-hidden relative ${getTrendClasses()}`}>
      <div className="absolute top-0 right-0 p-4 opacity-5">
         <Zap size={64} />
      </div>

      <div className="flex items-center gap-2 mb-6">
         <Rocket size={18} className="text-blue-600" />
         <h3 className="text-sm font-black uppercase tracking-widest">Active Trading Advice (Bitcoin)</h3>
      </div>

      {loading ? (
        <div className="text-xs font-bold uppercase tracking-widest animate-pulse flex items-center gap-2">
           <div className="w-1.5 h-1.5 rounded-full bg-blue-600" />
           Loading intelligence...
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-y-4 gap-x-8">
          <div className="space-y-1">
             <p className="text-[10px] font-black uppercase tracking-widest opacity-60">Setup</p>
             <p className="text-sm font-black">{advice?.setup}</p>
          </div>
          
          <div className="space-y-1">
             <p className="text-[10px] font-black uppercase tracking-widest opacity-60">Trend</p>
             <p className="text-sm font-black">{advice?.trend}</p>
          </div>

          <div className="space-y-1">
             <p className="text-[10px] font-black uppercase tracking-widest opacity-60 flex items-center gap-1">
                <Target size={10} className="text-emerald-500" /> Entry
             </p>
             <p className="text-sm font-mono font-black text-blue-600 dark:text-blue-400">
                ${Number(advice?.entry).toLocaleString()}
             </p>
          </div>

          <div className="space-y-1">
             <p className="text-[10px] font-black uppercase tracking-widest opacity-60">Targets</p>
             <p className="text-sm font-mono font-black text-emerald-600 dark:text-emerald-400">
               {Array.isArray(advice?.targets)
                 ? advice.targets.map(t => `${t.type}: $${t.price.toLocaleString()}`).join(' / ')
                 : '-'}
             </p>
          </div>

          <div className="space-y-1">
             <p className="text-[10px] font-black uppercase tracking-widest opacity-60 flex items-center gap-1">
                <ShieldAlert size={10} className="text-rose-500" /> Stop Loss
             </p>
             <p className="text-sm font-mono font-black text-rose-600 dark:text-rose-400">
                {advice?.stop_loss}
             </p>
          </div>

          <div className="space-y-1">
             <p className="text-[10px] font-black uppercase tracking-widest opacity-60">Risk Profile</p>
             <p className="text-sm font-black uppercase">{advice?.risk}</p>
          </div>

          {advice?.reason && (
            <div className="col-span-1 md:col-span-2 mt-4 pt-4 border-t border-current opacity-20">
               <p className="text-[11px] font-medium leading-relaxed italic">
                 "{advice.reason}"
               </p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
