"use client";

import React from "react";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Area,
  ComposedChart,
  Legend
} from "recharts";
import { useScoresData } from "@/hooks/useScoresData";
import { TrendingUp, Activity } from "lucide-react";

export default function ScoreHistoryChart() {
  const { history, loading } = useScoresData();

  if (loading || !history || history.length === 0) {
    return (
      <div className="w-full h-[400px] bg-card rounded-[2.5rem] border border-[var(--color-border)] p-10 flex items-center justify-center">
         <div className="flex flex-col items-center gap-4">
            <Activity className="animate-pulse text-blue-500/20" size={40} />
            <p className="text-[11px] font-black uppercase tracking-widest text-secondary/40">Synchronizing History...</p>
         </div>
      </div>
    );
  }

  // Formatting for Recharts
  const data = history.map(item => ({
    ...item,
    formattedDate: new Date(item.date).toLocaleDateString('nl-NL', { day: '2-digit', month: 'short' }),
  }));

  return (
    <div className="w-full bg-card rounded-[2.5rem] border border-[var(--color-border)] p-6 sm:p-10 shadow-[0_8px_30px_rgb(0,0,0,0.04)] relative overflow-hidden group transition-all hover:shadow-[0_20px_50px_rgba(0,0,0,0.08)]">
      <div className="absolute inset-0 opacity-[0.03] pointer-events-none bg-[radial-gradient(#000_1px,transparent_1px)] [background-size:24px_24px]" />
      
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-8 relative z-10">
        <div className="flex items-center gap-4">
          <div className="w-12 h-12 rounded-2xl bg-blue-500/10 border border-blue-500/20 flex items-center justify-center text-blue-500 shadow-inner">
            <TrendingUp size={24} strokeWidth={1.5} />
          </div>
          <div>
            <div className="text-[11px] font-bold text-secondary/60 uppercase tracking-[0.2em] mb-0.5">Performance Analytics</div>
            <div className="text-2xl font-black text-foreground tracking-tight uppercase leading-none">Intelligence Correlation</div>
          </div>
        </div>

        <div className="flex items-center gap-6">
           <div className="flex items-center gap-2">
              <div className="w-2 h-2 rounded-full bg-blue-500" />
              <span className="text-[10px] font-black uppercase tracking-widest text-secondary">Master Score</span>
           </div>
           <div className="flex items-center gap-2">
              <div className="w-2 h-2 rounded-full bg-slate-300" />
              <span className="text-[10px] font-black uppercase tracking-widest text-secondary">BTC Price</span>
           </div>
        </div>
      </div>

      <div className="h-[350px] w-full relative z-10">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={data}>
            <defs>
              <linearGradient id="colorScore" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.1}/>
                <stop offset="95%" stopColor="#3b82f6" stopOpacity={0}/>
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#f1f5f9" />
            <XAxis 
              dataKey="formattedDate" 
              axisLine={false}
              tickLine={false}
              tick={{ fontSize: 10, fontWeight: 700, fill: '#94a3b8' }}
              dy={10}
            />
            <YAxis 
              yAxisId="left"
              domain={[0, 100]} 
              axisLine={false}
              tickLine={false}
              tick={{ fontSize: 10, fontWeight: 700, fill: '#94a3b8' }}
            />
            <YAxis 
              yAxisId="right"
              orientation="right"
              domain={['auto', 'auto']}
              axisLine={false}
              tickLine={false}
              tick={{ fontSize: 10, fontWeight: 700, fill: '#cbd5e1' }}
            />
            <Tooltip 
              contentStyle={{ 
                borderRadius: '1rem', 
                border: 'none', 
                boxShadow: '0 10px 25px -5px rgba(0, 0, 0, 0.1)',
                fontSize: '11px',
                fontWeight: '900',
                textTransform: 'uppercase'
              }}
            />
            <Area 
              yAxisId="left"
              type="monotone" 
              dataKey="macro" 
              stroke="none" 
              fillOpacity={1} 
              fill="url(#colorScore)" 
            />
            <Line 
              yAxisId="left"
              type="monotone" 
              dataKey="technical" 
              stroke="#3b82f6" 
              strokeWidth={3} 
              dot={false}
              activeDot={{ r: 6, strokeWidth: 0 }}
            />
            <Line 
              yAxisId="right"
              type="monotone" 
              dataKey="btc_price" 
              stroke="#cbd5e1" 
              strokeWidth={2} 
              strokeDasharray="5 5"
              dot={false} 
            />
          </ComposedChart>
        </ResponsiveContainer>
      </div>

      <div className="mt-8 pt-6 border-t border-[var(--color-border-subtle)] relative z-10">
         <p className="text-[10px] text-secondary/50 leading-relaxed font-bold uppercase tracking-wider italic text-center">
            Historical correlation between technical intelligence scores and BTC price action (30D Lookback).
         </p>
      </div>
    </div>
  );
}
