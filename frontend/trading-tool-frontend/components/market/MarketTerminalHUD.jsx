"use client";

import { Activity, Bitcoin, TrendingUp, TrendingDown, Clock, BarChart3, Gauge } from "lucide-react";
import React from "react";
import { formatNumber } from "@/components/market/utils";

/**
 * 🛰️ MarketTerminalHUD — PRO V2
 * Visualizes live price action (BTC) and market sentiment (Score & Bias).
 */
export default function MarketTerminalHUD({ score, bias, btc = {} }) {
  
  const scoreNum = Number(score ?? 0);
  const priceChange = btc?.change_24h || 0;
  const positive = priceChange >= 0;
  const ChangeIcon = positive ? TrendingUp : TrendingDown;
  
  const getBiasConfig = (s) => {
    if (s >= 80) return { label: "EXTREME BULLISH", color: "text-green-500", bg: "bg-green-500", border: "border-green-200" };
    if (s >= 60) return { label: "BULLISH", color: "text-blue-500", bg: "bg-blue-500", border: "border-blue-200" };
    if (s >= 40) return { label: "NEUTRAL", color: "text-slate-400", bg: "bg-slate-400", border: "border-slate-200" };
    if (s >= 20) return { label: "BEARISH", color: "text-red-400", bg: "bg-red-400", border: "border-red-200" };
    return { label: "EXTREME BEARISH", color: "text-red-600", bg: "bg-red-600", border: "border-red-300" };
  };

  const config = getBiasConfig(scoreNum);

  return (
    <div className="w-full grid grid-cols-1 lg:grid-cols-3 gap-6">
      
      {/* 🔮 MODULE 1: GLOBAL MARKET SENTIMENT */}
      <div className="lg:col-span-2 bg-white rounded-[2rem] border border-slate-200 p-8 shadow-sm flex flex-col justify-between relative overflow-hidden group">
         <div className="absolute inset-0 opacity-[0.03] pointer-events-none bg-[radial-gradient(#000_1px,transparent_1px)] [background-size:20px_20px]" />
         
         <div className="flex items-center justify-between mb-8 relative z-10">
            <div className="flex items-center gap-3">
               <div className="w-10 h-10 rounded-xl bg-slate-50 border border-slate-100 flex items-center justify-center text-slate-400">
                  <Gauge size={20} />
               </div>
               <div>
                  <div className="text-[10px] font-black text-slate-400 uppercase tracking-widest">Aggregate Market Sentiment</div>
                  <div className="text-xl font-black text-slate-800 tracking-tight uppercase leading-none mt-1">Market Sentiment Terminal</div>
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
                  <div className="text-[10px] font-bold text-slate-400 uppercase tracking-widest mb-1 italic leading-none">Sentiment_Bias</div>
                  <div className={`text-2xl font-black ${config.color} tracking-tighter uppercase leading-none`}>{bias || "NEUTRAL"}</div>
               </div>
            </div>

            <div className="h-6 w-full bg-slate-100 rounded-lg p-1 border border-slate-200 overflow-hidden">
               <div 
                  className={`h-full rounded-md transition-all duration-1000 ease-out shadow-[0_0_15px_-5px] ${config.bg}`}
                  style={{ width: `${scoreNum > 0 ? scoreNum : 0.1}%` }}
               />
            </div>
         </div>
      </div>

      {/* 📡 MODULE 2: LIVE BTC PRICE NODE */}
      <div className="bg-white rounded-[2rem] border border-slate-200 p-8 flex flex-col justify-between shadow-sm relative overflow-hidden group h-full">
         <div className="absolute top-0 right-0 w-32 h-32 bg-orange-500/5 blur-3xl rounded-full -mr-16 -mt-16 group-hover:scale-150 transition-transform duration-1000" />
         
         <div className="flex items-center justify-between mb-6 relative z-10">
            <div className="flex items-center gap-3">
               <div className="w-8 h-8 rounded-lg bg-slate-50 border border-slate-100 flex items-center justify-center">
                  <Bitcoin size={16} className="text-orange-500" />
               </div>
               <div className="text-[9px] font-black uppercase tracking-[0.2em] text-slate-400 leading-none">Live_Price_Node</div>
            </div>
            <div className="flex items-center gap-1.5 text-[9px] font-bold text-slate-300">
               <Clock size={10} />
               <span className="uppercase tracking-widest leading-none">
                 {btc?.timestamp ? new Date(btc.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : "SYNC"}
               </span>
            </div>
         </div>

         <div className="relative z-10 space-y-1">
            <div className="text-[10px] font-black text-slate-400 uppercase tracking-widest">BTC / USD</div>
            <div className="text-4xl font-black tracking-tighter uppercase leading-none text-slate-900 font-mono">
               ${btc?.price ? Number(btc.price).toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 0 }) : "—"}
            </div>
            
            <div className={`flex items-center gap-1.5 pt-2 font-black text-xs uppercase tracking-widest ${positive ? 'text-green-500' : 'text-red-500'}`}>
               <ChangeIcon size={14} />
               <span>{positive ? "+" : ""}{priceChange}%</span>
               <span className="text-[9px] text-slate-300 ml-1">24H_SHIFT</span>
            </div>
         </div>

         <div className="mt-8 relative z-10 border-t border-slate-50 pt-4">
            <div className="flex justify-between items-center">
               <div className="flex flex-col">
                  <span className="text-[8px] font-black tracking-widest text-slate-300 uppercase leading-none mb-1">Volume_24h</span>
                  <span className="text-[11px] font-black text-slate-800 tracking-tight leading-none">${formatNumber(btc?.volume)}</span>
               </div>
               <div className="flex items-center gap-2">
                  <div className="w-1.5 h-1.5 rounded-full bg-orange-500 animate-pulse" />
                  <span className="text-[8px] font-black tracking-widest text-slate-300 uppercase">Telemetry_Live</span>
               </div>
            </div>
         </div>
      </div>
    </div>
  );
}
