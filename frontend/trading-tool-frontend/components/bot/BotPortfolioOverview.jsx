"use client";

import { Wallet, Info, Zap, Clock, LayoutGrid } from "lucide-react";
import { useState, useMemo, useEffect } from "react";
import { useTranslation } from "@/app/providers/I18nProvider";
import { formatCurrency, formatNumber } from "@/lib/i18n";

import BotBudgetBar from "./BotBudgetBar";
import BotPnLBadge from "./BotPnLBadge";

/**
 * BotPortfolioOverview — READ ONLY
 * --------------------------------------------------
 * ✅ Aggregatie over ALLE bots
 * ✅ Filterbaar op Paper / Live
 * ✅ Budget usage = executed trades
 * ✅ Invested = executed trades only
 * ✅ Backend blijft single source of truth
 */
export default function BotPortfolioOverview({ 
  bots = [], 
  envFilter = "all", 
  onEnvFilterChange 
}) {
  const { t, locale } = useTranslation();
  const copy = t?.botPage?.portfolioOverview || {};
  const [exchangeBalances, setExchangeBalances] = useState([]);
  const [exchangeLoading, setExchangeLoading] = useState(false);

  useEffect(() => {
    if (envFilter === "live") {
      const fetchEx = async () => {
        setExchangeLoading(true);
        try {
          const res = await fetch("/api/exchange/balances");
          if (res.ok) {
            const data = await res.json();
            setExchangeBalances(data);
          }
        } catch (err) {
          console.error("Exchange fetch failed", err);
        } finally {
          setExchangeLoading(false);
        }
      };
      fetchEx();
    }
  }, [envFilter]);

  const list = useMemo(() => {
    const raw = Array.isArray(bots) ? bots : [];
    if (envFilter === "all") return raw;
    return raw.filter(b => envFilter === "live" ? b.is_live : !b.is_live);
  }, [bots, envFilter]);

  if (!Array.isArray(bots) || bots.length === 0) return null;

  // -----------------------------
  // Helper
  // -----------------------------
  const sum = (arr, getter) =>
    arr.reduce((acc, x) => acc + (Number(getter(x)) || 0), 0);

  // =============================
  // BUDGET AGGREGATES
  // =============================

  const totalBudgetEur = sum(list, (b) => b?.budget?.total_eur);
  const totalDailyLimitEur = sum(list, (b) => b?.budget?.daily_limit_eur);
  const totalMaxOrderEur = sum(list, (b) => b?.budget?.max_order_eur);

  // ✅ Alleen executed trades tellen voor budget usage
  const spentExecuted = sum(list, (b) =>
    Math.abs(b?.stats?.net_executed_cash_delta_eur ?? 0)
  );

  const todaySpent = sum(list, (b) => b?.stats?.today_spent_eur);

  const hasBudget =
    totalBudgetEur > 0 || totalDailyLimitEur > 0 || totalMaxOrderEur > 0;

  // =============================
  // PORTFOLIO AGGREGATES
  // =============================

  const positionValue = sum(list, (b) => b?.stats?.position_value_eur);

  const pnlEur = positionValue - spentExecuted;
  const pnlPct = spentExecuted > 0 ? (pnlEur / spentExecuted) * 100 : 0;

  // =============================
  // SYMBOL BREAKDOWN
  // =============================

  const bySymbol = list.reduce((acc, b) => {
    const sym = b?.symbol || "—";

    if (!acc[sym]) {
      acc[sym] = {
        symbol: sym,
        netQty: 0,
        positionValue: 0,
        spentExecuted: 0,
      };
    }

    acc[sym].netQty += Number(b?.stats?.net_qty ?? 0);
    acc[sym].positionValue += Number(b?.stats?.position_value_eur ?? 0);
    acc[sym].spentExecuted += Math.abs(
      Number(b?.stats?.net_executed_cash_delta_eur ?? 0)
    );

    return acc;
  }, {});

  const symbolRows = Object.values(bySymbol).sort(
    (a, b) => b.positionValue - a.positionValue
  );

  // =============================
  // UI
  // =============================

  return (
    <div className="card p-10 space-y-12 animate-fade-in mb-16">
      {/* HEADER WITH BLUE ACCENT */}
      <div className="flex items-start justify-between gap-4 pb-8 border-b-2 border-slate-100">
        <div className="border-l-4 border-blue-600 pl-6">
           <div className="text-[10px] font-black text-secondary gap-2 flex items-center uppercase tracking-[0.3em] mb-1">
              <Wallet size={10} className="text-blue-600" />
              {copy.eyebrow}
           </div>
           <h3 className="text-3xl font-black text-foreground tracking-tighter uppercase leading-none">
             {copy.title} <span className="text-blue-600/30">—</span> {envFilter === "all" ? copy.allBots : envFilter === "live" ? copy.liveExchange : copy.paperTrading}
           </h3>
            <p className="text-[13px] font-medium text-secondary mt-2">
              {copy.subtitle}
            </p>
        </div>

        <div className="flex flex-col items-end gap-4">
          <div className="flex bg-slate-100 dark:bg-slate-900 p-1.5 rounded-2xl border-2 border-slate-100 dark:border-slate-800 shadow-inner">
             <button 
                onClick={() => onEnvFilterChange?.("all")}
                className={`px-4 py-2 rounded-xl text-[10px] font-black uppercase tracking-widest transition-all flex items-center gap-2 ${envFilter === "all" ? 'bg-white dark:bg-slate-800 text-slate-900 shadow-md' : 'text-slate-400 hover:text-slate-600'}`}
             >
                <LayoutGrid size={12} />
                {copy.filterAll}
             </button>
             <button 
                onClick={() => onEnvFilterChange?.("paper")}
                className={`px-4 py-2 rounded-xl text-[10px] font-black uppercase tracking-widest transition-all flex items-center gap-2 ${envFilter === "paper" ? 'bg-white dark:bg-slate-800 text-blue-600 shadow-md' : 'text-slate-400 hover:text-blue-500'}`}
             >
                <Clock size={12} />
                {copy.filterPaper}
             </button>
             <button 
                onClick={() => onEnvFilterChange?.("live")}
                className={`px-4 py-2 rounded-xl text-[10px] font-black uppercase tracking-widest transition-all flex items-center gap-2 ${envFilter === "live" ? 'bg-white dark:bg-slate-800 text-emerald-600 shadow-md' : 'text-slate-400 hover:text-emerald-500'}`}
             >
                <Zap size={12} />
                {copy.filterLive}
             </button>
          </div>

          <div className="bg-[var(--color-border-subtle)] px-4 py-2 rounded-xl border-2 border-slate-200/50">
             <div className="text-[9px] font-black text-secondary uppercase tracking-widest">{copy.activeBots}</div>
             <span className="text-xl font-black text-foreground tracking-tighter tabular-nums">
               {list.length}
             </span>
          </div>
        </div>
      </div>

      {/* =============================
         BUDGET SECTION (BLUEPRINT STYLE)
      ============================= */}
      <div className="bg-blue-50/20 border-2 border-blue-600/5 rounded-3xl p-8">
        <div className="flex items-center justify-between gap-3 mb-6">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-blue-600 text-white rounded-lg shadow-lg shadow-blue-600/20">
               <Wallet size={16} />
            </div>
            <div>
               <div className="text-[10px] font-black text-secondary uppercase tracking-widest">{copy.budgetUsage}</div>
               <div className="text-[11px] font-bold text-blue-600/60 uppercase">{copy.backendSource}</div>
            </div>
          </div>

          {envFilter === 'live' && exchangeBalances.length > 0 && (
            <div className="flex items-center gap-4 animate-in fade-in slide-in-from-right-4 duration-500">
               <div className="text-right">
                  <div className="text-[9px] font-black text-secondary uppercase tracking-tighter">{copy.bitvavoCash}</div>
                  <div className="text-sm font-black text-emerald-600">{formatCurrency(Number(exchangeBalances[0]?.free?.EUR ?? 0), locale, "EUR", { maximumFractionDigits: 0 })}</div>
               </div>
               <div className="w-px h-8 bg-slate-200 dark:bg-slate-800" />
               <div className="text-right">
                  <div className="text-[9px] font-black text-secondary uppercase tracking-tighter">{copy.totalValue}</div>
                  <div className="text-sm font-black text-slate-900 dark:text-white">{formatCurrency(Number(exchangeBalances[0]?.total_eur ?? 0), locale, "EUR", { maximumFractionDigits: 0 })}</div>
               </div>
            </div>
          )}
        </div>

        {hasBudget ? (
          <div className="space-y-6">
            <BotBudgetBar
              label={copy.combinedBots}
              total={totalBudgetEur}
              spent={spentExecuted}
            />

            <div className="flex flex-wrap items-center gap-x-6 gap-y-2 pt-6 border-t border-blue-600/5">
               <div className="flex flex-col">
                  <span className="text-[9px] font-black text-secondary uppercase tracking-tighter">{copy.spentToday}</span>
                  <span className="text-sm font-black text-slate-800">{formatCurrency(Number(todaySpent ?? 0), locale, "EUR", { maximumFractionDigits: 0 })}</span>
               </div>
               {totalDailyLimitEur && (
                  <div className="flex flex-col">
                     <span className="text-[9px] font-black text-secondary uppercase tracking-tighter">{copy.dailyLimit}</span>
                     <span className="text-sm font-black text-slate-800">{formatCurrency(Number(totalDailyLimitEur), locale, "EUR", { maximumFractionDigits: 0 })}</span>
                  </div>
               )}
               {totalMaxOrderEur && (
                  <div className="flex flex-col">
                     <span className="text-[9px] font-black text-secondary uppercase tracking-tighter">{copy.maxPerTrade}</span>
                     <span className="text-sm font-black text-slate-800">{formatCurrency(Number(totalMaxOrderEur), locale, "EUR", { maximumFractionDigits: 0 })}</span>
                  </div>
               )}
            </div>
          </div>
        ) : (
          <div className="text-sm font-black text-secondary uppercase tracking-widest flex items-center gap-2 py-4">
             <Info size={16} /> {copy.noBudget}
          </div>
        )}
      </div>

      {/* =============================
         PORTFOLIO TOTAL METRICS
      ============================= */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-8 py-8 border-y-2 border-slate-100">
        <Stat label={copy.positions}>{symbolRows.length}</Stat>

        <Stat label={copy.totalValue}>
          {formatCurrency(Number(positionValue), locale, "EUR", { maximumFractionDigits: 0 })}
        </Stat>

        <Stat label={copy.investedExecuted}>
          {formatCurrency(Number(spentExecuted), locale, "EUR", { maximumFractionDigits: 0 })}
        </Stat>

        <Stat label={copy.totalPnl}>
          <BotPnLBadge pnlEur={pnlEur} pnlPct={pnlPct} />
        </Stat>
      </div>

      {/* =============================
         PER SYMBOL BREAKDOWN
      ============================= */}
      {symbolRows.length > 0 && (
        <div className="space-y-6">
          <div className="text-[10px] font-black text-secondary uppercase tracking-[0.25em]">
            {copy.byAsset}
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {symbolRows.map((row) => {
              const rowPnl = row.positionValue - row.spentExecuted;
              const rowPct =
                row.spentExecuted > 0
                  ? (rowPnl / row.spentExecuted) * 100
                  : 0;

              return (
                <div
                  key={row.symbol}
                  className="flex items-center justify-between gap-4 rounded-2xl border-2 border-slate-50 bg-slate-50/30 px-5 py-4 transition-all hover:border-blue-600/10 hover:bg-white"
                >
                  <div className="min-w-0">
                    <div className="text-[10px] font-black text-blue-600 uppercase tracking-widest mb-1 leading-none">
                      {row.symbol}
                    </div>
                    <div className="text-sm font-black text-foreground tracking-tighter">
                      {formatNumber(Number(row.netQty), locale, { minimumFractionDigits: 0, maximumFractionDigits: 6 })} <span className="opacity-40 text-[9px] uppercase tracking-normal">{row.symbol}</span>
                    </div>
                  </div>

                  <div className="text-right">
                    <div className="text-sm font-black text-foreground tracking-tight">
                      {formatCurrency(Number(row.positionValue), locale, "EUR", { maximumFractionDigits: 0 })}
                    </div>
                    <div className="mt-1">
                      <BotPnLBadge pnlEur={rowPnl} pnlPct={rowPct} />
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}

/* =============================
   UI HELPER
============================= */
function Stat({ label, children }) {
  return (
    <div className="flex flex-col">
      <div className="text-[10px] font-black text-secondary uppercase tracking-widest mb-3">{label}</div>
      <div className="text-3xl font-black text-foreground tracking-tighter leading-none">{children}</div>
    </div>
  );
}
