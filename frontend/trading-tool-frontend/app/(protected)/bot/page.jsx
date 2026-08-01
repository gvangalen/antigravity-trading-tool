"use client";

import { Suspense, useEffect, useRef, useState, useMemo } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { Bot, ChevronDown, Plus, Sparkles, Wallet } from "lucide-react";

import useBotData from "@/hooks/useBotData";
import { useStrategyData } from "@/hooks/useStrategyData";
import { useModal } from "@/components/modal/ModalProvider";
import Drawer from "@/components/ui/Drawer";

import { useMarketIntelligence } from "@/hooks/useMarketIntelligence";
import BotAgentCard from "@/components/bot/BotAgentCard";
import AddBotForm from "@/components/bot/AddBotForm";
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
import { openFinnContext } from "@/lib/finnCommandSearch";

function persistBotSelection(botId) {
  if (typeof window === "undefined" || !botId) return;
  const url = new URL(window.location.href);
  url.searchParams.set("bot_id", String(botId));
  window.history.replaceState(window.history.state, "", `${url.pathname}${url.search}${url.hash}`);
}

function resolveBotChain(bot, strategies = [], setups = []) {
  const resolvedStrategy =
    bot?.strategy ||
    strategies.find((strategy) => strategy.id === (bot?.strategy_id || bot?.strategy?.id)) ||
    null;

  const resolvedSetup =
    resolvedStrategy?.setup ||
    setups.find((setup) => setup.id === (resolvedStrategy?.setup_id || bot?.strategy?.setup_id || bot?.strategy?.setup?.id)) ||
    null;

  return {
    ...bot,
    strategy: resolvedStrategy
      ? {
          ...resolvedStrategy,
          setup: resolvedSetup || resolvedStrategy?.setup || null,
        }
      : bot?.strategy || null,
  };
}

function getBotChainState(bot, strategies = []) {
  const linkedStrategy =
    bot?.strategy ||
    strategies.find((strategy) => strategy.id === (bot?.strategy_id || bot?.strategy?.id)) ||
    null;

  const hasStrategy = Boolean(linkedStrategy?.id || bot?.strategy_id || bot?.strategy);
  const hasSetup = Boolean(
    linkedStrategy?.setup?.id ||
    linkedStrategy?.setup_id ||
    bot?.strategy?.setup?.id ||
    bot?.strategy?.setup_id
  );

  return {
    linkedStrategy,
    hasStrategy,
    hasSetup,
    isComplete: hasStrategy && hasSetup,
  };
}

function getBotMarketFitScore(decision) {
  const setupMatchScore = Number(
    decision?.setup_match?.score ??
    decision?.scores_json?.setup_match?.score ??
    decision?.scores_json?.setup_score ??
    decision?.setup_score ??
    NaN
  );

  return Number.isFinite(setupMatchScore) ? setupMatchScore : -1;
}

function compareBotsForAutomation(a, b, strategies = [], decisionsByBot = {}) {
  const aChain = getBotChainState(a, strategies);
  const bChain = getBotChainState(b, strategies);

  if (aChain.isComplete !== bChain.isComplete) {
    return aChain.isComplete ? -1 : 1;
  }

  const aScore = getBotMarketFitScore(decisionsByBot?.[a.id] || {});
  const bScore = getBotMarketFitScore(decisionsByBot?.[b.id] || {});
  if (aScore !== bScore) {
    return bScore - aScore;
  }

  if (a.is_active !== b.is_active) {
    return a.is_active ? -1 : 1;
  }

  if (aChain.hasStrategy !== bChain.hasStrategy) {
    return aChain.hasStrategy ? -1 : 1;
  }

  return String(a?.name || "").localeCompare(String(b?.name || ""));
}

function BotPageInner() {
  const router = useRouter();
  const { t, locale } = useTranslation();
  const { status, completeStep } = useOnboarding();
  const { openConfirm, showSnackbar } = useModal();
  const searchParams = useSearchParams();
  const botFormRef = useRef(null);
  const budgetFormRef = useRef(null);
  const hasInitializedExpansionRef = useRef(false);
  const botListColumnRef = useRef(null);
  const botRowRefs = useRef(new Map());

  const { activeBot, setActiveBot } = useActiveBot();

  const [expandedBotId, setExpandedBotId] = useState(null);
  const [tradePanelBotId, setTradePanelBotId] = useState(null);
  const [tradePanelOffset, setTradePanelOffset] = useState(0);
  const [drawer, setDrawer] = useState(null);
  const [pendingFocusedBotId, setPendingFocusedBotId] = useState(null);
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

  const { strategies = [], setups = [], loadStrategies, loadSetups } = useStrategyData();

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
    loadSetups();
    loadStrategies();
  }, [loadSetups, loadStrategies]);

  const resolvedBots = useMemo(() => {
    return bots.map((bot) => resolveBotChain(bot, strategies, setups));
  }, [bots, strategies, setups]);

  const rankedBots = useMemo(() => {
    return [...resolvedBots].sort((left, right) => (
      compareBotsForAutomation(left, right, strategies, decisionsByBot)
    ));
  }, [resolvedBots, strategies, decisionsByBot]);

  useEffect(() => {
    trackAssistantEvent({
      event_name: "screen_view",
      page: "/bot",
      surface: "web",
      flow_type: "portfolio_review",
    });
  }, []);

  useEffect(() => {
    if (rankedBots.length === 0) {
      setActiveBot(null);
      setExpandedBotId(null);
      setTradePanelBotId(null);
      hasInitializedExpansionRef.current = false;
      return;
    }
    if (!activeBot || !rankedBots.find((b) => b.id === activeBot.id)) {
      const defaultBot = rankedBots[0];
      setActiveBot(defaultBot);
      setExpandedBotId(defaultBot.id);
      hasInitializedExpansionRef.current = true;
      return;
    }
    if (!hasInitializedExpansionRef.current) {
      setExpandedBotId(activeBot.id);
      hasInitializedExpansionRef.current = true;
      return;
    }
    setExpandedBotId((currentId) => (
      currentId && !rankedBots.some((bot) => bot.id === currentId) ? null : currentId
    ));
  }, [rankedBots, activeBot, setActiveBot]);

  useEffect(() => {
    if (resolvedBots.length > 0 && status && status.has_bot === false) {
      completeStep("bot");
    }
  }, [resolvedBots, status, completeStep]);

  useEffect(() => {
    if (!resolvedBots.length) return;

    const requestedBotId = Number(searchParams.get("bot_id"));
    const requestedSymbol = (searchParams.get("symbol") || "").toUpperCase();
    const requestedFocus = searchParams.get("focus");

    const targetBot =
      (Number.isFinite(requestedBotId) && requestedBotId > 0
        ? resolvedBots.find((bot) => bot.id === requestedBotId)
        : null) ||
      (requestedSymbol
        ? resolvedBots.find((bot) => String(bot?.symbol || bot?.strategy?.symbol || "").toUpperCase() === requestedSymbol)
        : null);

    if (targetBot && activeBot?.id !== targetBot.id) {
      setActiveBot(targetBot);
      setExpandedBotId(targetBot.id);
    }

    if (requestedFocus === "trade" && targetBot) {
      setTradePanelBotId(targetBot.id);
      requestAnimationFrame(() => {
        document.getElementById("execution-guardrail-panel")?.scrollIntoView({
          behavior: "smooth",
          block: "start",
        });
      });
    }
  }, [resolvedBots, activeBot?.id, searchParams, setActiveBot]);

  useEffect(() => {
    if (!pendingFocusedBotId) return;
    const nextBot = resolvedBots.find((bot) => bot.id === pendingFocusedBotId);
    if (!nextBot) return;

    setActiveBot(nextBot);
    setExpandedBotId(nextBot.id);
    persistBotSelection(nextBot.id);
    setPendingFocusedBotId(null);
  }, [pendingFocusedBotId, resolvedBots, setActiveBot]);

  useEffect(() => {
    const handleExecutionHandoff = (event) => {
      const detail = event?.detail || {};
      const botId = Number(detail.botId);
      const symbol = String(detail.symbol || "").toUpperCase();
      const targetBot =
        (Number.isFinite(botId) && botId > 0 ? resolvedBots.find((bot) => bot.id === botId) : null) ||
        (symbol ? resolvedBots.find((bot) => String(bot?.symbol || bot?.strategy?.symbol || "").toUpperCase() === symbol) : null);

      if (targetBot) {
        setActiveBot(targetBot);
        setExpandedBotId(targetBot.id);
        setTradePanelBotId(targetBot.id);
        persistBotSelection(targetBot.id);
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
  }, [resolvedBots, setActiveBot]);

  const availableAssets = useMemo(() => {
    const assets = new Set(
      resolvedBots
        .map((bot) => {
          const portfolio = portfolios.find((item) => item.bot_id === bot.id);
          return portfolio?.symbol ?? bot?.symbol ?? "—";
        })
        .filter((symbol) => symbol && symbol !== "—")
    );
    return Array.from(assets).sort();
  }, [resolvedBots, portfolios]);

  const filteredBots = useMemo(() => {
    return rankedBots.filter((bot) => {
      if (statusFilter === "active" && !bot.is_active) return false;
      if (statusFilter === "paused" && bot.is_active) return false;
      
      const p = portfolios.find((x) => x.bot_id === bot.id);
      const symbol = p?.symbol ?? bot?.symbol ?? "—";
      
      if (assetFilter !== "all" && symbol !== assetFilter) return false;
      
      return true;
    });
  }, [rankedBots, statusFilter, assetFilter, portfolios]);

  useEffect(() => {
    if (!tradePanelBotId) {
      setTradePanelOffset(0);
      return;
    }

    const updateTradePanelOffset = () => {
      const column = botListColumnRef.current;
      const row = botRowRefs.current.get(String(tradePanelBotId));
      if (!column || !row) return;

      const nextOffset = Math.max(
        0,
        Math.round(row.getBoundingClientRect().top - column.getBoundingClientRect().top)
      );
      setTradePanelOffset((currentOffset) => (
        currentOffset === nextOffset ? currentOffset : nextOffset
      ));
    };

    const animationFrame = window.requestAnimationFrame(updateTradePanelOffset);
    window.addEventListener("resize", updateTradePanelOffset);

    const resizeObserver = typeof ResizeObserver === "undefined"
      ? null
      : new ResizeObserver(updateTradePanelOffset);
    if (resizeObserver) {
      resizeObserver.observe(botListColumnRef.current);
      const selectedRow = botRowRefs.current.get(String(tradePanelBotId));
      if (selectedRow) resizeObserver.observe(selectedRow);
    }

    return () => {
      window.cancelAnimationFrame(animationFrame);
      window.removeEventListener("resize", updateTradePanelOffset);
      resizeObserver?.disconnect();
    };
  }, [expandedBotId, filteredBots, tradePanelBotId]);

  useEffect(() => {
    if (!filteredBots.length) {
      if (activeBot) setActiveBot(null);
      return;
    }
    if (!filteredBots.some((bot) => bot.id === activeBot?.id)) {
      const nextBot = filteredBots[0];
      setActiveBot(nextBot);
      setExpandedBotId(nextBot.id);
      persistBotSelection(nextBot.id);
    }
  }, [activeBot, filteredBots, setActiveBot]);

  const getBotPresentation = (bot) => {
    const portfolio = portfolios.find((item) => item.bot_id === bot.id);
    const decision = decisionsByBot?.[bot.id] || {};
    const symbol = String(
      portfolio?.symbol ||
      bot?.strategy?.setup?.symbol ||
      bot?.strategy?.symbol ||
      bot?.symbol ||
      "—"
    ).toUpperCase();
    const timeframe =
      bot?.strategy?.setup?.timeframe ||
      bot?.strategy?.timeframe ||
      bot?.timeframe ||
      "—";
    const rawAction = String(decision?.action || "").toLowerCase();
    const action = rawAction
      ? copy.agentCard?.actionLabels?.[rawAction] || rawAction.toUpperCase()
      : copy.botList?.insufficientData || "Onvoldoende data";
    const rawConfidence = decision?.confidence_label || decision?.confidence;
    const confidence = rawConfidence
      ? String(rawConfidence).toUpperCase()
      : copy.botList?.insufficientData || "Onvoldoende data";

    return { portfolio, decision, symbol, timeframe, action, confidence };
  };

  const askFinnAboutBot = (bot) => {
    const { symbol, timeframe } = getBotPresentation(bot);
    const language = String(locale || "nl").slice(0, 2);
    const query = language === "en"
      ? `Review bot ${bot.name}. Briefly explain its current status and risks, then give one concrete next step.`
      : language === "de"
        ? `Bewerte Bot ${bot.name}. Erklaere kurz den aktuellen Status und die Risiken und nenne einen konkreten naechsten Schritt.`
        : `Beoordeel bot ${bot.name}. Leg kort uit wat de huidige status en risico's betekenen en geef een concrete volgende stap.`;

    openFinnContext({
      query,
      context: {
        page: "/bot",
        page_type: copy.title || "Automation",
        symbol,
        timeframe,
        bot_id: bot.id,
        bot_name: bot.name,
        strategy_id: bot?.strategy?.id || bot?.strategy_id || null,
        finn_subject_type: "bot",
        locale,
      },
    });
  };

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

  const closeBotDrawer = () => {
    if (botFormRef.current?.isSubmitting?.() || budgetFormRef.current?.isSubmitting?.()) {
      return;
    }
    setDrawer(null);
  };

  const hasConfiguredBudget = (budget) =>
    Number(budget?.total_eur ?? 0) > 0 ||
    Number(budget?.daily_limit_eur ?? 0) > 0 ||
    Number(budget?.max_order_eur ?? 0) > 0;

  const focusSavedBot = (savedBot, fallbackBot = null) => {
    const candidate = savedBot?.bot ?? savedBot ?? fallbackBot;
    const botId = Number(candidate?.id ?? fallbackBot?.id ?? 0);

    if (botId > 0) {
      setPendingFocusedBotId(botId);
      setExpandedBotId(botId);
      persistBotSelection(botId);
    }

    if (candidate) {
      const resolvedCandidate = resolveBotChain(candidate, strategies, setups);
      setActiveBot(resolvedCandidate);
    }

    setDrawer(null);
  };

  const handleAddBot = (initialValues = {}) => {
    const isPlanActivation = Boolean(initialValues?.strategy_id);
    setDrawer({
      type: "create-bot",
      initialValues,
      fromPlan: isPlanActivation,
    });
  };

  useEffect(() => {
    const action = searchParams.get("action");
    if (action === "new_bot") {
      if (!strategies.length) return;

      const symbol = searchParams.get("symbol") || "";
      const requestedStrategyId = Number(searchParams.get("strategy_id"));
      const requestedPlanName = searchParams.get("plan_name") || "";
      const mode = searchParams.get("mode") || "paper";
      const risk = searchParams.get("risk") || "balanced";
      const budget = searchParams.get("budget") || "";
      const matchingStrategy =
        Number.isFinite(requestedStrategyId) && requestedStrategyId > 0
          ? strategies.find((strategy) => strategy.id === requestedStrategyId) || null
          : null;
      
      // Auto-prefill the form values
      const initialValues = {
        name:
          requestedPlanName ||
          (matchingStrategy?.name
            ? `${matchingStrategy.name} Bot`
            : `Finn Bot ${symbol} ${mode === "paper" ? copy.modePaper : copy.modeLive}`),
        symbol: symbol,
        strategy_id: matchingStrategy?.id ?? null,
        is_live: mode === "live",
        risk_profile: risk,
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
      setDrawer({
        type: "edit-bot",
        bot,
      });
      return;
    }
    if (type === "portfolio") {
      const portfolio = portfolios.find((p) => p.bot_id === bot.id);
      setDrawer({
        type: "budget-bot",
        bot,
        initialBudget: {
          total_eur: portfolio?.budget?.total_eur ?? 0,
          daily_limit_eur: portfolio?.budget?.daily_limit_eur ?? 0,
          max_order_eur: portfolio?.budget?.max_order_eur ?? 0,
          max_asset_exposure_pct: portfolio?.budget?.max_asset_exposure_pct ?? 100,
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

  const handleGenerateDecision = async (bot, { silent = false } = {}) => {
    try {
      setGeneratingBotId(bot.id);
      await generateDecisionForBot({ bot_id: bot.id });
      if (!silent) {
        showSnackbar(`${copy.proposalCreatedPrefix} ${bot.name}`, "success");
      }
    } catch {
      if (!silent) {
        showSnackbar(copy.proposalCreateFailed, "danger");
      }
    } finally {
      setGeneratingBotId(null);
    }
  };

  return (
    <div className="page-container !max-w-none !px-6 bg-white dark:bg-[#020617] transition-colors h-auto overflow-visible">
      
      {/* 🟢 STANDARD PAGE HEADER */}
      <header className="page-header border-l-4 border-blue-600 pl-8 mb-8">
        <div className="page-label text-[11px] font-black text-blue-600 dark:text-blue-500 uppercase tracking-[0.3em] mb-2 opacity-80 flex items-center gap-2">
           <Wallet size={12} />
           {copy.eyebrow}
        </div>
          <div className="max-w-2xl">
            <h1 className="page-title text-4xl font-black text-slate-900 dark:text-slate-100 tracking-tight leading-none mb-3">{copy.title}</h1>
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

      <div className="max-w-full flex flex-col lg:flex-row gap-8 pb-24 items-start relative">
        
        {/* 🕋 LEFT: MAIN COMMAND CENTER */}
        <div ref={botListColumnRef} className="flex-1 min-w-0 space-y-8">
          {error && (
            <div className="rounded-2xl border border-red-200 bg-red-50 px-5 py-4 text-sm font-bold text-red-700 dark:border-red-900/60 dark:bg-red-950/30 dark:text-red-200">
              {copy.partialError}
            </div>
          )}

          {/* BOT DEPLOYMENT SECTION */}
          <div className="space-y-6">
            <div className="space-y-4">
              <div>
                <h2 className="text-3xl font-black text-slate-900 dark:text-slate-100 tracking-tighter">{copy.myBotsTitle}</h2>
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

            <div className="overflow-hidden rounded-3xl border border-slate-200 bg-white shadow-sm dark:border-slate-800 dark:bg-slate-950">
              <div className="hidden grid-cols-[minmax(0,2fr)_0.8fr_0.8fr_0.8fr_auto] gap-4 border-b border-slate-100 bg-slate-50/70 px-5 py-3 text-[9px] font-black uppercase tracking-[0.2em] text-slate-400 dark:border-slate-800 dark:bg-slate-900/60 md:grid">
                <span>{copy.botList?.bot || "Bot"}</span>
                <span>{copy.botList?.status || "Status"}</span>
                <span>{copy.botList?.action || "Action"}</span>
                <span>{copy.botList?.confidence || "Confidence"}</span>
                <span className="sr-only">{copy.botList?.open || "Open"}</span>
              </div>

              {filteredBots.map((bot) => {
                const isSelected = activeBot?.id === bot.id;
                const isExpanded = expandedBotId === bot.id;
                const presentation = getBotPresentation(bot);
                const toggleBot = () => {
                  if (!isSelected) {
                    setActiveBot(bot);
                    setExpandedBotId(bot.id);
                    setTradePanelBotId(null);
                    persistBotSelection(bot.id);
                    return;
                  }
                  setExpandedBotId((currentId) => currentId === bot.id ? null : bot.id);
                };
                const toggleTradePanel = (event) => {
                  event?.stopPropagation();
                  if (!isSelected) {
                    setActiveBot(bot);
                    setExpandedBotId(bot.id);
                    persistBotSelection(bot.id);
                  }
                  setTradePanelBotId((currentId) => currentId === bot.id ? null : bot.id);
                };
                return (
                  <div
                    key={bot.id}
                    ref={(node) => {
                      const botKey = String(bot.id);
                      if (node) botRowRefs.current.set(botKey, node);
                      else botRowRefs.current.delete(botKey);
                    }}
                    className="border-b border-slate-100 last:border-b-0 dark:border-slate-800"
                  >
                    <div
                      role="button"
                      tabIndex={0}
                      aria-expanded={isExpanded}
                      onClick={toggleBot}
                      onKeyDown={(event) => {
                        if (event.key === "Enter" || event.key === " ") {
                          event.preventDefault();
                          toggleBot();
                        }
                      }}
                      className={`group grid cursor-pointer grid-cols-[minmax(0,1fr)_auto] items-center gap-4 px-5 py-4 transition md:grid-cols-[minmax(0,2fr)_0.8fr_0.8fr_0.8fr_auto] ${isSelected ? "bg-blue-50 ring-1 ring-inset ring-blue-200 shadow-[inset_3px_0_0_#2563eb] dark:bg-blue-950/25 dark:ring-blue-900" : "hover:bg-slate-50 dark:hover:bg-slate-900/50"}`}
                    >
                      <div className="flex min-w-0 items-center gap-3">
                        <span className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-xl ${isSelected ? "bg-blue-600 text-white" : "bg-slate-100 text-slate-500 dark:bg-slate-900"}`}>
                          <Bot size={18} />
                        </span>
                        <span className="min-w-0">
                          <span className="block truncate text-sm font-black text-slate-950 dark:text-white">{bot.name}</span>
                          <span className="mt-1 block text-[10px] font-bold uppercase tracking-[0.16em] text-slate-400">
                            {presentation.symbol} · {presentation.timeframe} · {bot.is_live ? copy.modeLive : copy.modePaper}
                          </span>
                        </span>
                      </div>

                      <span className={`hidden w-fit rounded-full border px-2.5 py-1 text-[9px] font-black uppercase tracking-[0.16em] md:inline-flex ${bot.is_active ? "border-emerald-200 bg-emerald-50 text-emerald-700" : "border-amber-200 bg-amber-50 text-amber-700"}`}>
                        {bot.is_active ? copy.filterActive : copy.filterPaused}
                      </span>
                      <span className="hidden text-xs font-black uppercase text-blue-700 dark:text-blue-300 md:block">{presentation.action}</span>
                      <span className="hidden text-xs font-black uppercase text-slate-600 dark:text-slate-300 md:block">{presentation.confidence}</span>

                      <div className="flex items-center justify-end gap-1">
                        <button
                          type="button"
                          aria-pressed={tradePanelBotId === bot.id}
                          onClick={toggleTradePanel}
                          className={`inline-flex min-h-9 items-center gap-1.5 rounded-xl px-2.5 text-[11px] font-black transition ${tradePanelBotId === bot.id ? "bg-blue-600 text-white shadow-sm" : "text-slate-400 hover:bg-blue-100 hover:text-blue-700 dark:hover:bg-blue-950/50 dark:hover:text-blue-300"}`}
                        >
                          <Wallet size={14} />
                          <span className="hidden xl:inline">
                            {tradePanelBotId === bot.id
                              ? (copy.botList?.closeTrade || "Close")
                              : (copy.botList?.trade || "Trade")}
                          </span>
                        </button>
                        <button
                          type="button"
                          onClick={(event) => {
                            event.stopPropagation();
                            askFinnAboutBot(bot);
                          }}
                          className="inline-flex min-h-9 items-center gap-1.5 rounded-xl px-2.5 text-[11px] font-black text-slate-400 opacity-100 transition hover:bg-blue-100 hover:text-blue-700 focus-visible:opacity-100 dark:hover:bg-blue-950/50 dark:hover:text-blue-300 lg:opacity-0 lg:group-hover:opacity-100"
                        >
                          <Sparkles size={14} />
                          <span className="hidden xl:inline">{copy.botList?.askFinn || "Ask FINN"}</span>
                        </button>
                        <ChevronDown size={17} className={`text-slate-400 transition-transform ${isExpanded ? "rotate-180 text-blue-600" : ""}`} />
                      </div>
                    </div>

                    {isExpanded && (
                      <div className="border-t border-blue-100 bg-blue-50/30 p-3 sm:p-5 dark:border-blue-950 dark:bg-blue-950/10">
                        <BotAgentCard
                          bot={bot}
                          decision={presentation.decision}
                          order={(today?.orders || []).find((o) => o.bot_id === bot.id)}
                          marketIntelligence={marketIntelligence}
                          loadingMarketIntelligence={loadingMarketIntelligence}
                          portfolio={presentation.portfolio}
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
                          onTrade={() => toggleTradePanel()}
                          tradeActionLabel={
                            tradePanelBotId === bot.id
                              ? (copy.botList?.closeTrade || "Close")
                              : (copy.botList?.trade || "Trade")
                          }
                          tradeActive={tradePanelBotId === bot.id}
                          onAskFinn={() => askFinnAboutBot(bot)}
                          finnActionLabel={copy.botList?.askFinn || "Ask FINN"}
                          compact
                        />
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        </div>

        {tradePanelBotId === activeBot?.id && (
          <>
            <button
              type="button"
              aria-label={copy.botList?.closeTrade || "Sluiten"}
              onClick={() => setTradePanelBotId(null)}
              className="fixed inset-0 z-[80] bg-slate-950/45 backdrop-blur-[2px] lg:hidden"
            />
            <div
              style={{ "--trade-panel-offset": `${tradePanelOffset}px` }}
              className="fixed inset-x-0 bottom-0 z-[90] max-h-[88vh] overflow-y-auto rounded-t-[2rem] bg-white p-3 shadow-2xl dark:bg-slate-950 lg:sticky lg:inset-auto lg:top-24 lg:z-auto lg:mt-[var(--trade-panel-offset)] lg:max-h-none lg:w-[350px] lg:shrink-0 lg:overflow-visible lg:rounded-none lg:bg-transparent lg:p-0 lg:shadow-none lg:dark:bg-transparent"
            >
            <div id="tp-final-v2200-smooth">
              <GlobalTradePanel
                decision={decisionsByBot?.[activeBot?.id]}
                portfolio={portfolios.find((p) => p.bot_id === activeBot?.id)}
                onManualTrade={() => handleGenerateDecision(activeBot)}
                onClose={() => setTradePanelBotId(null)}
              />
            </div>
            </div>
          </>
        )}

      </div>

      <Drawer
        isOpen={drawer?.type === "create-bot" || drawer?.type === "edit-bot"}
        onClose={closeBotDrawer}
        isCloseBlocked={() =>
          Boolean(botFormRef.current?.isSubmitting?.() || budgetFormRef.current?.isSubmitting?.())
        }
        title={
          drawer?.type === "edit-bot"
            ? (copy.editTitle || copy.updateTitlePrefix)
            : drawer?.fromPlan
              ? copy.createFromPlanTitle
              : copy.createTitle
        }
        subtitle={
          drawer?.type === "edit-bot"
            ? copy.updateStatus
            : drawer?.fromPlan
              ? copy.createFromPlanStatus
              : copy.createStatus
        }
        width="max-w-2xl"
      >
        <AddBotForm
          ref={botFormRef}
          strategies={strategies}
          initialData={drawer?.type === "edit-bot" ? drawer?.bot : null}
          initialValues={drawer?.type === "create-bot" ? drawer?.initialValues : null}
          hideActions={false}
          submitLabel={
            drawer?.type === "edit-bot"
              ? copy.updateConfirm
              : drawer?.fromPlan
                ? copy.createFromPlanConfirm
                : copy.createConfirm
          }
          submitBusyLabel={
            drawer?.type === "edit-bot"
              ? copy.updateBusy
              : drawer?.fromPlan
                ? copy.createFromPlanBusy
                : copy.createBusy
          }
          cancelLabel={t?.common?.cancel || "Annuleren"}
          successMessage={
            drawer?.type === "edit-bot"
              ? copy.updateSuccess
              : drawer?.fromPlan
                ? copy.createFromPlanSuccess
                : copy.createSuccess
          }
          saveFailedMessage={copy.form?.saveFailed || copy.createValidation}
          onCancel={closeBotDrawer}
          onSubmit={async (payload) => {
            if (drawer?.type === "edit-bot" && drawer?.bot?.id) {
              return await updateBot(drawer.bot.id, payload);
            }
            return await createBot(payload);
          }}
          onSaved={(savedBot) => focusSavedBot(savedBot, drawer?.bot || null)}
        />
      </Drawer>

      <Drawer
        isOpen={drawer?.type === "budget-bot"}
        onClose={closeBotDrawer}
        isCloseBlocked={() =>
          Boolean(botFormRef.current?.isSubmitting?.() || budgetFormRef.current?.isSubmitting?.())
        }
        title={
          hasConfiguredBudget(drawer?.initialBudget)
            ? (copy.budgetEditTitle || copy.budgetTitlePrefix)
            : (copy.budgetSetTitle || copy.budgetTitlePrefix)
        }
        subtitle={copy.budgetStatus}
        width="max-w-xl"
      >
        <BotBudgetForm
          ref={budgetFormRef}
          initialBudget={drawer?.initialBudget || null}
          hideActions={false}
          submitLabel={copy.budgetConfirm}
          submitBusyLabel={copy.budgetBusy}
          cancelLabel={t?.common?.cancel || "Annuleren"}
          successMessage={copy.budgetSuccess}
          saveFailedMessage={copy.budgetForm?.saveFailed || copy.partialError}
          onCancel={closeBotDrawer}
          onSubmit={async (budget) => {
            if (!drawer?.bot?.id) return null;
            const result = await updateBot(drawer.bot.id, {
              budget_total_eur: budget.total_eur,
              budget_daily_limit_eur: budget.daily_limit_eur,
              budget_max_order_eur: budget.max_order_eur,
              max_asset_exposure_pct: budget.max_asset_exposure_pct,
            });
            await handleGenerateDecision(drawer.bot, { silent: true });
            return result;
          }}
          onSaved={(savedBot) => focusSavedBot(savedBot, drawer?.bot || null)}
        />
      </Drawer>
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
