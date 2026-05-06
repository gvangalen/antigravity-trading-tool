"use client";

import React, { useState, useEffect, useRef } from "react";
import { usePathname, useSearchParams, useRouter } from "next/navigation";
import { assistantChat, fetchAssistantInsight, getAssistantPreferences } from "@/lib/api/ai";
import { Send, Zap, Brain, Shield, BarChart3, Loader2, X, MessageSquare, Target, Activity, FileText, Bot, ChevronDown, ListChecks } from "lucide-react";
import { useOnboarding } from "@/hooks/useOnboarding";
import { ChatSkeleton } from "@/components/dashboard/DashboardSkeleton";
import { useAsset } from "@/app/providers/AssetProvider";
import { useWatchlist } from "@/hooks/useWatchlist";

export default function AIAssistant({ isOpen, setIsOpen }) {
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const { symbol: globalSymbol } = useAsset();
  const router = useRouter();
  const watchlist = useWatchlist();
  
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(false);
  const [messages, setMessages] = useState([]);
  const [preferences, setPreferences] = useState({});
  const [insight, setInsight] = useState(null);
  const [insightLoading, setInsightLoading] = useState(false);
  const [lastUpdated, setLastUpdated] = useState(null);
  
  const messagesEndRef = useRef(null);
  const scrollRef = useRef(null);
  const [showReasoning, setShowReasoning] = useState(false);
  
  // 🧭 Onboarding Context
  const { stepStatus, onboardingComplete } = useOnboarding();
  const isOnboarding = (pathname.includes("onboarding") || !onboardingComplete) && pathname !== "/dashboard";

  // Helper to get nested insight consistently
  const getInsightField = (block, field) => {
    return insight?.[block]?.[field] || insight?.[block.replace('_insight', '')]?.[field];
  };

  const getContext = () => {
    const pageMap = {
      "/dashboard": "Dashboard",
      "/": "Dashboard",
      "/market": "Market",
      "/macro": "Macro",
      "/technical": "Technical",
      "/setup": "Setups",
      "/strategy": "Strategies",
      "/onboarding": "Onboarding",
      "/bot": "Bots",
      "/report": "Reports",
    };

    return {
      page_type: pageMap[pathname] || "Unknown",
      symbol: searchParams.get("symbol") || searchParams.get("asset") || globalSymbol || "BTC",
      timeframe: searchParams.get("tf") || searchParams.get("interval") || (pathname.includes("dashboard") || pathname === "/" ? "Weekly" : "Daily"),
      setup_name: searchParams.get("name") || "No specific setup",
    };
  };

  const context = getContext();

  useEffect(() => {
    if (isOpen) {
      loadInsight();
      if (Object.keys(preferences).length === 0) {
        getAssistantPreferences().then(res => setPreferences(res.preferences || {}));
      }
    }
  }, [isOpen, pathname, searchParams, globalSymbol]);

  const loadInsight = async () => {
    setInsightLoading(true);
    try {
      const res = await fetchAssistantInsight(context);
      setInsight(res);
      setLastUpdated(new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }));
    } catch (err) {
      console.error("Failed to fetch AI insight", err);
    } finally {
      setInsightLoading(false);
    }
  };

  const handleActionClick = async (action) => {
    if (!action) return;
    const { type, symbol, params } = action;

    try {
      if (type === "add_to_watchlist") {
        if (symbol && watchlist?.add) {
          await watchlist.add(symbol);
        }
      } else if (type === "open_setup_page") {
        router.push(`/setup${symbol ? `?symbol=${symbol}` : ""}`);
        setIsOpen(false);
      } else if (type === "generate_strategy") {
        router.push(`/strategy${symbol ? `?symbol=${symbol}` : ""}`);
        setIsOpen(false);
      } else if (type === "open_bot_draft") {
        // Support prefilled bot parameters via query params
        const qParams = new URLSearchParams();
        if (symbol) qParams.append("symbol", symbol);
        if (params?.mode) qParams.append("mode", params.mode);
        if (params?.risk) qParams.append("risk", params.risk);
        if (params?.budget) qParams.append("budget", params.budget);
        
        router.push(`/bot?action=new_bot&${qParams.toString()}`);
        setIsOpen(false);
      }
    } catch (err) {
      console.error("Action execution failed", err);
    }
  };

  const handleChat = async (directQuery, isSilent = false) => {
    const activeQuery = directQuery !== undefined ? directQuery : query;
    if (!activeQuery.trim()) return;

    setLoading(true);
    if (!isSilent) setQuery("");
    
    if (!isSilent) {
      setMessages(prev => [...prev, { role: "user", text: activeQuery }]);
    }

    try {
      const res = await assistantChat(activeQuery, context);
      setMessages(prev => [...prev, { role: "assistant", text: res.response, intent: res.intent, action: res.action }]);
    } catch (err) {
      setMessages(prev => [...prev, { 
        role: "assistant", 
        text: "⚠️ Failed to retrieve analysis. Please try again.", 
        isError: true 
      }]);
    } finally {
      setLoading(false);
    }
  };

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, loading]);

  if (!isOpen) return null;

  return (
    <aside 
      className={`fixed top-0 right-0 h-full bg-card dark:bg-[#0f172a] border-l border-slate-200 dark:border-slate-800 z-[70] shadow-2xl transition-all duration-300 flex flex-col ${
        isOpen ? "translate-x-0" : "translate-x-full"
      } w-full md:w-[400px]`}
    >
      {/* HEADER */}
      <div className="p-5 border-b border-slate-100 dark:border-slate-800 flex items-center justify-between bg-card dark:bg-[#0f172a] relative z-10 shadow-sm">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-blue-600 flex items-center justify-center text-white shadow-lg shadow-blue-600/30">
             <Bot size={22} />
          </div>
          <div>
            <h2 className="text-sm font-black text-foreground dark:text-slate-100 tracking-tight">Tradamind AI</h2>
            <div className="flex items-center gap-1.5 mt-0.5">
              <div className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
              <span className="text-[10px] font-bold text-secondary dark:text-slate-500 uppercase tracking-widest leading-none">Intelligence Layer Pulse</span>
            </div>
          </div>
        </div>
        <button 
          onClick={() => setIsOpen(false)}
          className="p-2 hover:bg-slate-50 dark:hover:bg-slate-900 rounded-lg transition-colors text-secondary hover:text-slate-900 dark:hover:text-slate-100"
        >
          <X size={18} />
        </button>
      </div>

      <div className="flex-1 overflow-y-auto no-scrollbar scroll-smooth" ref={scrollRef}>
        {/* ACTIVE CONTEXT CHIP */}
        <div className="px-6 py-4 border-b border-slate-50 dark:border-slate-800">
          <div className="flex items-center gap-3 p-3 bg-card dark:bg-slate-900 rounded-xl border border-blue-50/50 dark:border-blue-900/30 shadow-sm transition-colors">
             <div className="p-2 bg-blue-50 dark:bg-blue-900/30 rounded-lg">
                <Activity size={14} className="text-blue-500" />
             </div>
             <div>
                <span className="text-[9px] font-black text-blue-300 uppercase tracking-widest block leading-none mb-1">Active Context</span>
                <span className="text-[11px] font-bold text-dim dark:text-slate-300 block leading-none">{context.page_type} • {context.symbol} • {context.timeframe}</span>
             </div>
          </div>
        </div>

        {/* INSIGHT BLOCKS */}
        <div className="p-6 border-b border-slate-100 dark:border-slate-800 space-y-6">
          <div className="flex items-center justify-between mb-2">
            <h3 className="text-[10px] font-black text-secondary dark:text-slate-500 tracking-[0.2em] uppercase flex items-center gap-2">
              <Zap size={12} className="text-amber-500 animate-pulse" />
              Live Intelligence
            </h3>
            <div className="flex items-center gap-2">
               {insightLoading && <Loader2 size={12} className="animate-spin text-slate-300 dark:text-slate-600" />}
               {!insightLoading && lastUpdated && <span className="text-[9px] font-bold text-slate-300 dark:text-slate-600 uppercase">{lastUpdated}</span>}
            </div>
          </div>

          {/* 🧭 SETUP GUIDE (ONLY DURING ONBOARDING) */}
          {isOnboarding ? (
            <div className="p-4 bg-blue-600/5 dark:bg-blue-600/10 border-2 border-blue-600/20 rounded-2xl animate-in slide-in-from-right-4 duration-500">
               <div className="flex items-center gap-2.5 mb-3">
                  <div className="p-1.5 bg-blue-600 rounded-lg shadow-lg shadow-blue-600/20">
                    <ListChecks size={14} className="text-white" />
                  </div>
                  <span className="text-[10px] font-black text-blue-600 dark:text-blue-400 tracking-widest uppercase">Setup Guide</span>
               </div>
               
               <div className="space-y-3">
                  <p className="text-sm font-bold text-foreground dark:text-slate-100 leading-snug">
                    {/* 🎖️ CELEBRATION MODE */}
                    {status?.[`has_${pathname.split('/').pop()}`] ? (
                      `Excellent. The ${pathname.split('/').pop()} data stream is now stabilized and streaming high-fidelity intelligence to your cockpit. Return to the Launch Center for the next protocol.`
                    ) : (
                      /* 🧭 GUIDE MODE */
                      pathname.includes("market") ? "Market data is required to monitor live price action. Search for BTC and add it to your monitor." :
                      pathname.includes("macro") ? "Macro indicators track global liquidity and dollar strength. Search for DXY and add it to your monitor." :
                      pathname.includes("technical") ? "Technical signals identify price momentum and trends. Search for RSI and add it to your monitor." :
                      pathname.includes("setup") ? "Setups define your specific entry and exit rules. Click the 'New Setup' button to create your first rule-set." :
                      pathname.includes("strategy") ? "The strategy engine builds your AI-driven execution model. Click the 'Generate Strategy' button to finalize your cockpit." :
                      "I will guide you through the 5 steps to activate your system. Once initialized, your dashboard will be fully operational with live data and AI insights."
                    )}
                  </p>
                  <div className="flex gap-2">
                     <div className="px-3 py-1.5 bg-blue-600 rounded-xl text-[9px] font-black text-white uppercase tracking-widest">
                       Action: {pathname.includes("market") ? "Add BTC" :
                                pathname.includes("macro") ? "Add DXY" :
                                pathname.includes("technical") ? "Add RSI" :
                                pathname.includes("setup") ? "Create Setup" :
                                pathname.includes("strategy") ? "Generate Strategy" :
                                "Choose Module"}
                     </div>
                  </div>
               </div>
            </div>
          ) : (
            <>
              {/* GREETING */}
              <div className="animate-fade-in group">
                <p className="text-sm font-medium text-foreground dark:text-slate-200 leading-relaxed italic border-l-4 border-blue-500 pl-4 py-3 bg-blue-50/40 dark:bg-blue-900/10 rounded-xl transition-all group-hover:bg-blue-50/60 dark:group-hover:bg-blue-900/20 shadow-sm border border-blue-100/30 dark:border-blue-900/20">
                  "{insight?.greeting || 
                    (context.page_type === "Onboarding" 
                      ? `Hello ${preferences?.first_name || 'Henk'}, I have initialized the Launch Protocol. Please complete the modules to activate your cockpit.`
                      : (insightLoading 
                        ? `Hello ${preferences?.first_name || 'Henk'}, analyzing ${context.symbol}...` 
                        : `Hello ${preferences?.first_name || 'Henk'}, monitoring ${context.symbol} market.`
                      )
                    )
                  }"
                </p>
              </div>

              <div className="space-y-6 animate-fade-in">
                {/* 🛡️ COACH */}
                <div className="group">
                  <div className="flex items-center gap-2.5 mb-2.5">
                    <div className="p-1.5 bg-amber-50 dark:bg-amber-900/20 rounded-lg group-hover:bg-amber-100 dark:group-hover:bg-amber-900/30 transition-colors">
                      <Shield size={14} className="text-amber-600 dark:text-amber-300" />
                    </div>
                    <span className="text-[10px] font-black text-foreground dark:text-slate-100 tracking-widest uppercase">COACH</span>
                  </div>
                  <div className="pl-9 space-y-2.5">
                    <p className="text-sm font-bold text-foreground dark:text-slate-100 leading-snug">
                      {getInsightField('bot_insight', 'conclusion') || (insightLoading ? "Analyzing..." : "No strategy data found")}
                    </p>
                    <div className="flex">
                      <span className="text-xs font-black text-blue-600 dark:text-blue-400 bg-blue-50 dark:bg-blue-900/30 px-3 py-2 rounded-xl border border-blue-100 dark:border-blue-900/40 shadow-sm transition-all hover:bg-white dark:hover:bg-slate-800 hover:shadow-md cursor-default leading-tight">
                        {getInsightField('bot_insight', 'action') || (insightLoading ? "Waiting..." : "Add a setup to start")}
                      </span>
                    </div>
                    {showReasoning && getInsightField('bot_insight', 'why') && (
                      <div className="mt-2 p-3 bg-slate-100/50 dark:bg-slate-900/50 rounded-lg border border-slate-200/50 dark:border-slate-800 animate-in slide-in-from-top-1 duration-200">
                        <p className="text-xs font-medium text-muted dark:text-slate-400 leading-relaxed italic">
                          "{getInsightField('bot_insight', 'why')}"
                        </p>
                      </div>
                    )}
                  </div>
                </div>

                {/* 📈 MARKET */}
                <div className="group">
                  <div className="flex items-center gap-2.5 mb-2.5">
                    <div className="p-1.5 bg-blue-50 dark:bg-blue-900/20 rounded-lg group-hover:bg-blue-100 dark:group-hover:bg-blue-900/30 transition-colors">
                      <BarChart3 size={14} className="text-blue-600 dark:text-blue-400" />
                    </div>
                    <span className="text-[10px] font-black text-foreground dark:text-slate-100 tracking-widest uppercase">MARKET</span>
                  </div>
                  <div className="pl-9 space-y-2.5">
                    <p className="text-sm font-medium text-slate-700 dark:text-slate-300 leading-snug">
                      {getInsightField('market_insight', 'conclusion') || (insightLoading ? "Scanning..." : "Analyzing market trend...")}
                    </p>
                    <div className="inline-block">
                      <span className="text-xs font-bold text-muted dark:text-slate-400 bg-[var(--color-border-subtle)] dark:bg-slate-900 border border-slate-100 dark:border-slate-800 px-2.5 py-1.5 rounded-xl inline-block transition-all hover:bg-white dark:hover:bg-slate-800 hover:shadow-sm">
                        {getInsightField('market_insight', 'action') || (insightLoading ? "Processing..." : "Monitor trend")}
                      </span>
                    </div>
                    {showReasoning && getInsightField('market_insight', 'why') && (
                      <div className="mt-2 p-3 bg-slate-100/50 dark:bg-slate-900/50 rounded-lg border border-slate-200/50 dark:border-slate-800 animate-in slide-in-from-top-1 duration-200">
                        <p className="text-xs font-medium text-muted dark:text-slate-400 leading-relaxed italic">
                          "{getInsightField('market_insight', 'why')}"
                        </p>
                      </div>
                    )}
                  </div>
                </div>
              </div>

              {/* TOGGLE BUTTON */}
              <div className="pt-2">
                <button 
                  onClick={() => setShowReasoning(!showReasoning)}
                  className="group flex items-center gap-2 text-[10px] font-black text-secondary dark:text-slate-500 hover:text-blue-500 dark:hover:text-blue-400 uppercase tracking-[0.2em] transition-all"
                >
                  <div className={`transition-transform duration-200 ${showReasoning ? 'rotate-180' : ''}`}>
                    <ChevronDown size={12} />
                  </div>
                  {showReasoning ? "Quick Glance" : "Deep Analysis"}
                </button>
              </div>
            </>
          )}
        </div>

        {/* CHIP NAVIGATION */}
        <div className="px-6 py-4 flex flex-wrap items-center gap-2 border-b border-slate-100 dark:border-slate-800">
          {[
            { id: "chat", icon: <MessageSquare size={14} />, label: "Chat" },
            { id: "analyst", icon: <Brain size={14} />, label: "Analysis" },
            { id: "coach", icon: <Target size={14} />, label: "Coach" },
            { id: "report", icon: <FileText size={14} />, label: "Report" },
          ].map(chip => (
            <button 
              key={chip.id}
              onClick={() => handleChat(`Analyze my current ${chip.label} status/context`, true)}
              className="flex items-center gap-2 px-3 py-2 rounded-xl bg-card dark:bg-slate-900 border border-slate-200 dark:border-slate-800 text-[10px] font-black uppercase tracking-widest text-muted dark:text-slate-400 hover:border-blue-600 dark:hover:border-blue-400 hover:text-blue-600 dark:hover:text-blue-300 hover:shadow-sm transition-all whitespace-nowrap"
            >
              {chip.icon}
              {chip.label}
            </button>
          ))}
        </div>

        {/* MESSAGES AREA */}
        <div className="p-6 space-y-6 pb-24">
          {messages.map((m, i) => (
            <div key={i} className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}>
              <div className={`max-w-[90%] rounded-2xl p-4 ${
                m.role === "user" 
                  ? "bg-blue-600 text-white shadow-lg shadow-blue-600/10" 
                  : m.isError 
                    ? "bg-rose-50 dark:bg-rose-900/20 border border-rose-100 dark:border-rose-900 text-rose-700 dark:text-rose-300"
                    : "bg-[var(--color-border-subtle)] dark:bg-slate-900 border border-slate-100 dark:border-slate-800 text-foreground dark:text-slate-100"
              }`}>
                <p className="text-sm leading-relaxed">{m.text}</p>
                {m.action && (
                  <ActionCard action={m.action} onAction={handleActionClick} />
                )}
                {m.isError && (
                  <button 
                    onClick={() => handleChat(messages[i-1]?.text)} 
                    className="mt-2 text-[10px] font-bold uppercase tracking-widest underline hover:text-rose-900 dark:hover:text-rose-100"
                  >
                    Retry
                  </button>
                )}
              </div>
            </div>
          ))}
          {loading && (
            <ChatSkeleton />
          )}
          <div ref={messagesEndRef} />
        </div>
      </div>

      {/* INPUT AREA */}
      <div className="absolute bottom-0 left-0 right-0 p-6 bg-card dark:bg-[#0f172a] border-t border-slate-100 dark:border-slate-800 shadow-[0_-10px_20px_-10px_rgba(0,0,0,0.05)]">
        <div className="relative group">
          <input 
            type="text" 
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleChat()}
            placeholder="Ask a question..."
            className="w-full pl-6 pr-14 py-4 bg-[var(--color-border-subtle)] dark:bg-slate-900 border border-slate-100 dark:border-slate-800 rounded-2xl focus:ring-4 focus:ring-blue-600/5 focus:bg-white dark:focus:bg-slate-800 focus:border-blue-600/20 transition-all outline-none text-sm text-foreground dark:text-slate-100"
          />
          <button 
            onClick={() => handleChat()}
            disabled={loading || !query.trim()}
            className="absolute right-3 top-2.5 p-2 rounded-xl bg-slate-900 dark:bg-blue-600 text-white hover:bg-blue-600 dark:hover:bg-blue-700 disabled:opacity-50 transition-all shadow-lg"
          >
            <Send size={18} />
          </button>
        </div>
      </div>
    </aside>
  );
}

function ActionCard({ action, onAction }) {
  const [loading, setLoading] = useState(false);
  const [success, setSuccess] = useState(false);

  const handleClick = async () => {
    setLoading(true);
    try {
      await onAction(action);
      setSuccess(true);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const getActionLabel = () => {
    switch (action.type) {
      case "add_to_watchlist": return `Add ${action.symbol || ""} to Watchlist`;
      case "open_setup_page": return `Configure Setup for ${action.symbol || ""}`;
      case "generate_strategy": return `Generate ${action.symbol || ""} Strategy`;
      case "open_bot_draft": return `Deploy ${action.symbol || ""} Paper Bot`;
      default: return "Execute Action";
    }
  };

  const getActionDescription = () => {
    switch (action.type) {
      case "add_to_watchlist": return `Add ${action.symbol || ""} to the live tracking engine.`;
      case "open_setup_page": return `Open setups tab to create custom macro rules for ${action.symbol || ""}.`;
      case "generate_strategy": return `Use AI to build a customized algorithmic strategy for ${action.symbol || ""}.`;
      case "open_bot_draft": return `Open bot configuration modal with recommended pre-filled parameters.`;
      default: return "";
    }
  };

  return (
    <div className="mt-3 p-4 bg-blue-100/10 dark:bg-blue-950/20 border border-blue-200/50 dark:border-blue-900/40 rounded-2xl flex flex-col gap-3">
      <div>
        <h4 className="text-[10px] font-black uppercase tracking-[0.15em] text-blue-600 dark:text-blue-400">Proposed Action</h4>
        <p className="text-[11px] text-slate-500 dark:text-slate-400 font-medium mt-1 leading-snug">{getActionDescription()}</p>
      </div>
      
      <button 
        onClick={handleClick}
        disabled={loading || success}
        className={`w-full py-2.5 rounded-xl text-[10px] font-black uppercase tracking-widest text-white transition-all shadow-md active:scale-95 ${
          success 
            ? "bg-emerald-600 shadow-emerald-600/15 cursor-default" 
            : "bg-blue-600 hover:bg-blue-700 shadow-blue-600/15"
        }`}
      >
        {loading ? "Processing..." : success ? "✓ Executed Successfully" : getActionLabel()}
      </button>
    </div>
  );
}
