"use client";

import React, { useState, useEffect, useRef } from "react";
import { usePathname, useSearchParams, useRouter } from "next/navigation";
import { assistantChat, fetchAssistantInsight, getAssistantPreferences, assistantChatStream, executePendingAction } from "@/lib/api/ai";
import { Send, Zap, Brain, Shield, BarChart3, Loader2, X, MessageSquare, Target, Activity, FileText, Bot, ChevronDown, ListChecks, Terminal, Sparkles } from "lucide-react";
import useIntelligenceEvents from "@/hooks/useIntelligenceEvents";
import { useOnboarding } from "@/hooks/useOnboarding";
import { ChatSkeleton } from "@/components/dashboard/DashboardSkeleton";
import { useAsset } from "@/app/providers/AssetProvider";
import { useWatchlist } from "@/hooks/useWatchlist";
import { useModal } from "@/components/modal/ModalProvider";
import { saveNewSetup, fetchSetups } from "@/lib/api/setups";
import { createStrategy, fetchStrategies } from "@/lib/api/strategy";
import { createBotConfig } from "@/lib/api/botApi";
import { useActiveSetup } from "@/app/providers/SetupProvider";
import { useActiveBot } from "@/app/providers/ActiveBotProvider";
import SetupForm from "@/components/setup/SetupForm";
import StrategyForm from "@/components/strategy/StrategyForm";
import AddBotForm from "@/components/bot/AddBotForm";

export default function AIAssistant({ isOpen, setIsOpen }) {
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const { selectedAsset: globalSymbol } = useAsset();
  const router = useRouter();
  const watchlist = useWatchlist();
  const { openConfirm, showSnackbar } = useModal();
  const { events, loading: eventsLoading, archiveEvent } = useIntelligenceEvents();
  
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(false);
  const [messages, setMessages] = useState([]);
  const [preferences, setPreferences] = useState({});
  const [insight, setInsight] = useState(null);
  const [insightLoading, setInsightLoading] = useState(false);
  const [lastUpdated, setLastUpdated] = useState(null);
  const [activeState, setActiveState] = useState(null);
  
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

  // 🛰️ Active Entities Context (Phase 2 Sync)
  let activeSetup = null;
  let focusedBotId = null;
  let activeBot = null;
  
  try {
    const setupCtx = useActiveSetup();
    activeSetup = setupCtx?.activeSetup;
    focusedBotId = setupCtx?.focusedBotId;
  } catch (e) {
    console.warn("ActiveSetup context not ready:", e);
  }

  try {
    const botCtx = useActiveBot();
    activeBot = botCtx?.activeBot;
  } catch (e) {
    console.warn("ActiveBot context not ready:", e);
  }

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
      page: pathname,
      page_type: pageMap[pathname] || "Unknown",
      symbol: searchParams.get("symbol") || searchParams.get("asset") || globalSymbol || "BTC",
      timeframe: searchParams.get("tf") || searchParams.get("interval") || (pathname.includes("dashboard") || pathname === "/" ? "Weekly" : "Daily"),
      setup_id: activeSetup?.id || activeSetup?.setup_id || null,
      bot_id: activeBot?.id || activeBot?.bot_id || focusedBotId || null,
      strategy_id: activeSetup?.strategy_id || null,
      setup_name: searchParams.get("name") || activeSetup?.name || "No specific setup"
    };
  };

  const context = getContext();

  const getFlowProgress = (state) => {
    if (!state || !state.current_flow || state.current_flow === "none") return null;
    
    const flowSlots = {
      user_onboarding: ["experience_level", "risk_profile", "investment_goals"],
      setup_creation: ["symbol", "setup_type", "dca_frequency"],
      strategy_creation: ["symbol", "setup_type", "base_amount", "entry", "targets", "stop_loss"],
      bot_creation: ["name", "budget_total_eur"],
      macro_analysis_walkthrough: ["symbol"],
      technical_analysis_walkthrough: ["symbol"],
      risk_check: ["symbol", "proposed_size"],
      navigate_to_page: ["target_page"]
    };

    const slots = flowSlots[state.current_flow] || [];
    if (slots.length === 0) return null;

    // Calculate filled slots (only filter keys that are defined in the active flow's slots list!)
    const filledSlots = slots.filter(k => state.slots && state.slots[k] !== undefined && state.slots[k] !== null && state.slots[k] !== "");
    
    // Determine effective total slots (taking conditional parameters into account)
    let totalSlots = slots.length;
    const setupType = state.slots?.setup_type;
    if (state.current_flow === "setup_creation" && setupType === "trade") {
      totalSlots = 2; // symbol, setup_type (no dca_frequency)
    }
    if (state.current_flow === "strategy_creation" && setupType === "dca") {
      totalSlots = 3; // symbol, setup_type, base_amount
    }

    const percentage = Math.min(Math.round((filledSlots.length / totalSlots) * 100), 100);
    return {
      filled: filledSlots.length,
      total: totalSlots,
      percentage,
      flowLabel: state.current_flow.split("_").map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(" ")
    };
  };

  const parseSuggestedActions = (text) => {
    if (!text) return [];
    
    const headerRegex = /(?:Volgende stappen|Suggested actions|Proactieve volgacties):/i;
    const match = text.match(headerRegex);
    if (!match) return [];
    
    const headerIndex = match.index;
    const sectionText = text.substring(headerIndex + match[0].length);
    
    const lines = sectionText.split("\n");
    const suggestions = [];
    
    for (const line of lines) {
      const trimmed = line.trim();
      if (trimmed.startsWith("-") || trimmed.startsWith("*")) {
        const label = trimmed.substring(1).trim();
        if (label) suggestions.push(label);
      } else if (/^\d+\./.test(trimmed)) {
        const label = trimmed.replace(/^\d+\./, "").trim();
        if (label) suggestions.push(label);
      } else if (trimmed.length > 0 && suggestions.length > 0) {
        break;
      }
    }
    return suggestions.slice(0, 4);
  };

  useEffect(() => {
    const handleTrigger = (e) => {
      const { query: queryText, openAssistant } = e.detail || {};
      if (openAssistant) {
        setIsOpen(true);
      }
      if (queryText) {
        handleChat(queryText);
      }
    };

    window.addEventListener("finn-action-trigger", handleTrigger);
    return () => window.removeEventListener("finn-action-trigger", handleTrigger);
  }, [messages, handleChat]);

  useEffect(() => {
    if (isOpen) {
      loadInsight();
      if (Object.keys(preferences).length === 0) {
        getAssistantPreferences().then(res => setPreferences(res.preferences || {}));
      }
    }
  }, [isOpen, pathname, searchParams, globalSymbol]);

  async function loadInsight() {
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
  }

  async function handleActionClick(action) {
    if (!action) return;
    const { type, symbol, params } = action;

    try {
      if (type === "add_to_watchlist") {
        if (symbol && watchlist?.add) {
          await watchlist.add(symbol);
        }
      } else if (type === "remove_from_watchlist") {
        if (symbol && watchlist?.remove) {
          await watchlist.remove(symbol);
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
      } else if (type === "navigate_to_page") {
        if (params?.path) {
          router.push(params.path);
          setIsOpen(false);
        }
      }
    } catch (err) {
      console.error("Action execution failed", err);
    }
  }

  async function handleChat(directQuery, isSilent = false) {
    const activeQuery = directQuery !== undefined ? directQuery : query;
    if (!activeQuery.trim()) return;

    setLoading(true);
    if (!isSilent) setQuery("");
    
    if (!isSilent) {
      setMessages(prev => [...prev, { role: "user", text: activeQuery }]);
    }

    // Append initial empty assistant bubble
    setMessages(prev => [...prev, { 
      role: "assistant", 
      text: "", 
      isComplete: false 
    }]);

    try {
      const cleanHistory = [
        ...messages.map(m => ({ role: m.role, text: m.text })),
        { role: "user", text: activeQuery }
      ];

      await assistantChatStream(
        activeQuery,
        context,
        cleanHistory,
        (token) => {
          // onChunk
          setMessages(prev => {
            const copy = [...prev];
            const lastMsg = copy[copy.length - 1];
            if (lastMsg && lastMsg.role === "assistant") {
              lastMsg.text += token;
            }
            return copy;
          });
        },
        (envelope) => {
          // onEnvelope
          setMessages(prev => {
            const copy = [...prev];
            const lastMsg = copy[copy.length - 1];
            if (lastMsg && lastMsg.role === "assistant") {
              lastMsg.text = envelope.response;
              lastMsg.intent = envelope.intent;
              lastMsg.action = envelope.action;
              lastMsg.draft = envelope.draft;
              lastMsg.reasoning = envelope.reasoning;
              lastMsg.isComplete = true;
            }
            return copy;
          });

          if (envelope.state && envelope.state.status === "collecting" && envelope.state.current_flow !== "none") {
            setActiveState(envelope.state);
          } else {
            setActiveState(null);
          }
        },
        (errorMessage) => {
          // onError
          setMessages(prev => {
            const copy = [...prev];
            const lastMsg = copy[copy.length - 1];
            if (lastMsg && lastMsg.role === "assistant") {
              lastMsg.text = "⚠️ " + errorMessage;
              lastMsg.isError = true;
              lastMsg.isComplete = true;
            }
            return copy;
          });
        }
      );
    } catch (err) {
      setMessages(prev => {
        const copy = [...prev];
        const lastMsg = copy[copy.length - 1];
        if (lastMsg && lastMsg.role === "assistant") {
          lastMsg.text = "⚠️ Failed to retrieve analysis. Please try again.";
          lastMsg.isError = true;
          lastMsg.isComplete = true;
        }
        return copy;
      });
    } finally {
      setLoading(false);
    }
  };

  const handleCancelDraft = (index) => {
    setMessages(prev => prev.map((m, idx) => {
      if (idx === index) {
        return { ...m, draftCanceled: true };
      }
      return m;
    }));
    showSnackbar("Concept geannuleerd", "info");
  };

  const handleDraftSuccess = (index) => {
    setMessages(prev => prev.map((m, idx) => {
      if (idx === index) {
        return { ...m, draftExecuted: true };
      }
      return m;
    }));
  };

  const handleEditDraft = async (draft, onSuccess) => {
    if (draft.type === "setup") {
      try {
        openConfirm({
          title: `Bewerk Setup Concept`,
          tone: "primary",
          confirmText: "Opslaan & Creëren",
          cancelText: "Annuleren",
          description: (
            <div className="space-y-6 pt-4 max-h-[60vh] overflow-y-auto no-scrollbar">
              <SetupForm 
                mode="new"
                initialData={draft.payload}
                onSaved={() => {
                  showSnackbar("Setup succesvol aangemaakt!", "success");
                  onSuccess();
                }}
              />
            </div>
          ),
          onConfirm: () => {
            document.querySelector("#setup-edit-submit")?.click();
          }
        });
      } catch (err) {
        console.error("Failed to load SetupForm", err);
      }
    } else if (draft.type === "strategy") {
      try {
        const setupsList = await fetchSetups();
        openConfirm({
          title: `Bewerk Strategie Concept`,
          tone: "primary",
          confirmText: "Opslaan & Creëren",
          cancelText: "Annuleren",
          description: (
            <div className="space-y-6 pt-4 max-h-[60vh] overflow-y-auto no-scrollbar">
              <StrategyForm 
                setups={setupsList}
                isEdit={false}
                strategy={{
                  name: draft.payload.name,
                  symbol: draft.payload.symbol,
                  setup_type: draft.payload.setup_type,
                  setup_id: setupsList[0]?.id,
                  base_amount: draft.payload.base_amount,
                  entry: draft.payload.entry,
                  targets: draft.payload.targets,
                  stop_loss: draft.payload.stop_loss,
                  execution_mode: draft.payload.execution_mode || "fixed"
                }}
                onSubmit={async (payload) => {
                  await createStrategy(payload);
                  showSnackbar("Strategie succesvol aangemaakt!", "success");
                  onSuccess();
                }}
              />
            </div>
          ),
          onConfirm: () => {
            document.querySelector("#strategy-edit-submit")?.click();
          }
        });
      } catch (err) {
        console.error("Failed to load StrategyForm", err);
      }
    } else if (draft.type === "bot") {
      try {
        const stratList = await fetchStrategies();
        let currentFormVal = {};
        openConfirm({
          title: `Bewerk Bot Concept`,
          tone: "primary",
          confirmText: "Opslaan & Creëren",
          cancelText: "Annuleren",
          description: (
            <div className="space-y-6 pt-4 max-h-[60vh] overflow-y-auto no-scrollbar">
              <AddBotForm 
                strategies={stratList}
                initialData={{
                  name: draft.payload.name,
                  strategy_id: draft.payload.strategy_id || stratList[0]?.id,
                  mode: draft.payload.mode || "manual",
                  is_live: draft.payload.is_live || false,
                  risk_profile: draft.payload.risk_profile || "balanced",
                  base_currency: draft.payload.base_currency || "EUR"
                }}
                onChange={(val) => {
                  currentFormVal = val;
                }}
              />
            </div>
          ),
          onConfirm: async () => {
            const payload = {
              name: currentFormVal.name || draft.payload.name,
              strategy_id: currentFormVal.strategy_id || draft.payload.strategy_id || stratList[0]?.id,
              mode: currentFormVal.mode || draft.payload.mode || "manual",
              is_live: currentFormVal.is_live ?? draft.payload.is_live ?? false,
              risk_profile: currentFormVal.risk_profile || draft.payload.risk_profile || "balanced",
              base_currency: currentFormVal.base_currency || draft.payload.base_currency || "EUR",
              budget_total_eur: draft.payload.budget_total_eur || 500.0,
              budget_daily_limit_eur: draft.payload.budget_daily_limit_eur || 50.0,
              budget_min_order_eur: draft.payload.budget_min_order_eur || 10.0,
              budget_max_order_eur: draft.payload.budget_max_order_eur || 100.0,
              max_asset_exposure_pct: draft.payload.max_asset_exposure_pct || 100.0,
              cadence: draft.payload.cadence || "daily"
            };
            await createBotConfig(payload);
            showSnackbar("Bot succesvol aangemaakt!", "success");
            onSuccess();
          }
        });
      } catch (err) {
        console.error("Failed to load AddBotForm", err);
      }
    }
  };

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, loading, activeState]);

  if (!isOpen) return null;

  return (
    <aside 
      className={`fixed top-0 right-0 h-full bg-card dark:bg-[#0f172a] border-l border-slate-200 dark:border-slate-800 z-[70] shadow-2xl transition-all duration-300 flex flex-col ${
        isOpen ? "translate-x-0" : "translate-x-full"
      } w-full md:w-[400px]`}
    >
      {/* HEADER */}
      <div className="p-4 border-b border-slate-100 dark:border-slate-800 flex items-center justify-between bg-card dark:bg-[#0f172a] relative z-10 shadow-sm flex-shrink-0">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-xl bg-blue-600 flex items-center justify-center text-white shadow-lg shadow-blue-600/30">
             <Bot size={20} />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-sm font-black text-foreground dark:text-slate-100 tracking-tight">FINN</h2>
              <span className="text-[9px] font-black uppercase tracking-widest bg-blue-100 dark:bg-blue-900/40 text-blue-700 dark:text-blue-300 px-1.5 py-0.5 rounded">Chief of Staff</span>
            </div>
            <div className="flex items-center gap-1.5 mt-0.5">
              <div className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
              <span className="text-[10px] font-bold text-secondary dark:text-slate-500 uppercase tracking-widest leading-none">
                {context.page_type} · {context.symbol} · {context.timeframe}
              </span>
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
        {/* SECTION 1 — FINN POSTURE & BRIEFING */}
        <div className="p-5 border-b border-slate-100 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-900/20 space-y-2.5 animate-fade-in">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-1.5">
              <Shield size={12} className="text-blue-600" />
              <span className="text-[10px] font-black text-slate-900 dark:text-white uppercase tracking-widest">Actieve Briefing</span>
            </div>
            <span className="text-[9px] font-bold text-emerald-600 dark:text-emerald-400 bg-emerald-50 dark:bg-emerald-900/20 px-2 py-0.5 rounded-full border border-emerald-200/50 dark:border-emerald-800/50">Defensieve Posture</span>
          </div>
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
                    {stepStatus?.[`has_${pathname.split('/').pop()}`] ? (
                      `Excellent. The ${pathname.split('/').pop()} data stream is now stabilized and streaming high-fidelity intelligence to your cockpit. Return to the Launch Center for the next protocol.`
                    ) : (
                      pathname.includes("market") ? "Market data is required to monitor live price action. Search for BTC and add it to your monitor." :
                      pathname.includes("macro") ? "Macro indicators track global liquidity and dollar strength. Search for DXY and add it to your monitor." :
                      pathname.includes("technical") ? "Technical signals identify price momentum and trends. Search for RSI and add it to your monitor." :
                      pathname.includes("setup") ? "Setups define your specific entry and exit rules. Click the 'New Setup' button to create your first rule-set." :
                      pathname.includes("strategy") ? "The strategy engine builds your AI-driven execution model. Click the 'Generate Strategy' button to finalize your cockpit." :
                      "I will guide you through the 5 steps to activate your system. Once initialized, your dashboard will be fully operational with live data and AI insights."
                    )}
                  </p>
               </div>
            </div>
          ) : (
            <p className="text-xs font-semibold text-slate-800 dark:text-slate-200 leading-relaxed italic border-l-3 border-blue-500 pl-3 py-0.5">
              "{insight?.greeting || `Hallo ${preferences?.first_name || 'Henk'}, alle ${context.symbol} feeds draaien stabiel.`} {getInsightField('bot_insight', 'conclusion') || getInsightField('market_insight', 'conclusion') || "BTC bevindt zich momenteel in een consolidatiefase met verhoogd correctierisico zolang volume achterblijft."}"
            </p>
          )}
        </div>

        {/* SECTION 2 — FINN Live Intelligence Terminal */}
        <div className="p-6 border-b border-slate-100 dark:border-slate-800 bg-white dark:bg-[#0f172a] space-y-4">
          <div className="flex items-center justify-between mb-2">
            <h3 className="text-[10px] font-black text-slate-900 dark:text-white uppercase tracking-widest flex items-center gap-2">
              <Terminal size={14} className="text-blue-600" />
              FINN Live Intelligence Terminal
            </h3>
            <span className="text-[9px] font-bold text-slate-400 dark:text-slate-500 uppercase">Mission Control</span>
          </div>

          <div className="space-y-3 max-h-[280px] overflow-y-auto pr-1 custom-scrollbar">
            {eventsLoading && events.length === 0 ? (
              <div className="py-8 flex flex-col items-center justify-center gap-2 text-center">
                <Sparkles size={16} className="text-blue-500 animate-spin" />
                <span className="text-[10px] font-bold text-slate-400 uppercase tracking-widest">Radar synchroniseren...</span>
              </div>
            ) : events.length === 0 ? (
              <div className="py-8 text-center bg-slate-50 dark:bg-slate-900/50 rounded-2xl border border-slate-100 dark:border-slate-800 p-4">
                <p className="text-[11px] font-bold text-slate-400 dark:text-slate-500 uppercase tracking-widest italic">
                  Geen actieve risico-meldingen. Cockpit draait stabiel.
                </p>
              </div>
            ) : (
              events.map(ev => (
                <div key={ev.id} className="p-3.5 rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-900/50 relative flex flex-col gap-2 transition-all hover:border-blue-500/50">
                  <button 
                    onClick={() => archiveEvent(ev.id)}
                    className="absolute top-2.5 right-2.5 text-slate-400 hover:text-slate-600 dark:hover:text-slate-200"
                  >
                    <X size={14} />
                  </button>
                  <div className="flex items-center gap-2 pr-6">
                    <span className="text-xs font-black text-slate-900 dark:text-slate-100">{ev.title}</span>
                    {ev.symbol && <span className="text-[9px] font-black uppercase tracking-widest bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300 px-1.5 py-0.5 rounded">{ev.symbol}</span>}
                  </div>
                  <p className="text-[11px] text-slate-600 dark:text-slate-400 leading-snug font-medium">
                    {ev.description}
                  </p>
                  <div className="flex pt-1">
                    <button 
                      onClick={() => handleChat(`Wat kan ik concreet doen aan het event: "${ev.title}" voor ${ev.symbol || "portfolio"}?`, true)}
                      className="flex items-center gap-1.5 text-[10px] font-black text-blue-600 dark:text-blue-400 hover:underline tracking-wider uppercase"
                    >
                      <MessageSquare size={12} /> Bespreek met FINN
                    </button>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>

        {/* SECTION 4 — Recent Conversations */}
        <div className="p-6 border-b border-slate-100 dark:border-slate-800 space-y-4 bg-white dark:bg-[#0f172a]">
          <span className="text-[10px] font-black uppercase tracking-widest text-slate-400 dark:text-slate-500 block">Recent Conversations</span>
          <div className="space-y-2">
            {[
              { id: 1, title: "BTC correction review", query: "Vat de laatste BTC correctie en steunniveaus samen" },
              { id: 2, title: "Weekly portfolio report", query: "Analyseer de wekelijkse portfolio prestaties en allocatierisico" },
              { id: 3, title: "SOL setup analysis", query: "Beoordeel de huidige SOL setup en DCA drempelwaarden" },
              { id: 4, title: "Macro contraction discussion", query: "Bespreek de macro contractie en impact op liquiditeit" },
            ].map(conv => (
              <button 
                key={conv.id}
                onClick={() => handleChat(conv.query, true)}
                className="w-full flex items-center justify-between p-3 rounded-xl bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-800 hover:border-blue-600 dark:hover:border-blue-400 hover:shadow-sm transition-all group text-left"
              >
                <div className="flex items-center gap-3 truncate">
                  <MessageSquare size={14} className="text-slate-400 group-hover:text-blue-600 dark:group-hover:text-blue-400 shrink-0" />
                  <span className="text-xs font-bold text-slate-700 dark:text-slate-300 group-hover:text-blue-600 dark:group-hover:text-blue-400 truncate">{conv.title}</span>
                </div>
                <span className="text-[10px] font-bold text-slate-400 group-hover:text-blue-600 dark:group-hover:text-blue-400">→</span>
              </button>
            ))}
          </div>
        </div>

        {/* MESSAGES AREA */}
        <div className="p-6 space-y-6 pb-20">
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
                {m.role === "assistant" && m.isComplete !== false && (() => {
                  const suggestions = parseSuggestedActions(m.text);
                  if (suggestions.length === 0) return null;
                  return (
                    <div className="mt-4 pt-3 border-t border-slate-100/50 dark:border-slate-800/50 flex flex-col gap-2">
                      <span className="text-[9px] font-black uppercase tracking-widest text-slate-400 dark:text-slate-500">Volgende stappen:</span>
                      <div className="flex flex-wrap gap-2">
                        {suggestions.map((s, idx) => (
                          <button
                            key={idx}
                            onClick={() => handleChat(s)}
                            className="flex items-center gap-1.5 px-3 py-2 rounded-xl text-[11px] font-bold bg-white dark:bg-slate-950 hover:bg-blue-50 dark:hover:bg-blue-950/30 text-blue-600 dark:text-blue-400 hover:text-blue-700 border border-slate-100 dark:border-slate-800 hover:border-blue-200 dark:hover:border-blue-900/40 transition-all hover:-translate-y-0.5 active:translate-y-0 hover:shadow-sm text-left"
                          >
                            <Zap size={10} className="text-amber-500" />
                            {s}
                          </button>
                        ))}
                      </div>
                    </div>
                  );
                })()}
                {m.reasoning && m.isComplete !== false && (
                  <ReasoningWidget reasoning={m.reasoning} />
                )}
                {/* Universal Action Card Renderer */}
                {m.isComplete !== false && (() => {
                  const card = (m.draft?.type === "action_card" ? m.draft : null) || (m.action?.type === "action_card" ? m.action : null);
                  if (card) {
                    return (
                      <UniversalActionCard
                        card={card}
                        onCancel={() => handleCancelDraft(i)}
                        onSuccess={() => handleDraftSuccess(i)}
                        handleEditDraft={handleEditDraft}
                      />
                    );
                  }
                  return null;
                })()}
                {m.action && m.action.type !== "action_card" && m.isComplete !== false && (
                  <ActionCard action={m.action} onAction={handleActionClick} />
                )}
                {m.draft && m.draft.type !== "action_card" && !m.draftCanceled && !m.draftExecuted && m.isComplete !== false && (
                  <DraftCard 
                    draft={m.draft} 
                    onCancel={() => handleCancelDraft(i)} 
                    onSuccess={() => handleDraftSuccess(i)}
                    handleEditDraft={handleEditDraft}
                  />
                )}
                {m.draft && m.draftCanceled && m.isComplete !== false && (
                  <div className="mt-3 p-3 bg-slate-100/50 dark:bg-slate-950/20 border border-dashed border-slate-200 dark:border-slate-800/80 rounded-xl text-center text-[10px] text-slate-400 font-bold uppercase tracking-wider">
                    ✕ Concept geannuleerd
                  </div>
                )}
                {m.draft && m.draftExecuted && m.isComplete !== false && (
                  <div className="mt-3 p-3 bg-emerald-500/10 dark:bg-emerald-950/20 border border-emerald-500/30 rounded-xl text-center text-[10px] text-emerald-600 dark:text-emerald-400 font-black uppercase tracking-widest flex items-center justify-center gap-1.5 animate-pulse">
                    ✓ Concept Succesvol Opgeslagen!
                  </div>
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

          {/* LIVE INTERACTIVE CONCEPT CARD */}
          {activeState && activeState.current_flow && activeState.current_flow !== "none" && (() => {
            const flow = activeState.current_flow;
            const slots = activeState.slots || {};
            let shouldShowCard = false;
            
            if (flow === "setup_creation") {
              shouldShowCard = !!(slots.setup_type && slots.market_condition);
            } else if (flow === "strategy_creation") {
              shouldShowCard = !!(slots.setup_type && slots.base_amount);
            } else if (flow === "bot_creation") {
              shouldShowCard = !!slots.budget_total_eur;
            } else {
              shouldShowCard = true;
            }

            if (!shouldShowCard) return null;

            return (
              <div className="flex justify-start animate-in slide-in-from-bottom-3 duration-300">
                <div className="max-w-[90%]">
                  <ConceptCard 
                    state={activeState}
                    onCancel={() => {
                      handleChat("annuleer", false);
                      setActiveState(null);
                    }}
                    onEdit={() => {
                      const mockDraft = {
                        type: activeState.current_flow.split("_")[0],
                        payload: {
                          name: activeState.slots?.name || `${activeState.slots?.symbol || globalSymbol} Concept`,
                          symbol: activeState.slots?.symbol || globalSymbol,
                          setup_type: activeState.slots?.setup_type || "trade",
                          ...activeState.slots
                        }
                      };
                      handleEditDraft(mockDraft, async () => {
                        setActiveState(null);
                        await handleChat("ik heb hem zojuist opgeslagen", true);
                      });
                    }}
                    onFinalize={() => handleChat("maak de setup")}
                    onUpdateSlots={(newSlots) => {
                      if (newSlots.setup_type) handleChat(newSlots.setup_type, true);
                      if (newSlots.dca_frequency) handleChat(newSlots.dca_frequency, true);
                    }}
                  />
                </div>
              </div>
            );
          })()}

          {loading && (
            <ChatSkeleton />
          )}
          <div ref={messagesEndRef} />
        </div>
      </div>

      {/* INPUT AREA */}
      <div className="p-6 bg-card dark:bg-[#0f172a] border-t border-slate-100 dark:border-slate-800 shadow-[0_-10px_20px_-10px_rgba(0,0,0,0.05)] relative z-10 flex-shrink-0">
        {pathname?.includes("/admin") && activeState && activeState.current_flow && activeState.current_flow !== "none" && (() => {
          const progress = getFlowProgress(activeState);
          if (!progress) return null;
          const activeStep = Math.min(progress.filled + 1, progress.total);
          return (
            <div className="mb-4 p-4 bg-slate-50 dark:bg-slate-900/50 border border-slate-100 dark:border-slate-800/80 rounded-2xl flex flex-col gap-2.5">
              <div className="flex items-center justify-between text-xs font-medium text-slate-700 dark:text-slate-300">
                <span className="font-semibold">{progress.flowLabel === "Setup Creation" ? "Setup Wizard" : progress.flowLabel}</span>
                <span className="text-slate-400 dark:text-slate-500">Stap {activeStep} van {progress.total}</span>
              </div>
              <div className="w-full h-1 bg-slate-100 dark:bg-slate-900 rounded-full overflow-hidden">
                <div 
                  className="h-full bg-blue-600 dark:bg-blue-500 rounded-full transition-all duration-500 ease-out"
                  style={{ width: `${progress.percentage}%` }}
                />
              </div>
            </div>
          );
        })()}
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

function UniversalActionCard({ card, onCancel, onSuccess, handleEditDraft }) {
  const { openConfirm, showSnackbar } = useModal();
  const [status, setStatus] = useState("pending"); // pending, executing, success, error, canceled
  const [errorMessage, setErrorMessage] = useState("");

  const cardType = card.card_type || "";
  const payload = card.payload || {};
  const isDraft = cardType.endsWith("_draft_card");
  const baseType = cardType.replace("_draft_card", "").replace("_card", ""); // setup, strategy, bot, add_to_watchlist, remove_from_watchlist etc.

  const handleApprove = async () => {
    setStatus("executing");
    setErrorMessage("");
    try {
      const res = await executePendingAction(card.action_id);
      if (res && res.error) {
        throw new Error(res.error || "Execution failed.");
      }
      setStatus("success");
      showSnackbar("✓ Actie succesvol uitgevoerd!", "success");
      if (onSuccess) onSuccess();
    } catch (err) {
      console.error("Action execution failed:", err);
      setStatus("error");
      setErrorMessage(err.message || "Fout bij het uitvoeren van deze actie.");
      showSnackbar("Uitvoering mislukt", "danger");
    }
  };

  const handleCancelClick = () => {
    setStatus("canceled");
    if (onCancel) onCancel();
  };

  const handleEditClick = () => {
    if (!handleEditDraft) return;
    const draftType = cardType.replace("_draft_card", ""); // setup, strategy, bot
    const mockDraft = {
      type: draftType,
      payload: payload
    };
    handleEditDraft(mockDraft, () => {
      setStatus("success");
      if (onSuccess) onSuccess();
    });
  };

  // --- Theme styling ---
  const getAccentGradient = () => {
    if (baseType === "setup") return "from-amber-500 to-yellow-400";
    if (baseType === "strategy") return "from-blue-500 to-indigo-500";
    if (baseType === "bot") return "from-emerald-500 to-teal-500";
    return "from-violet-500 to-fuchsia-500";
  };

  const getRiskBadge = () => {
    if (baseType === "setup") {
      const isDca = payload.setup_type === "dca";
      return isDca 
        ? { text: "Laag Risico", class: "bg-emerald-500/10 text-emerald-500 dark:text-emerald-400 border-emerald-500/20" }
        : { text: "Medium Risico", class: "bg-amber-500/10 text-amber-500 dark:text-amber-400 border-amber-500/20" };
    }
    if (baseType === "strategy") {
      const sl = parseFloat(payload.stop_loss);
      const isHighSl = sl && sl > 12;
      return isHighSl
        ? { text: "Hoog Risico", class: "bg-rose-500/10 text-rose-500 dark:text-rose-400 border-rose-500/20" }
        : { text: "Medium Risico", class: "bg-amber-500/10 text-amber-500 dark:text-amber-400 border-amber-500/20" };
    }
    if (baseType === "bot") {
      const risk = payload.risk_profile || "balanced";
      if (risk === "aggressive") return { text: "Actief Risico", class: "bg-rose-500/10 text-rose-500 dark:text-rose-400 border-rose-500/20" };
      if (risk === "conservative") return { text: "Behoedzaam", class: "bg-emerald-500/10 text-emerald-500 dark:text-emerald-400 border-emerald-500/20" };
      return { text: "Gebalanceerd", class: "bg-blue-500/10 text-blue-500 dark:text-blue-400 border-blue-500/20" };
    }
    return { text: "Operationeel", class: "bg-violet-500/10 text-violet-500 dark:text-violet-400 border-violet-500/20" };
  };

  const riskBadge = getRiskBadge();

  if (status === "canceled") {
    return (
      <div className="mt-4 p-4 bg-slate-100/50 dark:bg-slate-950/20 border border-dashed border-slate-200 dark:border-slate-800/80 rounded-2xl text-center text-[10px] text-slate-400 dark:text-slate-500 font-bold uppercase tracking-wider animate-in fade-in duration-200">
        ✕ Actie Geannuleerd
      </div>
    );
  }

  if (status === "success") {
    return (
      <div className="mt-4 p-5 bg-emerald-500/10 dark:bg-emerald-950/20 border border-emerald-500/30 rounded-2xl text-center text-xs text-emerald-600 dark:text-emerald-400 font-black uppercase tracking-widest flex flex-col items-center justify-center gap-2 animate-in fade-in zoom-in-95 duration-300">
        <div className="w-10 h-10 rounded-full bg-emerald-500 text-white flex items-center justify-center text-lg font-black shadow-lg shadow-emerald-500/20 animate-bounce">
          ✓
        </div>
        <span>Actie Succesvol Uitgevoerd!</span>
      </div>
    );
  }

  return (
    <div className="mt-4 overflow-hidden rounded-2xl border border-slate-100 dark:border-slate-800 bg-white dark:bg-slate-900/60 shadow-xl shadow-slate-100/10 dark:shadow-none animate-in fade-in slide-in-from-bottom-4 duration-300">
      {/* CARD ACCENT LINE */}
      <div className={`h-1.5 w-full bg-gradient-to-r ${getAccentGradient()}`} />

      <div className="p-4 space-y-4">
        {/* CARD TITLE & RISK BADGE */}
        <div className="flex items-start justify-between">
          <div className="space-y-0.5">
            <span className="text-[9px] font-black uppercase tracking-widest text-slate-400 dark:text-slate-500">
              AI Command Center
            </span>
            <h4 className="text-xs font-black text-foreground dark:text-slate-200 tracking-tight leading-snug">
              {payload.name || (baseType === "add_to_watchlist" ? `Watchlist Activatie: ${payload.symbol}` : baseType === "remove_from_watchlist" ? `Watchlist Deactivatie: ${payload.symbol}` : `${payload.symbol || "Asset"} Concept`)}
            </h4>
          </div>
          <div className="flex flex-col items-end gap-1.5">
            <span className={`text-[8px] font-black uppercase tracking-wider px-2 py-0.5 rounded-md shadow-sm text-white bg-gradient-to-r ${getAccentGradient()}`}>
              {baseType} {isDraft ? "draft" : "actie"}
            </span>
            <span className={`text-[8px] font-black uppercase px-1.5 py-0.5 rounded border ${riskBadge.class}`}>
              {riskBadge.text}
            </span>
          </div>
        </div>

        {/* METADATA CONTENT AREA */}
        <div className="rounded-xl bg-slate-50 dark:bg-slate-950 p-3.5 border border-slate-100 dark:border-slate-800/80 space-y-2.5 shadow-inner">
          {baseType === "setup" && (
            <div className="grid grid-cols-2 gap-x-4 gap-y-2 text-[11px] font-bold text-slate-600 dark:text-slate-300">
              <div className="flex flex-col">
                <span className="text-[8px] font-black uppercase tracking-widest text-slate-400 dark:text-slate-500 mb-0.5">Asset</span>
                <span className="font-mono text-xs text-foreground dark:text-slate-200">{payload.symbol || "SOL"}</span>
              </div>
              <div className="flex flex-col">
                <span className="text-[8px] font-black uppercase tracking-widest text-slate-400 dark:text-slate-500 mb-0.5">Setup Type</span>
                <span className="uppercase text-xs text-foreground dark:text-slate-200">{payload.setup_type || "dca"}</span>
              </div>
              {payload.setup_type === "dca" && (
                <div className="flex flex-col col-span-2 border-t border-slate-100 dark:border-slate-800 pt-2">
                  <span className="text-[8px] font-black uppercase tracking-widest text-slate-400 dark:text-slate-500 mb-0.5">DCA Parameters</span>
                  <span className="text-xs text-foreground dark:text-slate-200">
                    {payload.dca_frequency || "weekly"} {payload.dca_day ? `op ${payload.dca_day}` : ""}
                  </span>
                </div>
              )}
              {(payload.min_macro_score !== undefined || payload.min_technical_score !== undefined) && (
                <div className="flex flex-col col-span-2 border-t border-slate-100 dark:border-slate-800 pt-2 space-y-1">
                  <span className="text-[8px] font-black uppercase tracking-widest text-slate-400 dark:text-slate-500">Score Drempelwaarden</span>
                  <div className="grid grid-cols-3 gap-2 mt-1">
                    <div className="bg-white dark:bg-slate-900 rounded-lg p-1.5 text-center border border-slate-100 dark:border-slate-800">
                      <div className="text-[7px] font-black uppercase text-slate-400 dark:text-slate-500">Macro</div>
                      <div className="text-[10px] font-mono font-black text-blue-500">{payload.min_macro_score ?? 30}-{payload.max_macro_score ?? 70}</div>
                    </div>
                    <div className="bg-white dark:bg-slate-900 rounded-lg p-1.5 text-center border border-slate-100 dark:border-slate-800">
                      <div className="text-[7px] font-black uppercase text-slate-400 dark:text-slate-500">Tech</div>
                      <div className="text-[10px] font-mono font-black text-amber-500">{payload.min_technical_score ?? 40}-{payload.max_technical_score ?? 80}</div>
                    </div>
                    <div className="bg-white dark:bg-slate-900 rounded-lg p-1.5 text-center border border-slate-100 dark:border-slate-800">
                      <div className="text-[7px] font-black uppercase text-slate-400 dark:text-slate-500">Market</div>
                      <div className="text-[10px] font-mono font-black text-emerald-500">{payload.min_market_score ?? 20}-{payload.max_market_score ?? 60}</div>
                    </div>
                  </div>
                </div>
              )}
            </div>
          )}

          {baseType === "strategy" && (
            <div className="grid grid-cols-2 gap-x-4 gap-y-2 text-[11px] font-bold text-slate-600 dark:text-slate-300">
              <div className="flex flex-col">
                <span className="text-[8px] font-black uppercase tracking-widest text-slate-400 dark:text-slate-500 mb-0.5">Asset</span>
                <span className="font-mono text-xs text-foreground dark:text-slate-200">{payload.symbol || "SOL"}</span>
              </div>
              <div className="flex flex-col">
                <span className="text-[8px] font-black uppercase tracking-widest text-slate-400 dark:text-slate-500 mb-0.5">Base Budget</span>
                <span className="text-xs text-foreground dark:text-slate-200">€{payload.base_amount || 100.0}</span>
              </div>
              {payload.setup_type === "trade" ? (
                <>
                  <div className="flex flex-col border-t border-slate-100 dark:border-slate-800 pt-2">
                    <span className="text-[8px] font-black uppercase tracking-widest text-slate-400 dark:text-slate-500 mb-0.5">Entry Target</span>
                    <span className="text-xs text-foreground dark:text-slate-200">€{payload.entry}</span>
                  </div>
                  <div className="flex flex-col border-t border-slate-100 dark:border-slate-800 pt-2">
                    <span className="text-[8px] font-black uppercase tracking-widest text-slate-400 dark:text-slate-500 mb-0.5">Stop Loss</span>
                    <span className="text-xs text-rose-500">€{payload.stop_loss}</span>
                  </div>
                  <div className="flex flex-col col-span-2 border-t border-slate-100 dark:border-slate-800 pt-2">
                    <span className="text-[8px] font-black uppercase tracking-widest text-slate-400 dark:text-slate-500 mb-0.5">Take Profit Targets</span>
                    <span className="text-xs text-emerald-500 font-mono">
                      {Array.isArray(payload.targets) ? payload.targets.map(t => `€${t}`).join(" · ") : `€${payload.targets}`}
                    </span>
                  </div>
                </>
              ) : (
                <div className="flex flex-col col-span-2 border-t border-slate-100 dark:border-slate-800 pt-2">
                  <span className="text-[8px] font-black uppercase tracking-widest text-slate-400 dark:text-slate-500 mb-0.5">DCA Multiplier Mode</span>
                  <span className="text-xs text-foreground dark:text-slate-200 uppercase font-mono">{payload.execution_mode || "fixed"}</span>
                </div>
              )}
            </div>
          )}

          {baseType === "bot" && (
            <div className="grid grid-cols-2 gap-x-4 gap-y-2 text-[11px] font-bold text-slate-600 dark:text-slate-300">
              <div className="flex flex-col">
                <span className="text-[8px] font-black uppercase tracking-widest text-slate-400 dark:text-slate-500 mb-0.5">Safety Profile</span>
                <span className="text-xs text-foreground dark:text-slate-200 capitalize">{payload.risk_profile || "balanced"}</span>
              </div>
              <div className="flex flex-col">
                <span className="text-[8px] font-black uppercase tracking-widest text-slate-400 dark:text-slate-500 mb-0.5">Budget</span>
                <span className="text-xs text-foreground dark:text-slate-200">€{payload.budget_total_eur || 500.0}</span>
              </div>
              <div className="flex flex-col border-t border-slate-100 dark:border-slate-800 pt-2">
                <span className="text-[8px] font-black uppercase tracking-widest text-slate-400 dark:text-slate-500 mb-0.5">Environment</span>
                <span className="text-xs text-foreground dark:text-slate-200">
                  {payload.is_live ? "⚡ LIVE Real" : "📝 PAPER Sandbox"}
                </span>
              </div>
              <div className="flex flex-col border-t border-slate-100 dark:border-slate-800 pt-2">
                <span className="text-[8px] font-black uppercase tracking-widest text-slate-400 dark:text-slate-500 mb-0.5">Mode</span>
                <span className="text-xs text-foreground dark:text-slate-200 capitalize">{payload.mode || "manual"}</span>
              </div>
            </div>
          )}

          {baseType.includes("watchlist") && (
            <div className="text-[11px] font-bold text-slate-600 dark:text-slate-300 flex items-center gap-3">
              <Activity size={18} className="text-violet-500 animate-pulse" />
              <div className="flex flex-col">
                <span className="text-[8px] font-black uppercase tracking-widest text-slate-400 dark:text-slate-500 mb-0.5">Doel Asset</span>
                <span className="font-mono text-xs text-foreground dark:text-slate-200">{payload.symbol}</span>
              </div>
            </div>
          )}

          {!["setup", "strategy", "bot"].includes(baseType) && !baseType.includes("watchlist") && (
            <div className="text-xs text-slate-500 dark:text-slate-400 font-bold leading-relaxed">
              {payload.description || "Geen gedetailleerde parameters beschikbaar."}
            </div>
          )}
        </div>

        {/* INLINE ERROR DISPLAY */}
        {status === "error" && (
          <div className="p-3 bg-rose-500/10 border border-rose-500/20 rounded-xl text-[10px] text-rose-500 font-black tracking-wide leading-snug animate-in fade-in slide-in-from-top-1 duration-200">
            ⚠ {errorMessage}
          </div>
        )}

        {/* CONTROL BUTTONS WITH OPTIMISTIC LOADING */}
        <div className="grid grid-cols-3 gap-2">
          <button
            onClick={handleApprove}
            disabled={status === "executing"}
            className={`py-2 px-3 rounded-xl text-[10px] font-black uppercase tracking-wider text-white transition-all shadow-md flex items-center justify-center gap-1.5 bg-gradient-to-r ${getAccentGradient()} hover:opacity-90 active:scale-95 disabled:opacity-50`}
          >
            {status === "executing" ? (
              <>
                <Loader2 size={12} className="animate-spin" />
                <span>Laden...</span>
              </>
            ) : (
              "APPROVE"
            )}
          </button>

          {isDraft && handleEditDraft ? (
            <button
              onClick={handleEditClick}
              disabled={status === "executing"}
              className="py-2 px-3 rounded-xl text-[10px] font-black uppercase tracking-wider border-2 border-slate-200 dark:border-slate-700 hover:border-slate-300 dark:hover:border-slate-600 text-slate-600 dark:text-slate-300 bg-white dark:bg-slate-950 transition-all hover:bg-slate-50 active:scale-95 disabled:opacity-50 flex items-center justify-center"
            >
              EDIT
            </button>
          ) : (
            <div className="col-span-1" /> // Placeholder to maintain exact symmetrical grid alignment
          )}

          <button
            onClick={handleCancelClick}
            disabled={status === "executing"}
            className="py-2 px-3 rounded-xl text-[10px] font-black uppercase tracking-wider border-2 border-slate-200 dark:border-slate-700 hover:border-red-500 hover:text-red-500 dark:hover:border-red-500/30 text-slate-500 dark:text-slate-400 bg-white dark:bg-slate-950 transition-all hover:bg-slate-50 active:scale-95 disabled:opacity-50 flex items-center justify-center"
          >
            CANCEL
          </button>
        </div>
      </div>
    </div>
  );
}

function ActionCard({ action, onAction }) {
  const [loading, setLoading] = useState(false);
  const [success, setSuccess] = useState(false);
  
  // State for bundle execution
  const [steps, setSteps] = useState([]);
  const [bundleStatus, setBundleStatus] = useState("idle"); // idle, running, success, failed

  useEffect(() => {
    if (action?.type === "bundle" && action?.actions) {
      setSteps(
        action.actions.map((act, index) => ({
          ...act,
          id: index,
          status: "pending", // pending, processing, success, failed
        }))
      );
    }
  }, [action]);

  const handleSingleClick = async () => {
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

  const handleBundleClick = async () => {
    setBundleStatus("running");
    
    let hasError = false;
    const updatedSteps = [...steps];

    for (let i = 0; i < updatedSteps.length; i++) {
      // Update state to processing for the current step
      updatedSteps[i] = { ...updatedSteps[i], status: "processing" };
      setSteps([...updatedSteps]);

      try {
        // Execute the action via the callback
        await onAction(updatedSteps[i]);
        
        // Mark as success
        updatedSteps[i] = { ...updatedSteps[i], status: "success" };
        setSteps([...updatedSteps]);
      } catch (err) {
        console.error(`Step ${i} failed:`, err);
        updatedSteps[i] = { ...updatedSteps[i], status: "failed" };
        setSteps([...updatedSteps]);
        hasError = true;
        break; // Stop sequential execution upon error
      }
      
      // Short delay for visual polish & sequential feel
      await new Promise(resolve => setTimeout(resolve, 600));
    }

    if (hasError) {
      setBundleStatus("failed");
    } else {
      setBundleStatus("success");
    }
  };

  const getActionLabel = (act = action) => {
    switch (act.type) {
      case "add_to_watchlist": return `Add ${act.symbol || ""} to Watchlist`;
      case "remove_from_watchlist": return `Remove ${act.symbol || ""} from Watchlist`;
      case "open_setup_page": return `Configure Setup for ${act.symbol || ""}`;
      case "generate_strategy": return `Generate ${act.symbol || ""} Strategy`;
      case "open_bot_draft": return `Deploy ${act.symbol || ""} Paper Bot`;
      case "navigate_to_page": return `Ga naar ${act.params?.label || "Pagina"}`;
      default: return "Execute Action";
    }
  };

  const getActionDescription = (act = action) => {
    switch (act.type) {
      case "add_to_watchlist": return `Add ${act.symbol || ""} to the live tracking engine.`;
      case "remove_from_watchlist": return `Remove ${act.symbol || ""} from the live tracking engine.`;
      case "open_setup_page": return `Open setups tab to create custom macro rules for ${act.symbol || ""}.`;
      case "generate_strategy": return `Use AI to build a customized algorithmic strategy for ${act.symbol || ""}.`;
      case "open_bot_draft": return `Open bot configuration modal with recommended pre-filled parameters.`;
      case "navigate_to_page": return `Navigeer direct naar de ${act.params?.label || "pagina"} in het dashboard.`;
      default: return "";
    }
  };

  // --- RENDERING MULTI-ACTION BUNDLE ---
  if (action?.type === "bundle") {
    return (
      <div className="mt-3 p-5 bg-gradient-to-br from-blue-600/5 to-indigo-600/5 dark:from-blue-950/10 dark:to-indigo-950/10 border-2 border-blue-200/50 dark:border-blue-900/40 rounded-2xl flex flex-col gap-4 shadow-xl shadow-blue-500/5">
        <div className="flex items-center justify-between border-b border-blue-100/30 dark:border-blue-900/20 pb-2.5">
          <div>
            <h4 className="text-[10px] font-black uppercase tracking-[0.2em] text-blue-600 dark:text-blue-400 flex items-center gap-2">
              <span className="flex h-2 w-2 relative">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-blue-400 opacity-75"></span>
                <span className="relative inline-flex rounded-full h-2 w-2 bg-blue-500"></span>
              </span>
              🛒 AI Operator Checkout
            </h4>
            <p className="text-[11px] text-slate-500 dark:text-slate-400 font-bold mt-1">
              Approve and deploy the suggested pipeline
            </p>
          </div>
        </div>

        {/* Action Steps List */}
        <div className="space-y-3">
          {steps.map((step, idx) => (
            <div 
              key={step.id} 
              className={`flex items-start gap-3 p-3 rounded-xl border transition-all ${
                step.status === "processing" 
                  ? "bg-blue-50/50 dark:bg-blue-950/30 border-blue-300 dark:border-blue-800 shadow-sm"
                  : step.status === "success"
                    ? "bg-emerald-50/20 dark:bg-emerald-950/10 border-emerald-500/30 dark:border-emerald-500/20"
                    : step.status === "failed"
                      ? "bg-rose-50/20 dark:bg-rose-950/10 border-rose-500/30 dark:border-rose-500/20"
                      : "bg-white/50 dark:bg-slate-900/40 border-slate-100 dark:border-slate-800"
              }`}
            >
              {/* Step Number / Status Indicator */}
              <div className="flex-shrink-0 mt-0.5">
                {step.status === "pending" && (
                  <div className="w-5 h-5 rounded-full border-2 border-slate-200 dark:border-slate-700 flex items-center justify-center text-[9px] font-black text-slate-400 dark:text-slate-500">
                    {idx + 1}
                  </div>
                )}
                {step.status === "processing" && (
                  <div className="w-5 h-5 flex items-center justify-center text-blue-500">
                    <Loader2 size={16} className="animate-spin" />
                  </div>
                )}
                {step.status === "success" && (
                  <div className="w-5 h-5 rounded-full bg-emerald-500 dark:bg-emerald-600 flex items-center justify-center text-white text-[10px] font-black transition-all duration-300 scale-100">
                    ✓
                  </div>
                )}
                {step.status === "failed" && (
                  <div className="w-5 h-5 rounded-full bg-rose-500 dark:bg-rose-600 flex items-center justify-center text-white text-[10px] font-black">
                    !
                  </div>
                )}
              </div>

              {/* Step Info */}
              <div className="flex-1">
                <span className="text-xs font-black text-foreground dark:text-slate-200 block leading-tight">
                  {step.description || getActionLabel(step)}
                </span>
                <span className="text-[10px] text-slate-400 dark:text-slate-500 font-medium block mt-0.5">
                  {getActionDescription(step)}
                </span>
              </div>
            </div>
          ))}
        </div>

        {/* Execution Trigger */}
        <button 
          onClick={handleBundleClick}
          disabled={bundleStatus === "running" || bundleStatus === "success"}
          className={`w-full py-3 rounded-xl text-[10px] font-black uppercase tracking-widest text-white transition-all shadow-lg active:scale-95 ${
            bundleStatus === "success" 
              ? "bg-emerald-600 shadow-emerald-600/15 cursor-default" 
              : bundleStatus === "failed"
                ? "bg-rose-600 shadow-rose-600/15"
                : "bg-blue-600 hover:bg-blue-700 shadow-blue-600/15"
          }`}
        >
          {bundleStatus === "running" 
            ? "Executing Pipeline..." 
            : bundleStatus === "success" 
              ? "✓ Pipeline Deployed Successfully" 
              : bundleStatus === "failed"
                ? "Retry Pipeline"
                : `Confirm & Deploy (${steps.length} Actions)`}
        </button>
      </div>
    );
  }

  // --- RENDERING SINGLE ACTION ---
  return (
    <div className="mt-3 p-4 bg-blue-100/10 dark:bg-blue-950/20 border border-blue-200/50 dark:border-blue-900/40 rounded-2xl flex flex-col gap-3">
      <div>
        <h4 className="text-[10px] font-black uppercase tracking-[0.15em] text-blue-600 dark:text-blue-400">Proposed Action</h4>
        <p className="text-[11px] text-slate-500 dark:text-slate-400 font-medium mt-1 leading-snug">{getActionDescription()}</p>
      </div>
      
      <button 
        onClick={handleSingleClick}
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

function DraftCard({ draft, onCancel, onSuccess, handleEditDraft }) {
  const { openConfirm, showSnackbar } = useModal();
  const [approving, setApproving] = useState(false);

  const handleApprove = async () => {
    setApproving(true);
    try {
      if (draft.type === "setup") {
        await saveNewSetup(draft.payload);
        showSnackbar("Concept setup succesvol goedgekeurd!", "success");
        onSuccess();
      } else if (draft.type === "strategy") {
        const setups = await fetchSetups();
        const matching = setups.filter(s => s.symbol?.toUpperCase() === draft.payload.symbol?.toUpperCase());
        if (matching.length === 0) {
          showSnackbar(`Geen actieve setup gevonden voor ${draft.payload.symbol}. Maak eerst een setup concept aan.`, "danger");
          setApproving(false);
          return;
        }
        const payload = {
          ...draft.payload,
          setup_id: matching[0].id
        };
        await createStrategy(payload);
        showSnackbar("Concept strategie succesvol goedgekeurd!", "success");
        onSuccess();
      } else if (draft.type === "bot") {
        const strategies = await fetchStrategies();
        const matching = strategies.filter(s => s.symbol?.toUpperCase() === draft.payload.name?.split(' ')[0]?.toUpperCase() || s.name?.toLowerCase().includes(draft.payload.name?.toLowerCase()));
        let stratId = matching[0]?.id;
        if (!stratId && strategies.length > 0) {
          stratId = strategies[0].id;
        }
        if (!stratId) {
          showSnackbar(`Geen actieve strategie gevonden. Maak eerst een strategie concept aan.`, "danger");
          setApproving(false);
          return;
        }
        const payload = {
          ...draft.payload,
          strategy_id: stratId
        };
        await createBotConfig(payload);
        showSnackbar("Concept bot succesvol goedgekeurd!", "success");
        onSuccess();
      }
    } catch (err) {
      console.error(err);
      showSnackbar(`Fout bij goedkeuren van ${draft.type} concept.`, "danger");
    } finally {
      setApproving(false);
    }
  };

  const handleEditClick = () => {
    handleEditDraft(draft, onSuccess);
  };

  const getAccentGradient = () => {
    if (draft.type === "setup") return "from-amber-500 to-yellow-400";
    if (draft.type === "strategy") return "from-blue-500 to-indigo-500";
    return "from-emerald-500 to-teal-500";
  };

  return (
    <div className="mt-4 overflow-hidden rounded-2xl border border-slate-100 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-900/60 shadow-xl shadow-slate-100/10 dark:shadow-none animate-in fade-in duration-300">
      {/* CARD HEADER */}
      <div className={`h-1.5 w-full bg-gradient-to-r ${getAccentGradient()}`} />
      
      <div className="p-4 space-y-4">
        {/* TITLE & BADGE */}
        <div className="flex items-start justify-between">
          <div className="space-y-0.5">
            <span className="text-[9px] font-black uppercase tracking-widest text-slate-400 dark:text-slate-500">
              AI Concept Operator
            </span>
            <h4 className="text-xs font-black text-foreground dark:text-slate-200 tracking-tight leading-snug">
              {draft.payload.name || "Nieuw Concept"}
            </h4>
          </div>
          <span className={`text-[8px] font-black uppercase tracking-wider px-2 py-0.5 rounded-md shadow-sm text-white bg-gradient-to-r ${getAccentGradient()}`}>
            {draft.type}
          </span>
        </div>

        {/* METADATA RENDER */}
        <div className="rounded-xl bg-white dark:bg-slate-950 p-3.5 border border-slate-100 dark:border-slate-800/80 space-y-2.5 shadow-sm">
          {draft.type === "setup" && (
            <div className="grid grid-cols-2 gap-x-4 gap-y-2 text-[11px] font-bold text-slate-600 dark:text-slate-300">
              <div className="flex flex-col">
                <span className="text-[8px] font-black uppercase tracking-widest text-slate-400 dark:text-slate-500 mb-0.5">Asset</span>
                <span className="font-mono text-xs text-foreground dark:text-slate-200">{draft.payload.symbol || "SOL"}</span>
              </div>
              <div className="flex flex-col">
                <span className="text-[8px] font-black uppercase tracking-widest text-slate-400 dark:text-slate-500 mb-0.5">Setup Type</span>
                <span className="uppercase text-xs text-foreground dark:text-slate-200">{draft.payload.setup_type || "dca"}</span>
              </div>
              {draft.payload.setup_type === "dca" && (
                <div className="flex flex-col col-span-2 border-t border-slate-50 dark:border-slate-800 pt-2">
                  <span className="text-[8px] font-black uppercase tracking-widest text-slate-400 dark:text-slate-500 mb-0.5">DCA Parameters</span>
                  <span className="text-xs text-foreground dark:text-slate-200">
                    {draft.payload.dca_frequency || "weekly"} {draft.payload.dca_day ? `op ${draft.payload.dca_day}` : ""}
                  </span>
                </div>
              )}
              <div className="flex flex-col col-span-2 border-t border-slate-50 dark:border-slate-800 pt-2 space-y-1">
                <span className="text-[8px] font-black uppercase tracking-widest text-slate-400 dark:text-slate-500">Score Drempelwaarden</span>
                <div className="grid grid-cols-3 gap-2 mt-1">
                  <div className="bg-slate-50 dark:bg-slate-900 rounded-lg p-1.5 text-center">
                    <div className="text-[7px] font-black uppercase text-slate-400 dark:text-slate-500">Macro</div>
                    <div className="text-[10px] font-mono font-black text-blue-500">{draft.payload.min_macro_score ?? 30}-{draft.payload.max_macro_score ?? 70}</div>
                  </div>
                  <div className="bg-slate-50 dark:bg-slate-900 rounded-lg p-1.5 text-center">
                    <div className="text-[7px] font-black uppercase text-slate-400 dark:text-slate-500">Tech</div>
                    <div className="text-[10px] font-mono font-black text-amber-500">{draft.payload.min_technical_score ?? 40}-{draft.payload.max_technical_score ?? 80}</div>
                  </div>
                  <div className="bg-slate-50 dark:bg-slate-900 rounded-lg p-1.5 text-center">
                    <div className="text-[7px] font-black uppercase text-slate-400 dark:text-slate-500">Market</div>
                    <div className="text-[10px] font-mono font-black text-emerald-500">{draft.payload.min_market_score ?? 20}-{draft.payload.max_market_score ?? 60}</div>
                  </div>
                </div>
              </div>
            </div>
          )}

          {draft.type === "strategy" && (
            <div className="grid grid-cols-2 gap-x-4 gap-y-2 text-[11px] font-bold text-slate-600 dark:text-slate-300">
              <div className="flex flex-col">
                <span className="text-[8px] font-black uppercase tracking-widest text-slate-400 dark:text-slate-500 mb-0.5">Asset</span>
                <span className="font-mono text-xs text-foreground dark:text-slate-200">{draft.payload.symbol || "SOL"}</span>
              </div>
              <div className="flex flex-col">
                <span className="text-[8px] font-black uppercase tracking-widest text-slate-400 dark:text-slate-500 mb-0.5">Base Budget</span>
                <span className="text-xs text-foreground dark:text-slate-200">€{draft.payload.base_amount || 100.0}</span>
              </div>
              {draft.payload.setup_type === "trade" ? (
                <>
                  <div className="flex flex-col border-t border-slate-50 dark:border-slate-800 pt-2">
                    <span className="text-[8px] font-black uppercase tracking-widest text-slate-400 dark:text-slate-500 mb-0.5">Entry Target</span>
                    <span className="text-xs text-foreground dark:text-slate-200">€{draft.payload.entry}</span>
                  </div>
                  <div className="flex flex-col border-t border-slate-50 dark:border-slate-800 pt-2">
                    <span className="text-[8px] font-black uppercase tracking-widest text-slate-400 dark:text-slate-500 mb-0.5">Stop Loss</span>
                    <span className="text-xs text-rose-500">€{draft.payload.stop_loss}</span>
                  </div>
                  <div className="flex flex-col col-span-2 border-t border-slate-50 dark:border-slate-800 pt-2">
                    <span className="text-[8px] font-black uppercase tracking-widest text-slate-400 dark:text-slate-500 mb-0.5">Take Profit Targets</span>
                    <span className="text-xs text-emerald-500 font-mono">
                      {Array.isArray(draft.payload.targets) ? draft.payload.targets.map(t => `€${t}`).join(" · ") : `€${draft.payload.targets}`}
                    </span>
                  </div>
                </>
              ) : (
                <div className="flex flex-col col-span-2 border-t border-slate-50 dark:border-slate-800 pt-2">
                  <span className="text-[8px] font-black uppercase tracking-widest text-slate-400 dark:text-slate-500 mb-0.5">DCA Multiplier Mode</span>
                  <span className="text-xs text-foreground dark:text-slate-200 uppercase font-mono">{draft.payload.execution_mode || "fixed"}</span>
                </div>
              )}
            </div>
          )}

          {draft.type === "bot" && (
            <div className="grid grid-cols-2 gap-x-4 gap-y-2 text-[11px] font-bold text-slate-600 dark:text-slate-300">
              <div className="flex flex-col">
                <span className="text-[8px] font-black uppercase tracking-widest text-slate-400 dark:text-slate-500 mb-0.5">Safety Profile</span>
                <span className="text-xs text-foreground dark:text-slate-200 capitalize">{draft.payload.risk_profile || "balanced"}</span>
              </div>
              <div className="flex flex-col">
                <span className="text-[8px] font-black uppercase tracking-widest text-slate-400 dark:text-slate-500 mb-0.5">Budget</span>
                <span className="text-xs text-foreground dark:text-slate-200">€{draft.payload.budget_total_eur || 500.0}</span>
              </div>
              <div className="flex flex-col border-t border-slate-50 dark:border-slate-800 pt-2">
                <span className="text-[8px] font-black uppercase tracking-widest text-slate-400 dark:text-slate-500 mb-0.5">Environment</span>
                <span className="text-xs text-foreground dark:text-slate-200">
                  {draft.payload.is_live ? "⚡ LIVE Real" : "📝 PAPER Sandbox"}
                </span>
              </div>
              <div className="flex flex-col border-t border-slate-50 dark:border-slate-800 pt-2">
                <span className="text-[8px] font-black uppercase tracking-widest text-slate-400 dark:text-slate-500 mb-0.5">Mode</span>
                <span className="text-xs text-foreground dark:text-slate-200 capitalize">{draft.payload.mode || "manual"}</span>
              </div>
            </div>
          )}
        </div>

        {/* BUTTON CONTROLS */}
        <div className="grid grid-cols-3 gap-2">
          <button
            onClick={handleApprove}
            disabled={approving}
            className={`py-2 px-3 rounded-xl text-[10px] font-black uppercase tracking-wider text-white transition-all shadow-md flex items-center justify-center gap-1 bg-gradient-to-r ${getAccentGradient()} hover:opacity-90 active:scale-95`}
          >
            {approving ? (
              <Loader2 size={12} className="animate-spin" />
            ) : (
              "APPROVE"
            )}
          </button>
          
          <button
            onClick={handleEditClick}
            disabled={approving}
            className="py-2 px-3 rounded-xl text-[10px] font-black uppercase tracking-wider border-2 border-slate-200 dark:border-slate-700 hover:border-slate-300 dark:hover:border-slate-600 text-slate-600 dark:text-slate-300 bg-white dark:bg-slate-950 transition-all hover:bg-slate-50 active:scale-95 flex items-center justify-center"
          >
            EDIT
          </button>

          <button
            onClick={onCancel}
            disabled={approving}
            className="py-2 px-3 rounded-xl text-[10px] font-black uppercase tracking-wider border-2 border-slate-200 dark:border-slate-700 hover:border-red-500 hover:text-red-500 dark:hover:border-red-500/30 text-slate-500 dark:text-slate-400 bg-white dark:bg-slate-950 transition-all hover:bg-slate-50 active:scale-95 flex items-center justify-center"
          >
            CANCEL
          </button>
        </div>
      </div>
    </div>
  );
}

function ConceptCard({ state, onCancel, onEdit, onFinalize, onUpdateSlots }) {
  const { current_flow, slots } = state;
  const flowType = current_flow?.split("_")?.[0] || "setup"; // setup, strategy, bot

  const getAccentGradient = () => {
    if (flowType === "setup") return "from-amber-500 to-yellow-400";
    if (flowType === "strategy") return "from-blue-500 to-indigo-500";
    return "from-emerald-500 to-teal-500";
  };

  return (
    <div className="mt-4 overflow-hidden rounded-2xl border-2 border-dashed border-slate-200 dark:border-slate-800 bg-slate-50/30 dark:bg-slate-900/40 shadow-md animate-in fade-in duration-300">
      <div className="p-4 space-y-4">
        {/* TITLE & BADGE */}
        <div className="flex items-start justify-between">
          <div className="space-y-0.5">
            <span className="text-[9px] font-black uppercase tracking-widest text-slate-400 dark:text-slate-500 flex items-center gap-1.5">
              <span className="w-1.5 h-1.5 rounded-full bg-amber-500 animate-pulse" />
              Live Concept
            </span>
            <h4 className="text-xs font-black text-foreground dark:text-slate-200 tracking-tight leading-snug">
              {flowType === "setup" ? `${slots?.symbol || "..."} Setup Concept` :
               flowType === "strategy" ? `${slots?.symbol || "..."} Strategie Concept` :
               `${slots?.name || "..."} Bot Concept`}
            </h4>
          </div>
          <span className={`text-[8px] font-black uppercase tracking-wider px-2 py-0.5 rounded-md shadow-sm text-white bg-gradient-to-r ${getAccentGradient()}`}>
            {flowType} concept
          </span>
        </div>

        {/* METADATA RENDER WITH PLACEHOLDERS */}
        <div className="rounded-xl bg-white dark:bg-slate-950 p-3.5 border border-slate-100 dark:border-slate-800/80 space-y-2.5 shadow-sm">
          {flowType === "setup" && (
            <div className="grid grid-cols-2 gap-x-4 gap-y-3.5 text-[11px] font-bold text-slate-600 dark:text-slate-300">
              <div className="flex flex-col">
                <span className="text-[8px] font-black uppercase tracking-widest text-slate-400 dark:text-slate-500 mb-0.5">Asset</span>
                <span className="font-mono text-xs text-foreground dark:text-slate-200">{slots?.symbol || <span className="text-slate-400 italic font-normal">[Vereist]</span>}</span>
              </div>
              
              <div className="flex flex-col">
                <span className="text-[8px] font-black uppercase tracking-widest text-slate-400 dark:text-slate-500 mb-1">Setup Type</span>
                <div className="flex gap-1.5">
                  {['dca', 'trade'].map((type) => (
                    <button
                      key={type}
                      onClick={() => onUpdateSlots && onUpdateSlots({ setup_type: type })}
                      className={`px-2.5 py-0.5 rounded-lg text-[9px] font-black uppercase tracking-wider transition-all duration-150 active:scale-95 ${
                        slots?.setup_type === type
                          ? 'bg-amber-500 text-white shadow-sm'
                          : 'bg-slate-100 dark:bg-slate-900 text-slate-500 dark:text-slate-400 hover:bg-slate-200 dark:hover:bg-slate-800'
                      }`}
                    >
                      {type}
                    </button>
                  ))}
                </div>
              </div>

              {slots?.setup_type === "dca" && (
                <div className="flex flex-col col-span-2 border-t border-slate-50 dark:border-slate-800/80 pt-2.5">
                  <span className="text-[8px] font-black uppercase tracking-widest text-slate-400 dark:text-slate-500 mb-1.5">DCA Frequency</span>
                  <div className="flex gap-1.5">
                    {['daily', 'weekly', 'monthly'].map((freq) => (
                      <button
                        key={freq}
                        onClick={() => onUpdateSlots && onUpdateSlots({ dca_frequency: freq })}
                        className={`px-2.5 py-0.5 rounded-lg text-[9px] font-black uppercase tracking-wider transition-all duration-150 active:scale-95 ${
                          slots?.dca_frequency === freq
                            ? 'bg-amber-500 text-white shadow-sm'
                            : 'bg-slate-100 dark:bg-slate-900 text-slate-500 dark:text-slate-400 hover:bg-slate-200 dark:hover:bg-slate-800'
                        }`}
                      >
                        {freq === 'daily' ? 'Dagelijks' : freq === 'weekly' ? 'Wekelijks' : 'Maandelijks'}
                      </button>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}

          {flowType === "strategy" && (
            <div className="grid grid-cols-2 gap-x-4 gap-y-2 text-[11px] font-bold text-slate-600 dark:text-slate-300">
              <div className="flex flex-col">
                <span className="text-[8px] font-black uppercase tracking-widest text-slate-400 dark:text-slate-500 mb-0.5">Asset</span>
                <span className="font-mono text-xs text-foreground dark:text-slate-200">{slots?.symbol || "SOL"}</span>
              </div>
              <div className="flex flex-col">
                <span className="text-[8px] font-black uppercase tracking-widest text-slate-400 dark:text-slate-500 mb-0.5">Base Budget</span>
                <span className="text-xs text-foreground dark:text-slate-200">
                  {slots?.base_amount ? `€${slots.base_amount}` : <span className="text-slate-400 italic font-normal">[Kies inleg]</span>}
                </span>
              </div>
              {slots?.setup_type === "trade" ? (
                <>
                  <div className="flex flex-col border-t border-slate-50 dark:border-slate-800 pt-2">
                    <span className="text-[8px] font-black uppercase tracking-widest text-slate-400 dark:text-slate-500 mb-0.5">Entry Target</span>
                    <span className="text-xs text-foreground dark:text-slate-200">
                      {slots?.entry ? `€${slots.entry}` : <span className="text-slate-400 italic font-normal">[Optioneel]</span>}
                    </span>
                  </div>
                  <div className="flex flex-col border-t border-slate-50 dark:border-slate-800 pt-2">
                    <span className="text-[8px] font-black uppercase tracking-widest text-slate-400 dark:text-slate-500 mb-0.5">Stop Loss</span>
                    <span className="text-xs text-rose-500">
                      {slots?.stop_loss ? `€${slots.stop_loss}` : <span className="text-slate-400 italic font-normal">[Optioneel]</span>}
                    </span>
                  </div>
                  <div className="flex flex-col col-span-2 border-t border-slate-50 dark:border-slate-800 pt-2">
                    <span className="text-[8px] font-black uppercase tracking-widest text-slate-400 dark:text-slate-500 mb-0.5">Take Profit Targets</span>
                    <span className="text-xs text-emerald-500 font-mono">
                      {slots?.targets ? (Array.isArray(slots.targets) ? slots.targets.map(t => `€${t}`).join(" · ") : `€${slots.targets}`) : <span className="text-slate-400 italic font-normal">[Optioneel]</span>}
                    </span>
                  </div>
                </>
              ) : (
                <div className="flex flex-col col-span-2 border-t border-slate-50 dark:border-slate-800 pt-2">
                  <span className="text-[8px] font-black uppercase tracking-widest text-slate-400 dark:text-slate-500 mb-0.5">DCA Multiplier Mode</span>
                  <span className="text-xs text-foreground dark:text-slate-200 uppercase font-mono">{slots?.execution_mode || "fixed"}</span>
                </div>
              )}
            </div>
          )}

          {flowType === "bot" && (
            <div className="grid grid-cols-2 gap-x-4 gap-y-2 text-[11px] font-bold text-slate-600 dark:text-slate-300">
              <div className="flex flex-col col-span-2">
                <span className="text-[8px] font-black uppercase tracking-widest text-slate-400 dark:text-slate-500 mb-0.5">Bot Naam</span>
                <span className="text-xs text-foreground dark:text-slate-200">{slots?.name || "SOL Bot"}</span>
              </div>
              <div className="flex flex-col border-t border-slate-50 dark:border-slate-800 pt-2">
                <span className="text-[8px] font-black uppercase tracking-widest text-slate-400 dark:text-slate-500 mb-0.5">Safety Profile</span>
                <span className="text-xs text-foreground dark:text-slate-200 capitalize">{slots?.risk_profile || "balanced"}</span>
              </div>
              <div className="flex flex-col border-t border-slate-50 dark:border-slate-800 pt-2">
                <span className="text-[8px] font-black uppercase tracking-widest text-slate-400 dark:text-slate-500 mb-0.5">Budget</span>
                <span className="text-xs text-foreground dark:text-slate-200">
                  {slots?.budget_total_eur ? `€${slots.budget_total_eur}` : <span className="text-slate-400 italic font-normal">[Vereist]</span>}
                </span>
              </div>
            </div>
          )}
        </div>

        {/* CONTROLS */}
        <div className="grid grid-cols-3 gap-2">
          <button
            onClick={onCancel}
            className="py-2 px-3 rounded-xl text-[10px] font-black uppercase tracking-wider border-2 border-slate-200 dark:border-slate-700 hover:border-slate-300 dark:hover:border-slate-600 text-slate-600 dark:text-slate-300 bg-white dark:bg-slate-950 transition-all hover:bg-slate-50 active:scale-95 flex items-center justify-center"
          >
            CANCEL
          </button>
          
          <button
            onClick={onEdit}
            className="py-2 px-3 rounded-xl text-[10px] font-black uppercase tracking-wider border-2 border-slate-200 dark:border-slate-700 hover:border-slate-300 dark:hover:border-slate-600 text-slate-600 dark:text-slate-300 bg-white dark:bg-slate-950 transition-all hover:bg-slate-50 active:scale-95 flex items-center justify-center"
          >
            EDIT
          </button>

          <button
            onClick={onFinalize}
            className="py-2 px-3 rounded-xl text-[10px] font-black uppercase tracking-wider text-white transition-all shadow-md flex items-center justify-center bg-emerald-600 hover:bg-emerald-700 active:scale-95"
          >
            APPROVE
          </button>
        </div>
      </div>
    </div>
  );
}

function ReasoningWidget({ reasoning }) {
  const pathname = usePathname();
  if (!reasoning) return null;

  const isAdminMode = pathname?.includes("/admin");

  if (isAdminMode) {
    return <DebugExplainabilityCard reasoning={reasoning} />;
  }

  // Hide completely for standard users
  return null;
}

function DebugExplainabilityCard({ reasoning }) {
  const [isOpen, setIsOpen] = useState(false);
  if (!reasoning) return null;

  const { confidence_score, risk_detected, reasons, coaching_level } = reasoning;

  return (
    <div className="mt-3 overflow-hidden rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-900/50 shadow-sm">
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="w-full px-3 py-2 flex items-center justify-between text-left text-[10px] font-black uppercase tracking-wider text-rose-500 dark:text-rose-400 hover:bg-slate-100 dark:hover:bg-slate-800/60 transition-colors"
      >
        <span className="flex items-center gap-1.5 font-mono">
          <Brain size={12} className="text-rose-500" />
          [DEBUG] GEDACHTEGANG & DIAGNOSTICS
        </span>
        <ChevronDown size={12} className={`transition-transform duration-200 ${isOpen ? "rotate-180" : ""}`} />
      </button>

      {isOpen && (
        <div className="p-3 border-t border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-950 space-y-2.5 font-mono text-[10px]">
          <div className="grid grid-cols-3 gap-2">
            <div className="bg-slate-50 dark:bg-slate-900 rounded-lg p-2 text-center border border-slate-100 dark:border-slate-800">
              <span className="text-[7px] font-black uppercase tracking-wider text-slate-400 block">Confidence</span>
              <span className="text-[11px] font-black text-blue-500">{confidence_score ? `${confidence_score}%` : 'N/A'}</span>
            </div>
            
            <div className="bg-slate-50 dark:bg-slate-900 rounded-lg p-2 text-center border border-slate-100 dark:border-slate-800">
              <span className="text-[7px] font-black uppercase tracking-wider text-slate-400 block">Risico</span>
              <span className={`text-[10px] font-black ${risk_detected ? 'text-rose-500 animate-pulse' : 'text-emerald-500'}`}>
                {risk_detected ? 'GEDETECTEERD' : 'VEILIG'}
              </span>
            </div>
            
            <div className="bg-slate-50 dark:bg-slate-900 rounded-lg p-2 text-center border border-slate-100 dark:border-slate-800">
              <span className="text-[7px] font-black uppercase tracking-wider text-slate-400 block">Coaching</span>
              <span className="text-[10px] font-black text-amber-500 uppercase">{coaching_level || 'ALGEMEEN'}</span>
            </div>
          </div>

          {reasons && reasons.length > 0 && (
            <div className="space-y-1">
              <span className="text-[8px] font-black uppercase tracking-widest text-slate-400 block">REASONING CHAINS:</span>
              <ul className="space-y-1 pl-2">
                {reasons.map((reason, idx) => (
                  <li key={idx} className="text-[10px] text-slate-600 dark:text-slate-300 flex items-start gap-1.5">
                    <span className="text-blue-500 mt-0.5">•</span>
                    <span>{reason}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
