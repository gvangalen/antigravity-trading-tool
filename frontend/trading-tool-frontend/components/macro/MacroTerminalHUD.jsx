"use client";

import { Activity, Globe, ShieldAlert, Target, Zap } from "lucide-react";
import React from "react";

/**
 * 🛰️ MacroTerminalHUD — PRO V2
 * Visualizes the aggregate macro data from useScoresData().
 */
export default function MacroTerminalHUD({ score, bias, trend, risk }) {
  
  const scoreNum = Number(score ?? 0);
  
  /* ---------------- COLORS & LABELS ---------------- */
  const getBiasConfig = (s) => {
    if (s >= 80) return { label: "EXTREME BULLISH", color: "text-green-500", bg: "bg-green-500", dot: "bg-green-500", border: "border-green-200" };
    if (s >= 60) return { label: "BULLISH", color: "text-blue-500", bg: "bg-blue-500", dot: "bg-blue-500", border: "border-blue-200" };
    if (s >= 40) return { label: "NEUTRAL", color: "text-slate-400", bg: "bg-slate-400", dot: "bg-slate-400", border: "border-slate-200" };
    if (s >= 20) return { label: "BEARISH", color: "text-red-400", bg: "bg-red-400", dot: "bg-red-400", border: "border-red-200" };
    return { label: "EXTREME BEARISH", color: "text-red-600", bg: "bg-red-600", dot: "bg-red-600", border: "border-red-300" };
  };

  const config = getBiasConfig(scoreNum);

  return (
    <div className="w-full grid grid-cols-1 md:grid-cols-3 gap-6">
      
      {/* 🔮 MODULE 1: GLOBAL MACRO TERMINAL */}
      <div className="md:col-span-2 bg-white rounded-[2rem] border border-slate-200 p-8 shadow-sm flex flex-col justify-between relative overflow-hidden group">
         {/* DECORATIVE GRID */}
         <div className="absolute inset-0 opacity-[0.03] pointer-events-none bg-[radial-gradient(#000_1px,transparent_1px)] [background-size:20px_20px]" />
         
         <div className="flex items-center justify-between mb-8 relative z-10">
            <div className="flex items-center gap-3">
               <div className="w-10 h-10 rounded-xl bg-slate-50 border border-slate-100 flex items-center justify-center text-slate-400">
                  <Globe size={20} />
               </div>
               <div>
                  <div className="text-[10px] font-black text-slate-400 uppercase tracking-widest">Aggregated Macro Sentiment</div>
                  <div className="text-xl font-black text-slate-800 tracking-tight uppercase">Global Macro Terminal</div>
               </div>
            </div>
            
            <div className={`px-4 py-1.5 rounded-lg border ${config.border} ${config.color} bg-slate-50 text-[10px] font-black uppercase tracking-widest shadow-sm`}>
               System Status: {config.label}
            </div>
         </div>

         <div className="space-y-6 relative z-10">
            <div className="flex items-end justify-between">
               <div className="text-6xl font-black text-slate-900 tracking-tighter leading-none">
                  {score !== null && score !== undefined ? score : "—"}
                  <span className="text-2xl text-slate-300 ml-1 font-normal">/100</span>
               </div>
               <div className="text-right">
                  <div className="text-[10px] font-bold text-slate-400 uppercase tracking-widest mb-1 italic">Macro Bias</div>
                  <div className={`text-2xl font-black ${config.color} tracking-tighter uppercase`}>{bias || "STABLE"}</div>
               </div>
            </div>

            {/* THE BIAS BAR (V2 PRO STYLE) */}
            <div className="h-6 w-full bg-slate-100 rounded-lg p-1 border border-slate-200 overflow-hidden">
               <div 
                  className={`h-full rounded-md transition-all duration-1000 ease-out shadow-[0_0_15px_-5px] ${config.bg}`}
                  style={{ width: `${scoreNum > 0 ? scoreNum : 0.1}%` }}
               />
            </div>
         </div>
      </div>

      {/* 📡 MODULE 2: MACRO REGIME NODE */}
      <div className="h-full">
         <div className="bg-white rounded-[2rem] border border-slate-200 p-8 flex flex-col justify-between h-full shadow-sm relative overflow-hidden group">
            {/* SUBTLE DECORATIVE GLOW */}
            <div className="absolute top-0 right-0 w-32 h-32 bg-blue-500/5 blur-3xl rounded-full -mr-16 -mt-16 group-hover:scale-150 transition-transform duration-1000" />
            
            <div className="flex items-center gap-3 mb-6 relative z-10">
               <div className="w-8 h-8 rounded-lg bg-slate-50 border border-slate-100 flex items-center justify-center">
                  <Activity size={16} className="text-blue-500" />
               </div>
               <div className="text-[9px] font-black uppercase tracking-[0.2em] text-slate-400">Macro_Structural_Regime</div>
            </div>

            <div className="relative z-10">
               <div className="text-xs font-black text-blue-500 uppercase mb-1">Market Direction</div>
               <div className="text-4xl font-black tracking-tighter uppercase leading-none mb-3 text-slate-800">
                  {trend || "RANGING"}
               </div>
               <p className="text-[10px] text-slate-500 leading-relaxed max-w-[220px] font-medium uppercase tracking-wider">
                  SYSTEM_LOGIC: {trend || "STABLE"} GLOBAL MACRO DIRECTION DETECTED VIA MULTI-INDICATOR SYNC.
               </p>
            </div>

            <div className="mt-8 relative z-10">
               <div className="flex items-center gap-2">
                  <div className="w-1.5 h-1.5 rounded-full bg-blue-500 animate-pulse" />
                  <span className="text-[8px] font-black tracking-widest text-slate-300 uppercase">Telemetry_Live</span>
               </div>
            </div>
         </div>
      </div>
    </div>
  );
}
