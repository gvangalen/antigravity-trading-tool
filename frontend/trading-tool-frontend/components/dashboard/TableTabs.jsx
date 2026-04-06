"use client";

import React, { useState } from "react";
import CardWrapper from "@/components/ui/CardWrapper";
import { TrendingUp, Globe2, Coins, Search } from "lucide-react";

/**
 * 📑 TableTabs — Unified Deep Analysis Section (V2.1)
 * Consolidates Technical, Macro, and Market Data tables into one tabbed view.
 */
export default function TableTabs({ 
  technicalTable, 
  macroTable, 
  marketTable 
}) {
  const [activeTab, setActiveTab] = useState("technical");

  const tabs = [
    { id: "technical", label: "Technical", icon: <TrendingUp size={16} /> },
    { id: "macro", label: "Macro", icon: <Globe2 size={16} /> },
    { id: "market", label: "Market", icon: <Coins size={16} /> },
  ];

  return (
    <div className="w-full space-y-4">
      {/* Tab Navigation (Pill Container Style) */}
      <div className="inline-flex p-1 bg-slate-100/50 border border-slate-200 rounded-[1.5rem] shadow-inner mb-6">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={`
              flex items-center gap-2.5 px-6 py-2 rounded-2xl 
              text-[11px] font-black uppercase tracking-widest transition-all
              ${activeTab === tab.id 
                ? "bg-white text-blue-600 shadow-sm border border-slate-200" 
                : "text-slate-400 hover:text-slate-600"}
            `}
          >
            {React.cloneElement(tab.icon || <div />, { 
              size: 13, 
              className: activeTab === tab.id ? "text-blue-600" : "text-slate-400" 
            })}
            {tab.label}
          </button>
        ))}
      </div>

      {/* Tab Content */}
      <div className="animate-fade-in">
        {activeTab === "technical" && technicalTable}
        {activeTab === "macro" && macroTable}
        {activeTab === "market" && marketTable}
      </div>
      
      {/* Footer Info */}
      <div className="px-4 py-8 flex items-center justify-between opacity-60">
         <p className="text-[10px] uppercase font-bold tracking-[0.2em] text-slate-400">
           Deep Analysis Mode <span className="text-blue-600/30">/</span> Source: Real-Time API
         </p>
         <button className="text-[10px] font-black text-blue-600 uppercase tracking-widest hover:underline px-4 py-2 bg-white border border-slate-100 rounded-lg shadow-sm active:scale-95 transition-all">
           Export System Log
         </button>
      </div>
    </div>
  );
}
