"use client";

import { useEffect, useRef, useState, useMemo } from "react";
import { Wallet, Plus } from "lucide-react";

import useBotData from "@/hooks/useBotData";
import { useStrategyData } from "@/hooks/useStrategyData";
import { useModal } from "@/components/modal/ModalProvider";

import { useMarketIntelligence } from "@/hooks/useMarketIntelligence";
import BotAgentCard from "@/components/bot/BotAgentCard";
import BotScores from "@/components/bot/BotScores";
import BotForm from "@/components/bot/AddBotForm";
import BotBudgetForm from "@/components/bot/BotBudgetForm";
import BotPortfolioOverview from "@/components/bot/BotPortfolioOverview";
import PortfolioBalanceCard from "@/components/bot/PortfolioBalanceCard";
import GlobalTradePanel from "@/components/bot/GlobalTradePanel";

import {
  ActiveBotProvider,
  useActiveBot,
} from "@/app/providers/ActiveBotProvider";

function BotPageInner() {
  const { openConfirm, showSnackbar } = useModal();
  const formRef = useRef({});
  const budgetRef = useRef({});

  const { activeBot, setActiveBot } = useActiveBot();

  const [statusFilter, setStatusFilter] = useState("all");
  const [generatingBotId, setGeneratingBotId] = useState(null);
  const [executingBotId, setExecutingBotId] = useState(null);
  const [placingOrderBotId, setPlacingOrderBotId] = useState(null);

  const {
    configs: bots = [],
    today,
    history = [],
    portfolios = [],
    decisionsByBot = {},
    tradesByBot = {},
    loading,

    createBot,
    updateBot,
    deleteBot,

    generateDecisionForBot,
    executeBotDecision, 
    skipBot, 

    saveTradePlanForDecision,
    createManualOrder,
  } = useBotData();

  const { strategies = [], loadStrategies } = useStrategyData();

  const {
    data: marketIntelligence,
    loading: loadingMarketIntelligence,
  } = useMarketIntelligence();

  useEffect(() => {
    loadStrategies();
  }, [loadStrategies]);

  useEffect(() => {
    if (bots.length === 0) {
      setActiveBot(null);
      return;
    }
    if (!activeBot || !bots.find((b) => b.id === activeBot.id)) {
      setActiveBot(bots[0]);
    }
  }, [bots, activeBot, setActiveBot]);

  const dailyScores = today?.daily_scores ?? today?.scores ?? {
    macro: 10, technical: 10, market: 10, setup: 10
  };

  const aggregatedBotsForOverview = useMemo(() => {
    return bots.map((bot) => {
      const p = portfolios.find((x) => x.bot_id === bot.id);
      return {
        bot_id: bot.id,
        symbol: p?.symbol ?? bot?.symbol ?? "—",
        budget: p?.budget ?? {},
        stats: p?.stats ?? {},
      };
    });
  }, [bots, portfolios]);
  
  const filteredBots = useMemo(() => {
    return bots.filter((bot) => {
      if (statusFilter === "active") return bot.is_active;
      if (statusFilter === "paused") return !bot.is_active;
      return true;
    });
  }, [bots, statusFilter]);

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
    const single = [{ ts: new Date().toISOString(), value_eur: totalPortfolioValueEur }];
    return { "1D": single, "1W": single, "1M": single, "1Y": single, ALL: single };
  }, [today, totalPortfolioValueEur]);

  const handleGenerateDecision = async (bot) => {
    try { setGeneratingBotId(bot.id); await generateDecisionForBot({ bot_id: bot.id }); showSnackbar(`Nieuw voorstel voor ${bot.name}`, "success"); }
    catch { showSnackbar("Fout bij genereren voorstel", "danger"); }
    finally { setGeneratingBotId(null); }
  };

  const handleAddBot = () => {
    formRef.current = {};
    openConfirm({
      title: "➕ Nieuwe Bot",
      description: <BotForm strategies={strategies} onChange={(v) => (formRef.current = v)} />,
      confirmText: "Bot aanmaken",
      onConfirm: async () => {
        if (!formRef.current?.name || !formRef.current?.strategy_id) { showSnackbar("Vul alle velden in", "danger"); return; }
        await createBot(formRef.current); showSnackbar("Bot toegevoegd", "success");
      },
    });
  };

  const handleOpenBotSettings = async (type, bot) => {
    if (!bot) return;
    if (type === "general") {
      formRef.current = bot;
      openConfirm({
        title: "⚙️ Instellingen",
        description: <BotForm strategies={strategies} initialValues={bot} onChange={(v) => (formRef.current = v)} />,
        confirmText: "Opslaan",
        onConfirm: async () => { await updateBot(bot.id, formRef.current); showSnackbar("Bot bijgewerkt", "success"); },
      });
      return;
    }
    if (type === "portfolio") {
      const portfolio = portfolios.find((p) => p.bot_id === bot.id);
      budgetRef.current = { total_eur: portfolio?.budget?.total_eur ?? 0, daily_limit_eur: portfolio?.budget?.daily_limit_eur ?? 0, max_order_eur: portfolio?.budget?.max_order_eur ?? 0, max_asset_exposure_pct: portfolio?.budget?.max_asset_exposure_pct ?? 100 };
      openConfirm({
        title: "💰 Portfolio & Budget",
        description: <BotBudgetForm initialBudget={budgetRef.current} onChange={(v) => (budgetRef.current = v)} />,
        confirmText: "Opslaan",
        onConfirm: async () => { await updateBot(bot.id, { budget_total_eur: budgetRef.current.total_eur, budget_daily_limit_eur: budgetRef.current.daily_limit_eur, budget_max_order_eur: budgetRef.current.max_order_eur, max_asset_exposure_pct: budgetRef.current.max_asset_exposure_pct }); showSnackbar("Budget bijgewerkt", "success"); },
      });
      return;
    }
    if (type === "pause") { await updateBot(bot.id, { is_active: false }); showSnackbar("Bot gepauzeerd", "info"); return; }
    if (type === "resume") { await updateBot(bot.id, { is_active: true }); showSnackbar("Bot hervat", "success"); return; }
    if (type === "delete") { openConfirm({ title: "🗑️ Verwijderen", tone: "danger", confirmText: "Verwijderen", onConfirm: async () => { await deleteBot(bot.id); showSnackbar("Bot verwijderd", "danger"); } }); }
  };

  return (
    <div className="page-container !max-w-none !px-6">
      
      {/* 🟢 STANDARD PAGE HEADER */}
      <header className="page-header">
        <div className="page-label">
           <Wallet size={12} />
           Systeem-controle
        </div>
        <h1 className="page-title">Bots</h1>
        <p className="page-subtitle">Beheer je geautomatiseerde handelsstrategieën</p>
      </header>

      <div className="max-w-full grid grid-cols-1 lg:grid-cols-[1fr_350px] gap-10 items-start">
        
        {/* 🕋 LEFT: MAIN COMMAND CENTER */}
        <div className="space-y-12 min-w-0">
          <div className="space-y-6">
            <BotScores scores={dailyScores} loading={loading?.today} />
            
            <div className="card">
              <div className="card-header">
                <div className="card-title">Portfolio overzicht</div>
              </div>
              <div className="card-p">
                <PortfolioBalanceCard
                  title="RECAP"
                  defaultRange="1W"
                  dataByRange={portfolioBalanceDataByRange}
                />
              </div>
            </div>

            <BotPortfolioOverview bots={aggregatedBotsForOverview} />
          </div>

          {/* BOT DEPLOYMENT SECTION */}
          <div className="space-y-8">
            <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
              <div className="flex items-center gap-6">
                <h2 className="text-xl font-semibold text-slate-900 tracking-tight">Mijn Bots</h2>

                <div className="flex bg-slate-100 p-1 rounded-lg border border-slate-200">
                  <button onClick={() => setStatusFilter("all")} className={`px-4 py-1 rounded-md text-[10px] font-bold uppercase tracking-widest transition-all ${statusFilter === "all" ? "bg-white text-slate-800 shadow-sm" : "text-slate-400"}`}>Alle ({bots.length})</button>
                  <button onClick={() => setStatusFilter("active")} className={`px-4 py-1 rounded-md text-[10px] font-bold uppercase tracking-widest transition-all ${statusFilter === "active" ? "bg-white text-green-600 shadow-sm" : "text-slate-400"}`}>Actief ({bots.filter(b => b.is_active).length})</button>
                  <button onClick={() => setStatusFilter("paused")} className={`px-4 py-1 rounded-md text-[11px] font-bold uppercase tracking-widest transition-all ${statusFilter === "paused" ? "bg-white text-amber-600 shadow-sm" : "text-slate-400"}`}>Gepauzeerd ({bots.filter(b => !b.is_active).length})</button>
                </div>
              </div>

              <button onClick={handleAddBot} className="btn-primary flex items-center gap-2">
                <Plus size={16} />
                Nieuwe Bot
              </button>
            </div>

            <div className="space-y-10">
              {filteredBots.map((bot) => {
                const isActive = activeBot?.id === bot.id;
                return (
                  <div key={bot.id} onClick={(e) => { if (e.target.closest("button") || e.target.closest("input")) return; setActiveBot(bot); }} 
                  className={`relative transition-all duration-300 ${isActive ? "ring-2 ring-blue-600 ring-offset-4 rounded-3xl" : "hover:scale-[1.002]"}`}>
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
                    />
                  </div>
                );
              })}
            </div>
          </div>
        </div>

        {/* 🛰️ RIGHT: GLOBAL OVERRIDES */}
        <aside className="lg:sticky lg:top-8">
          <GlobalTradePanel />
        </aside>

      </div>
    </div>
  );
}

export default function BotPage() {
  return (
    <ActiveBotProvider>
      <BotPageInner />
    </ActiveBotProvider>
  );
}
