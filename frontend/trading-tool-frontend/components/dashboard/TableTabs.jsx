"use client";

import React, { useEffect, useState } from "react";
import { TrendingUp, Globe2, Coins, Bot } from "lucide-react";
import { useTranslation } from "@/app/providers/I18nProvider";

/**
 * 📑 TableTabs — Unified Deep Analysis Section (V2.1)
 * Consolidates Technical, Macro, and Market Data tables into one tabbed view.
 */
export default function TableTabs({ 
  technicalTable, 
  macroTable, 
  marketTable,
  botsTable,
  onActiveTabChange,
}) {
  const { t } = useTranslation();
  const [activeTab, setActiveTab] = useState("technical");

  useEffect(() => {
    onActiveTabChange?.(activeTab);
  }, [activeTab, onActiveTabChange]);

  const renderTabContent = (content) =>
    typeof content === "function" ? content() : content;

  const tabs = [
    { id: "technical", label: t.dashboard.tabs.technical, icon: <TrendingUp size={16} /> },
    { id: "macro", label: t.dashboard.tabs.macro, icon: <Globe2 size={16} /> },
    { id: "market", label: t.dashboard.tabs.market, icon: <Coins size={16} /> },
    { id: "bots", label: t.dashboard.tabs.bots, icon: <Bot size={16} /> },
  ];

  return (
    <div className="w-full space-y-4">
      {/* Tab Navigation (Pill Container Style) */}
      <div className="w-full overflow-x-auto no-scrollbar pb-2">
        <div className="inline-flex p-1 bg-slate-100/50 dark:bg-slate-900/50 border border-slate-200 dark:border-slate-800 rounded-[1.5rem] shadow-inner mb-2 transition-colors min-w-max">
          {tabs.map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`
                flex items-center gap-2.5 px-6 py-2 rounded-2xl 
                text-[11px] font-black uppercase tracking-widest transition-all whitespace-nowrap
                ${activeTab === tab.id 
                  ? "bg-card dark:bg-slate-800 text-blue-600 dark:text-blue-400 shadow-sm border border-slate-200 dark:border-slate-700" 
                  : "text-secondary dark:text-slate-500 hover:text-slate-600 dark:hover:text-slate-300"}
              `}
            >
              {React.cloneElement(tab.icon || <div />, { 
                size: 13, 
                className: activeTab === tab.id ? "text-blue-600 dark:text-blue-400" : "text-secondary dark:text-slate-500" 
              })}
              {tab.label}
            </button>
          ))}
        </div>
      </div>

      {/* Tab Content */}
      <div className="animate-fade-in">
        {activeTab === "technical" && renderTabContent(technicalTable)}
        {activeTab === "macro" && renderTabContent(macroTable)}
        {activeTab === "market" && renderTabContent(marketTable)}
        {activeTab === "bots" && renderTabContent(botsTable)}
      </div>
      
      {/* Footer Info */}
      <div className="px-4 py-8 flex items-center justify-between opacity-60">
         <p className="text-[10px] uppercase font-bold tracking-[0.2em] text-secondary dark:text-slate-500">
           {t.dashboard.tabs.analysis_mode} <span className="text-blue-600/30">/</span> {t.dashboard.tabs.source}
         </p>
         <button className="text-[10px] font-black text-blue-600 dark:text-blue-400 uppercase tracking-widest hover:underline px-4 py-2 bg-card dark:bg-slate-900 border border-slate-100 dark:border-slate-800 rounded-lg shadow-sm active:scale-95 transition-all">
           {t.dashboard.tabs.export}
         </button>
      </div>
    </div>
  );
}
