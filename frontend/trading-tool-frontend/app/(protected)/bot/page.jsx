"use client";

import { Suspense, useEffect, useRef, useState, useMemo } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { Wallet, Plus } from "lucide-react";

import useBotData from "@/hooks/useBotData";
import { useStrategyData } from "@/hooks/useStrategyData";
import { useModal } from "@/components/modal/ModalProvider";

import { useMarketIntelligence } from "@/hooks/useMarketIntelligence";
import BotAgentCard from "@/components/bot/BotAgentCard";
import BotScores from "@/components/bot/BotScores";
import BotForm from "@/components/bot/AddBotForm";
import BotBudgetForm from "@/components/bot/BotBudgetForm";
import GlobalTradePanel from "@/components/bot/GlobalTradePanel";

import {
  ActiveBotProvider,
  useActiveBot,
} from "@/app/providers/ActiveBotProvider";
import SystemConnectivity from "@/components/dashboard/SystemConnectivity";
import DashboardErrorBoundary from "@/components/ui/DashboardErrorBoundary";
import { actionButtonStyles } from "@/components/ui/actionButtonStyles";
import { trackAssistantEvent } from "@/lib/api/assistantAnalytics";
import { useTranslation } from "@/app/providers/I18nProvider";
import { useOnboarding } from "@/hooks/useOnboarding";
import OnboardingBanner from "@/components/onboarding/OnboardingBanner";
import OnboardingStepGuide from "@/components/onboarding/OnboardingStepGuide";
import FinnSpecialistContext from "@/components/finn/FinnSpecialistContext";

function BotPageInner() {
  const router = useRouter();
  const { t } = useTranslation();
  const { status, completeStep } = useOnboarding();
  const { openConfirm, showSnackbar } = useModal();
  const searchParams = useSearchParams();
  const formRef = useRef({});
  const budgetRef = useRef({});

  const { activeBot, setActiveBot } = useActiveBot();

  const [statusFilter, setStatusFilter] = useState("all");
  const [assetFilter, setAssetFilter] = useState("all");
  const [currentTime, setCurrentTime] = useState(null);
  const [generatingBotId, setGeneratingBotId] = useState(null);
  const copy = t?.botPage || {};
  const botGuideCopy = copy.onboardingGuide || {};

  const {
    configs: bots = [],
    today,
    history = [],
    portfolios = [],
    decisionsByBot = {},
    tradesByBot = {},
    loading,
    error,

    createBot,
    updateBot,
    deleteBot,

    generateDecisionForBot,
    runBacktest,
  } = useBotData();

  const { strategies = [], loadStrategies } = useStrategyData();

  const {
    data: marketIntelligence,
    loading: loadingMarketIntelligence,
  } = useMarketIntelligence();

  const botNeedsBot = status?.has_bot === false && bots.length === 0;
  const botStepComplete = Boolean(status?.has_bot || bots.length > 0);
  const onboardingGuidedMode = searchParams.get("onboarding") === "1";
  const showOnboardingGuide = onboardingGuidedMode || botNeedsBot;

  useEffect(() => {
    if (!status || status.has_asset) return;
    router.replace("/onboarding/asset?onboarding=1&step=asset");
  }, [status, router]);

  useEffect(() => {
    if (!status || !onboardingGuidedMode || status.has_strategy) return;
    router.replace(`/strategy?onboarding=1&step=strategy${searchParams.get("symbol") ? `&symbol=${encodeURIComponent(searchParams.get("symbol"))}` : ""}`);
  }, [status, onboardingGuidedMode, router, searchParams]);

  useEffect(() => {
    setCurrentTime(new Date());
    loadStrategies();
  }, [loadStrategies]);

  useEffect(() => {
    trackAssistantEvent({
      event_name: "screen_view",
      page: "/bot",
      surface: "web",
      flow_type: "portfolio_review",
    });
  }, []);

  useEffect(() => {
    if (bots.length === 0) {
      setActiveBot(null);
      return;
    }
    if (!activeBot || !bots.find((b) => b.id === activeBot.id)) {
      setActiveBot(bots[0]);
    }
  }, [bots, activeBot, setActiveBot]);

  useEffect(() => {
    if (bots.length > 0 && status && status.has_bot === false) {
      completeStep("bot");
    }
  }, [bots, status, completeStep]);

  useEffect(() => {
    if (!bots.length) return;

    const requestedBotId = Number(searchParams.get("bot_id"));
    const requestedSymbol = (searchParams.get("symbol") || "").toUpperCase();
    const requestedFocus = searchParams.get("focus");

    const targetBot =
      (Number.isFinite(requestedBotId) && requestedBotId > 0
        ? bots.find((bot) => bot.id === requestedBotId)
        : null) ||
      (requestedSymbol
        ? bots.find((bot) => String(bot?.symbol || bot?.strategy?.symbol || "").toUpperCase() === requestedSymbol)
        : null);

    if (targetBot && activeBot?.id !== targetBot.id) {
      setActiveBot(targetBot);
    }

    if (requestedFocus === "trade") {
      requestAnimationFrame(() => {
        document.getElementById("execution-guardrail-panel")?.scrollIntoView({
          behavior: "smooth",
          block: "start",
        });
      });
    }
  }, [bots, activeBot?.id, searchParams, setActiveBot]);

  useEffect(() => {
    const handleExecutionHandoff = (event) => {
      const detail = event?.detail || {};
      const botId = Number(detail.botId);
      const symbol = String(detail.symbol || "").toUpperCase();
      const targetBot =
        (Number.isFinite(botId) && botId > 0 ? bots.find((bot) => bot.id === botId) : null) ||
        (symbol ? bots.find((bot) => String(bot?.symbol || bot?.strategy?.symbol || "").toUpperCase() === symbol) : null);

      if (targetBot) {
        setActiveBot(targetBot);
      }

      requestAnimationFrame(() => {
        document.getElementById("execution-guardrail-panel")?.scrollIntoView({
          behavior: "smooth",
          block: "start",
        });
      });
    };

    window.addEventListener("execution-guardrail-handoff", handleExecutionHandoff);
    return () => window.removeEventListener("execution-guardrail-handoff", handleExecutionHandoff);
  }, [bots, setActiveBot]);

  const dailyScores = today?.daily_scores ?? today?.scores ?? {
    macro: 10, technical: 10, market: 10, setup: 10
  };

  const availableAssets = useMemo(() => {
    const assets = new Set(
      bots
        .map((bot) => {
          const portfolio = portfolios.find((item) => item.bot_id === bot.id);
          return portfolio?.symbol ?? bot?.symbol ?? "—";
        })
        .filter((symbol) => symbol && symbol !== "—")
    );
    return Array.from(assets).sort();
  }, [bots, portfolios]);

  const filteredBots = useMemo(() => {
    return bots.filter((bot) => {
      if (statusFilter === "active" && !bot.is_active) return false;
      if (statusFilter === "paused" && bot.is_active) return false;
      
      const p = portfolios.find((x) => x.bot_id === bot.id);
      const symbol = p?.symbol ?? bot?.symbol ?? "—";
      
      if (assetFilter !== "all" && symbol !== assetFilter) return false;
      
      return true;
    });
  }, [bots, statusFilter, assetFilter, portfolios]);

  const totalPortfolioValueEur = useMemo(() => {
    return portfolios.reduce((acc, p) => {
      const v = Number(p?.stats?.position_value_eur ?? 0);
      return acc + (Number.isFinite(v) ? v : 0);
    }, 0);
  }, [portfolios]);

  const portfolioBalanceDataByRange = useMemo(() => {
    const byRange = today?.portfolio_balance_by_range || today?.portfolio_balance_history_by_range || null;
    if (byRange && typeof byRange === "object") {
      const normalizeSeries = (series) =>
        (Array.isArray(series) ? series : []).map((p) => ({
          ts: p?.ts || p?.timestamp || p?.date || null,
          value_eur: Number(p?.value_eur ?? p?.value ?? p?.balance_eur ?? p?.portfolio_value_eur ?? 0)
        })).filter((p) => p.ts && Number.isFinite(p.value_eur));

      return {
        "1D": normalizeSeries(byRange["1D"]),
        "1W": normalizeSeries(byRange["1W"]),
        "1M": normalizeSeries(byRange["1M"]),
        "1Y": normalizeSeries(byRange["1Y"]),
        ALL: normalizeSeries(byRange["ALL"] || byRange["all"]),
      };
    }
    const single = [{ ts: currentTime?.toISOString() || new Date().toISOString(), value_eur: totalPortfolioValueEur }];
    return { "1D": single, "1W": single, "1M": single, "1Y": single, ALL: single };
  }, [today, totalPortfolioValueEur, currentTime]);

  const handleGenerateDecision = async (bot) => {
    try { 
      setGeneratingBotId(bot.id); 
      await generateDecisionForBot({ bot_id: bot.id }); 
      showSnackbar(`${copy.proposalCreatedPrefix} ${bot.name}`, "success");
    }
    catch { 
      showSnackbar(copy.proposalCreateFailed, "danger");
    }
    finally { 
      setGeneratingBotId(null); 
    }
  };

  const handleAddBot = (initialValues = {}) => {
    formRef.current = initialValues;
    openConfirm({
      title: copy.createTitle,
      statusLabel: copy.createStatus,
      description: <BotForm strategies={strategies} initialValues={initialValues} onChange={(v) => (formRef.current = v)} />,
      context: <p>{initialValues.symbol || formRef.current?.symbol || copy.newBotLabel} · {(initialValues.is_live || formRef.current?.is_live) ? copy.modeLive : copy.modeSimulation}</p>,
      impact: <p>{copy.createImpact}</p>,
      safety: <p>{copy.createSafety}</p>,
      consequence: <p>{copy.createConsequence}</p>,
      confirmText: copy.createConfirm,
      busyText: copy.createBusy,
      onConfirm: async () => {
        if (!formRef.current?.name || !formRef.current?.strategy_id) { showSnackbar(copy.createValidation, "danger"); return; }
        await createBot(formRef.current); showSnackbar(copy.createSuccess, "success");
      },
    });
  };

  useEffect(() => {
    const action = searchParams.get("action");
    if (action === "new_bot") {
      if (!strategies.length) return;

      const symbol = searchParams.get("symbol") || "";
      const mode = searchParams.get("mode") || "paper";
      const risk = searchParams.get("risk") || "balanced";
      const budget = searchParams.get("budget") || "";
      
      // Auto-prefill the form values
      const initialValues = {
        name: `Finn Bot ${symbol} ${mode === "paper" ? copy.modePaper : copy.modeLive}`,
        symbol: symbol,
        is_live: mode === "live",
        budget_total_eur: budget ? Number(budget) : 1000,
      };

      handleAddBot(initialValues);

      // Clean search parameters to avoid re-opening modal on subsequent updates
      const newUrl = window.location.pathname;
      window.history.replaceState({}, '', newUrl);
    }
  }, [searchParams, strategies]);

  const handleOpenBotSettings = async (type, bot) => {
    if (!bot) return;
    if (type === "general") {
      formRef.current = bot;
      openConfirm({
        title: `${copy.updateTitlePrefix} – ${bot.name}`,
        statusLabel: copy.updateStatus,
        description: <BotForm strategies={strategies} initialValues={bot} onChange={(v) => (formRef.current = v)} />,
        context: <p>{bot.symbol || copy.botLabel} · {bot.is_live ? copy.modeLive : copy.modePaper}</p>,
        impact: <p>{copy.updateImpact}</p>,
        safety: <p>{copy.updateSafety}</p>,
        consequence: <p>{copy.updateConsequence}</p>,
        confirmText: copy.updateConfirm,
        busyText: copy.updateBusy,
        onConfirm: async () => { await updateBot(bot.id, formRef.current); showSnackbar(copy.updateSuccess, "success"); },
      });
      return;
    }
    if (type === "portfolio") {
      const portfolio = portfolios.find((p) => p.bot_id === bot.id);
      budgetRef.current = { total_eur: portfolio?.budget?.total_eur ?? 0, daily_limit_eur: portfolio?.budget?.daily_limit_eur ?? 0, max_order_eur: portfolio?.budget?.max_order_eur ?? 0, max_asset_exposure_pct: portfolio?.budget?.max_asset_exposure_pct ?? 100 };
      openConfirm({
        title: `${copy.budgetTitlePrefix} – ${bot.name}`,
        statusLabel: copy.budgetStatus,
        description: <BotBudgetForm initialBudget={budgetRef.current} onChange={(v) => (budgetRef.current = v)} />,
        context: <p>{bot.symbol || copy.botLabel} · {bot.is_live ? copy.modeLive : copy.modePaper}</p>,
        impact: <p>{copy.budgetImpact}</p>,
        safety: <p>{copy.budgetSafety}</p>,
        consequence: <p>{copy.budgetConsequence}</p>,
        confirmText: copy.budgetConfirm,
        busyText: copy.budgetBusy,
        onConfirm: async () => {
          await updateBot(bot.id, {
            budget_total_eur: budgetRef.current.total_eur,
            budget_daily_limit_eur: budgetRef.current.daily_limit_eur,
            budget_max_order_eur: budgetRef.current.max_order_eur,
            max_asset_exposure_pct: budgetRef.current.max_asset_exposure_pct,
          });
          showSnackbar(copy.budgetSuccess, "success");
          // 🔥 Refresh decision to apply new budget to guardrails
          await handleGenerateDecision(bot);
        },
      });
      return;
    }
    if (type === "pause") { await updateBot(bot.id, { is_active: false }); showSnackbar(copy.pauseSuccess, "info"); return; }
    if (type === "resume") { await updateBot(bot.id, { is_active: true }); showSnackbar(copy.resumeSuccess, "success"); return; }
    if (type === "delete") {
      openConfirm({
        title: `${copy.deleteTitlePrefix} – ${bot.name}`,
        statusLabel: copy.deleteStatus,
        tone: "danger",
        context: <p>{bot.symbol || copy.botLabel} · {bot.is_live ? copy.modeLive : copy.modePaper}</p>,
        impact: <p>{copy.deleteImpact}</p>,
        safety: <p>{copy.deleteSafety}</p>,
        consequence: <p>{copy.deleteConsequence}</p>,
        confirmText: copy.deleteConfirm,
        busyText: copy.deleteBusy,
        onConfirm: async () => { await deleteBot(bot.id); showSnackbar(copy.deleteSuccess, "danger"); }
      });
    }
  };

  /* =====================================================
     🛸 THE GLIDER (ULTRA-SMOOTH 60FPS VERSION)
  ===================================================== */
  const gliderRef = useRef(null);
  const requestRef = useRef();

  useEffect(() => {
    const updatePosition = () => {
      if (!gliderRef.current) return;
      
      const container = gliderRef.current.parentElement;
      if (!container) return;

      const rect = container.getBoundingClientRect();
      const offset = Math.max(0, -rect.top + 100); // 100px margin from top
      
      const containerHeight = container.offsetHeight;
      const gliderHeight = gliderRef.current.offsetHeight;
      const maxOffset = Math.max(0, containerHeight - gliderHeight - 40);
      
      const finalOffset = Math.min(offset, maxOffset);
      
      // Direct DOM manipulation for maximum performance (no React jitter)
      gliderRef.current.style.transform = `translate3d(0, ${finalOffset}px, 0)`;
      
      requestRef.current = requestAnimationFrame(updatePosition);
    };

    requestRef.current = requestAnimationFrame(updatePosition);
    
    return () => {
      if (requestRef.current) cancelAnimationFrame(requestRef.current);
    };
  }, [bots.length]); 

  return (
    <div className="page-container !max-w-none !px-6 bg-white dark:bg-[#020617] transition-colors h-auto overflow-visible">
      
      {/* 🟢 STANDARD PAGE HEADER */}
      <header className="page-header border-l-4 border-blue-600 pl-8 mb-16">
        <div className="page-label text-[11px] font-black text-blue-600 dark:text-blue-500 uppercase tracking-[0.3em] mb-2 opacity-80 flex items-center gap-2">
           <Wallet size={12} />
           {copy.eyebrow}
        </div>
          <div className="max-w-2xl">
            <h1 className="page-title text-5xl font-black text-slate-900 dark:text-slate-100 tracking-tight leading-none mb-3">{copy.title}</h1>
            <p className="page-subtitle text-[15px] font-medium text-slate-400 dark:text-slate-500 leading-relaxed">
              {copy.subtitle}
            </p>
          </div>
      </header>

      <OnboardingBanner step="bot" />

      {showOnboardingGuide ? (
        <OnboardingStepGuide
          copy={botGuideCopy}
          anchorId="bot-create"
          guidedMode={onboardingGuidedMode}
          isComplete={botStepComplete}
          nextHref="/onboarding/complete"
        />
      ) : null}

      <div className="mb-10">
        <FinnSpecialistContext
          subjectType="automation"
          subjectId={activeBot?.id}
          symbol={activeBot?.symbol || searchParams.get("symbol") || "BTC"}
          timeframe={activeBot?.timeframe || "1D"}
        />
      </div>

      <div className="max-w-full flex flex-col lg:flex-row gap-10 pb-24 items-start relative">
        
        {/* 🕋 LEFT: MAIN COMMAND CENTER */}
        <div className="flex-1 min-w-0 space-y-12">
          {error && (
            <div className="rounded-2xl border border-red-200 bg-red-50 px-5 py-4 text-sm font-bold text-red-700 dark:border-red-900/60 dark:bg-red-950/30 dark:text-red-200">
              {copy.partialError}
            </div>
          )}

          {/* ... existing content ... */}
          <div className="space-y-6">
            <BotScores scores={dailyScores} loading={loading?.today} />
          </div>

          {/* BOT DEPLOYMENT SECTION */}
          <div className="space-y-8 pt-8 border-t border-slate-100 dark:border-slate-800">
            <div className="space-y-6">
              <div>
                <h2 className="text-4xl font-black text-slate-900 dark:text-slate-100 tracking-tighter">{copy.myBotsTitle}</h2>
                <p className="text-[13px] font-medium text-slate-400 dark:text-slate-500 mt-1">{copy.myBotsSubtitle}</p>
              </div>

              <div id="bot-create" className="flex flex-wrap items-center justify-between gap-6 scroll-mt-32">
                <div className="flex gap-4">
                  <div className="flex bg-slate-100/80 dark:bg-slate-900/80 backdrop-blur-sm p-1.5 rounded-2xl border border-slate-200/50 dark:border-slate-800/50 shadow-inner">
                    <button onClick={() => setStatusFilter("all")} className={`px-5 py-2 rounded-xl text-[10px] font-black uppercase tracking-widest transition-all ${statusFilter === "all" ? "bg-white dark:bg-slate-800 text-slate-900 dark:text-white shadow-md" : "text-slate-400 dark:text-slate-500 hover:text-slate-600"}`}>{copy.filterAll} ({bots.length})</button>
                    <button onClick={() => setStatusFilter("active")} className={`px-5 py-2 rounded-xl text-[10px] font-black uppercase tracking-widest transition-all ${statusFilter === "active" ? "bg-white dark:bg-slate-800 text-emerald-600 dark:text-emerald-400 shadow-md" : "text-slate-400 dark:text-slate-500 hover:text-emerald-500"}`}>{copy.filterActive} ({bots.filter(b => b.is_active).length})</button>
                    <button onClick={() => setStatusFilter("paused")} className={`px-5 py-2 rounded-xl text-[10px] font-black uppercase tracking-widest transition-all ${statusFilter === "paused" ? "bg-white dark:bg-slate-800 text-amber-600 dark:text-amber-400 shadow-md" : "text-slate-400 dark:text-slate-500 hover:text-amber-500"}`}>{copy.filterPaused} ({bots.filter(b => !b.is_active).length})</button>
                  </div>
                  
                  <div className="flex bg-slate-100/80 dark:bg-slate-900/80 backdrop-blur-sm p-1.5 rounded-2xl border border-slate-200/50 dark:border-slate-800/50 shadow-inner items-center">
                    <select
                      value={assetFilter}
                      onChange={(e) => setAssetFilter(e.target.value)}
                      className="bg-transparent px-4 py-1 text-[10px] font-black uppercase tracking-widest text-slate-700 dark:text-slate-300 focus:outline-none cursor-pointer appearance-none"
                    >
                      <option value="all">{copy.allAssets}</option>
                      {availableAssets.map((a) => (
                        <option key={a} value={a}>{a}</option>
                      ))}
                    </select>
                  </div>
                </div>

                <div className="flex items-center gap-4">
                  <DashboardErrorBoundary>
                    <SystemConnectivity />
                  </DashboardErrorBoundary>

                  <button onClick={handleAddBot} className={actionButtonStyles({ variant: "primary", className: "min-h-12 px-6 rounded-2xl shadow-sm" })}>
                    <Plus size={18} strokeWidth={3} />
                    {copy.createTitle}
                  </button>
                </div>
              </div>
            </div>

            <div className="space-y-10">
              {filteredBots.map((bot) => {
                const isActive = activeBot?.id === bot.id;
                return (
                  <div key={bot.id} onClick={(e) => { if (e.target.closest("button") || e.target.closest("input")) return; setActiveBot(bot); }} 
                  className={`relative transition-all duration-300 cursor-pointer ${isActive ? "ring-4 ring-blue-500 shadow-[0_0_25px_rgba(59,130,246,0.25)] ring-offset-4 dark:ring-offset-[#020617] rounded-[2.5rem] z-10" : "hover:scale-[1.002]"}`}>
                    <BotAgentCard
                      bot={bot}
                      decision={decisionsByBot?.[bot.id]}
                      order={(today?.orders || []).find((o) => o.bot_id === bot.id)}
                      marketIntelligence={marketIntelligence}
                      loadingMarketIntelligence={loadingMarketIntelligence}
                      portfolio={portfolios.find((p) => p.bot_id === bot.id)}
                      trades={tradesByBot?.[bot.id] ?? []}
                      history={history}
                      loadingDecision={generatingBotId === bot.id}
                      onGenerate={() => handleGenerateDecision(bot)}
                      onExecute={() => {}} 
                      onSkip={() => {}} 
                      onOpenSettings={handleOpenBotSettings}
                      onSaveTradePlan={() => {}}
                      onPlaceManualOrder={() => {}}
                      onBacktest={runBacktest}
                    />
                    {isActive && (
                      <div className="absolute -left-1 top-1/2 -translate-y-1/2 w-1.5 h-12 bg-blue-600 rounded-full" />
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        </div>

        {/* 🛰️ RIGHT: GLOBAL OVERRIDES (v2200-SMOOTH) */}
        <div 
          className="w-full lg:w-[350px] shrink-0"
          style={{ 
            willChange: 'transform',
            backfaceVisibility: 'hidden'
          }}
          ref={gliderRef}
        >
          <div id="tp-final-v2200-smooth">
            <GlobalTradePanel 
              decision={decisionsByBot?.[activeBot?.id]}
              portfolio={portfolios.find((p) => p.bot_id === activeBot?.id)}
              onManualTrade={() => handleGenerateDecision(activeBot)}
            />
          </div>
        </div>

      </div>
    </div>
  );
}

export default function BotPage() {
  return (
    <Suspense fallback={<div className="min-h-screen bg-[#020617]" />}>
      <ActiveBotProvider>
        <BotPageInner />
      </ActiveBotProvider>
    </Suspense>
  );
}
