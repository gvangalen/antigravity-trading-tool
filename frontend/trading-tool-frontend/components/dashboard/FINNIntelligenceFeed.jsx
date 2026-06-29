"use client";

import React, { useState } from "react";
import useIntelligenceEvents from "@/hooks/useIntelligenceEvents";
import { useTranslation } from "@/app/providers/I18nProvider";
import { 
  AlertTriangle, 
  Activity, 
  TrendingUp, 
  Layers, 
  ShieldAlert, 
  X, 
  Terminal, 
  Sparkles,
  ArrowRight,
  MessageSquare
} from "lucide-react";

export default function FINNIntelligenceFeed() {
  const { events, loading, error, archiveEvent } = useIntelligenceEvents();
  const { t } = useTranslation();
  const [activeTab, setActiveTab] = useState("all");
  const copy = t?.dashboard?.finnFeed || {};

  const getSeverityStyles = (severity) => {
    switch (severity?.toLowerCase()) {
      case "critical":
        return {
          bg: "bg-rose-50/70 dark:bg-rose-950/20",
          border: "border-rose-200 dark:border-rose-900/30",
          text: "text-rose-800 dark:text-rose-300",
          badge: "bg-rose-500/10 text-rose-600 dark:text-rose-400 border border-rose-300/30",
          iconColor: "text-rose-600 dark:text-rose-400"
        };
      case "warning":
        return {
          bg: "bg-amber-50/70 dark:bg-amber-950/20",
          border: "border-amber-200 dark:border-amber-900/30",
          text: "text-amber-800 dark:text-amber-300",
          badge: "bg-amber-500/10 text-amber-600 dark:text-amber-400 border border-amber-300/30",
          iconColor: "text-amber-600 dark:text-amber-400"
        };
      case "info":
      default:
        return {
          bg: "bg-blue-50/70 dark:bg-blue-950/20",
          border: "border-blue-200 dark:border-blue-900/30",
          text: "text-blue-800 dark:text-blue-300",
          badge: "bg-blue-500/10 text-blue-600 dark:text-blue-400 border border-blue-300/30",
          iconColor: "text-blue-600 dark:text-blue-400"
        };
    }
  };

  const getEventIcon = (type) => {
    switch (type) {
      case "drawdown_alert":
        return <ShieldAlert className="w-4 h-4" />;
      case "risk_spike":
        return <AlertTriangle className="w-4 h-4" />;
      case "duplicate_strategy":
        return <Layers className="w-4 h-4" />;
      case "volatility_expansion":
        return <Activity className="w-4 h-4" />;
      case "macro_shift":
      case "setup_activation":
      default:
        return <TrendingUp className="w-4 h-4" />;
    }
  };

  const handleActionChipClick = (actionType, event) => {
    // We send a custom event that can be listened to by the AIAssistant or pages to trigger action flow conversationally or directly
    if (actionType === "discuss") {
      const chatQuery = copy.discussQuery
        .replace("{title}", event.title)
        .replace("{symbol}", event.symbol || "portfolio");
      const customEvent = new CustomEvent("finn-action-trigger", { 
        detail: { query: chatQuery, openAssistant: true } 
      });
      window.dispatchEvent(customEvent);
    } else if (actionType === "view_bot") {
      window.location.href = "/bot";
    } else if (actionType === "view_market") {
      window.location.href = `/market?symbol=${event.symbol || "BTC"}`;
    }
  };

  const filteredEvents = events.filter(ev => {
    if (activeTab === "all") return true;
    if (activeTab === "critical") return ev.severity === "critical" || ev.severity === "warning";
    if (activeTab === "info") return ev.severity === "info";
    return true;
  });

  return (
    <div className="card bg-white dark:bg-[#0f172a] border-2 border-slate-100 dark:border-slate-800 rounded-3xl overflow-hidden shadow-sm hover:shadow-md transition-shadow">
      
      {/* 🚀 HEADER: FINN LIVE CONTEXT */}
      <div className="card-header border-b border-slate-100 dark:border-slate-800 p-4 sm:p-6 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <div className="relative flex h-3 w-3">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-blue-400 opacity-75"></span>
            <span className="relative inline-flex rounded-full h-3 w-3 bg-blue-500"></span>
          </div>
          <div>
            <h3 className="card-title text-slate-900 dark:text-white uppercase tracking-widest text-[12px] font-black flex items-center gap-2">
              <Terminal className="w-4 h-4 text-blue-600" />
              {copy.title}
            </h3>
            <p className="text-[10px] text-slate-400 dark:text-slate-500 font-bold tracking-tight mt-0.5">
              {copy.subtitle}
            </p>
          </div>
        </div>
        
        {/* TAB CONTROLS */}
        <div className="flex items-center gap-1.5 bg-slate-50 dark:bg-slate-900 p-1 rounded-xl border border-slate-100 dark:border-slate-800">
          <button 
            onClick={() => setActiveTab("all")}
            className={`px-3 py-1 text-[10px] uppercase tracking-wider font-black rounded-lg transition-all ${activeTab === 'all' ? 'bg-white dark:bg-slate-800 text-blue-600 dark:text-blue-400 shadow-sm border border-slate-100 dark:border-slate-700' : 'text-slate-400 dark:text-slate-500 hover:text-slate-600'}`}
          >
            {copy.all} ({events.length})
          </button>
          <button 
            onClick={() => setActiveTab("critical")}
            className={`px-3 py-1 text-[10px] uppercase tracking-wider font-black rounded-lg transition-all ${activeTab === 'critical' ? 'bg-white dark:bg-slate-800 text-rose-500 shadow-sm border border-slate-100 dark:border-slate-700' : 'text-slate-400 dark:text-slate-500 hover:text-rose-400'}`}
          >
            {copy.alerts} ({events.filter(e => e.severity === 'critical' || e.severity === 'warning').length})
          </button>
        </div>
      </div>

      {/* 📊 EVENTS CONTAINER */}
      <div className="p-4 sm:p-6 space-y-4 max-h-[380px] overflow-y-auto custom-scrollbar">
        {loading && events.length === 0 ? (
          <div className="py-12 flex flex-col items-center justify-center gap-2">
            <Sparkles className="w-6 h-6 text-blue-500 animate-spin" />
            <p className="text-xs font-bold text-slate-400 dark:text-slate-500 uppercase tracking-widest">
              {copy.loading}
            </p>
          </div>
        ) : error ? (
          <p className="text-xs font-bold text-rose-500 uppercase tracking-widest text-center py-6">
            {error}
          </p>
        ) : filteredEvents.length === 0 ? (
          <div className="py-12 text-center">
            <p className="text-xs font-bold text-slate-400 dark:text-slate-500 uppercase tracking-widest italic">
              {copy.empty}
            </p>
          </div>
        ) : (
          filteredEvents.map((ev) => {
            const styles = getSeverityStyles(ev.severity);
            return (
              <div 
                key={ev.id}
                className={`p-4 rounded-2xl border ${styles.border} ${styles.bg} relative transition-all duration-300 hover:translate-x-1 flex flex-col gap-3 group`}
              >
                {/* DISMISS BUTTON */}
                <button 
                  onClick={() => archiveEvent(ev.id)}
                  className="absolute top-3 right-3 text-slate-400 dark:text-slate-500 hover:text-slate-600 dark:hover:text-slate-300 transition-colors"
                  title={copy.archive}
                >
                  <X className="w-4 h-4" />
                </button>

                {/* HEADER */}
                <div className="flex items-center gap-2.5">
                  <div className={`p-1.5 rounded-lg ${styles.badge} flex items-center justify-center shrink-0`}>
                    {getEventIcon(ev.type)}
                  </div>
                  <div>
                    <h4 className="text-xs sm:text-sm font-black text-slate-900 dark:text-slate-100 flex items-center gap-1.5">
                      {ev.title}
                      {ev.symbol && (
                        <span className="text-[9px] font-black uppercase tracking-widest bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300 px-1.5 py-0.5 rounded">
                          {ev.symbol}
                        </span>
                      )}
                    </h4>
                    <span className="text-[8px] uppercase tracking-wider font-black text-slate-400 dark:text-slate-500">
                      {new Date(ev.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })} • {copy.realtime}
                    </span>
                  </div>
                </div>

                {/* DESCRIPTION */}
                <p className="text-[11px] leading-relaxed font-semibold text-slate-600 dark:text-slate-400 pl-8 pr-4">
                  {ev.description}
                </p>

                {/* ACTION CHIPS */}
                <div className="pl-8 flex flex-wrap gap-2 pt-1">
                  <button 
                    onClick={() => handleActionChipClick("discuss", ev)}
                    className="flex items-center gap-1 px-3 py-1 rounded-xl bg-slate-100 hover:bg-blue-500 dark:bg-slate-800 dark:hover:bg-blue-600 text-[10px] font-black text-slate-700 hover:text-white dark:text-slate-300 transition-all border border-slate-200 dark:border-slate-700 hover:border-transparent uppercase tracking-wider"
                  >
                    <MessageSquare className="w-3 h-3" />
                    {copy.discuss}
                  </button>
                  
                  {ev.type === "drawdown_alert" && (
                    <button 
                      onClick={() => handleActionChipClick("view_bot", ev)}
                      className="flex items-center gap-1 px-3 py-1 rounded-xl bg-slate-100 hover:bg-slate-200 dark:bg-slate-800 dark:hover:bg-slate-700 text-[10px] font-black text-slate-700 dark:text-slate-300 transition-all border border-slate-200 dark:border-slate-700 uppercase tracking-wider"
                    >
                      {copy.manageBot}
                      <ArrowRight className="w-3 h-3" />
                    </button>
                  )}
                  
                  {ev.symbol && (
                  <button 
                      onClick={() => handleActionChipClick("view_market", ev)}
                      className="flex items-center gap-1 px-3 py-1 rounded-xl bg-slate-100 hover:bg-slate-200 dark:bg-slate-800 dark:hover:bg-slate-700 text-[10px] font-black text-slate-700 dark:text-slate-300 transition-all border border-slate-200 dark:border-slate-700 uppercase tracking-wider"
                    >
                      {copy.analyzeSymbol.replace("{symbol}", ev.symbol)}
                      <ArrowRight className="w-3 h-3" />
                    </button>
                  )}
                </div>

              </div>
            );
          })
        )}
      </div>

    </div>
  );
}
