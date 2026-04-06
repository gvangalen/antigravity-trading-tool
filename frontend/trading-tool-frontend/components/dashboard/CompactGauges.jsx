"use client";

import React from "react";
import { useScoresData } from "@/hooks/useScoresData";
import { Globe2, LineChart, DollarSign, Settings2 } from "lucide-react";

/**
 * 📏 CompactGauges — Minimalist Status Bar (V2.1)
 * Replaces large Gauge cards with a slim horizontal strip.
 */
export default function CompactGauges() {
  const { macro, technical, market, setup, loading } = useScoresData();

  const items = [
    { title: "Macro", icon: <Globe2 size={14} />, score: macro.score },
    { title: "Technical", icon: <LineChart size={14} />, score: technical.score },
    { title: "Market", icon: <DollarSign size={14} />, score: market.score },
    { title: "Setup", icon: <Settings2 size={14} />, score: setup.score },
  ];

  if (loading) {
     return (
       <div className="flex gap-4 w-full animate-pulse">
         {[1, 2, 3, 4].map(i => (
           <div key={i} className="h-10 bg-[var(--bg-soft)] flex-1 rounded-xl" />
         ))}
       </div>
     );
  }

  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-4 w-full">
      {items.map((item, idx) => {
        const score = Math.round(item.score || 0);
        
        // Color logic
        let colorClass = "text-gray-400";
        let bgClass = "bg-gray-50";
        let borderClass = "border-gray-100";

        if (score >= 75) {
          colorClass = "text-green-600";
          bgClass = "bg-green-50";
          borderClass = "border-green-100";
        } else if (score >= 50) {
          colorClass = "text-blue-600";
          bgClass = "bg-blue-50";
          borderClass = "border-blue-100";
        } else if (score < 40) {
          colorClass = "text-red-500";
          bgClass = "bg-red-50";
          borderClass = "border-red-100";
        }

        return (
          <div 
            key={idx} 
            className={`
              flex items-center justify-between px-4 py-2.5 
              rounded-xl border ${borderClass} ${bgClass}
              shadow-sm transition-all hover:shadow-md
            `}
          >
            <div className="flex items-center gap-2.5">
              <div className={`p-1.5 rounded-lg bg-white shadow-sm ${colorClass}`}>
                {item.icon}
              </div>
              <span className="text-[11px] font-bold uppercase tracking-wider text-[var(--text-light)]">
                {item.title}
              </span>
            </div>
            
            <div className="flex items-center gap-1.5">
              <span className={`text-sm font-black font-mono ${colorClass}`}>
                {score}%
              </span>
              <div className="w-1.5 h-1.5 rounded-full fill-current bg-current opacity-60" style={{ color: colorClass.includes('text-') ? `var(--${colorClass.split('-')[1]})` : 'inherit' }} />
            </div>
          </div>
        );
      })}
    </div>
  );
}
